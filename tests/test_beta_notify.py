"""Host notifications use a local fake receiver only, never an actual webhook."""
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("beta_notify", ROOT / "deploy/beta/notify.py")
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)
NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)
SEED_DATABASE = "sqlite"


@pytest.fixture
def receiver():
    messages, responses = [], []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            messages.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(responses.pop(0) if responses else 200)
            self.send_header("Location", "/redirected")
            self.end_headers()
            self.wfile.write(b"ok")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/fake-private-token", messages, responses
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "traffic_notifications", lambda *args: True)
    for name in ("contacts", "status", "host-state"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(notify.shutil, "disk_usage", lambda _: SimpleNamespace(used=10, total=100))
    return tmp_path


def record(home, index=1, when=NOW, sent=False, **changes):
    directory = home / "contacts" / "sent" if sent else home / "contacts"
    directory.mkdir(exist_ok=True)
    path = directory / f"contact-{when:%Y%m%dT%H%M%S%fZ}-{index:032x}.json"
    value = dict(received_at=when.isoformat(), kind="removal", target_url="/theorems/example",
                 message="Please remove this entry", reply_to="private@example.invalid", source="192.0.2.123")
    path.write_text(json.dumps({**value, **changes}), encoding="utf-8")
    return path


def test_delivery_escapes_mentions_disables_formatting_and_omits_personal_fields(home, receiver):
    url, messages, _ = receiver
    path = record(home, message="& <!channel> <@U123> <https://example.invalid|link> @everyone *bold*", target_url="https://example.invalid/?x=<@U123>")
    assert notify.deliver(home, url, NOW)
    assert not path.exists() and (home / "contacts/sent" / path.name).exists()
    assert len(messages) == 1
    value = messages[0]
    assert value["mrkdwn"] is False and value["parse"] == "none" and value["link_names"] is False
    assert value["unfurl_links"] is False and value["unfurl_media"] is False
    assert value["blocks"][0]["text"]["type"] == "plain_text"
    text = value["text"]
    assert "&amp; &lt;!channel&gt; &lt;@U123&gt;" in text and "<" not in text and ">" not in text
    assert "192.0.2.123" not in json.dumps(value) and "private@example.invalid" not in json.dumps(value)
    assert "Reply address supplied: yes" in text and "Beta contact: removal" in text
    assert notify.deliver(home, url, NOW) and len(messages) == 1


def test_failure_retains_contact_for_next_run_without_logging_url(home, receiver, capsys):
    url, messages, responses = receiver
    path = record(home)
    responses.append(500)
    assert not notify.deliver(home, url, NOW) and path.exists()
    assert notify.deliver(home, url, NOW) and not path.exists()
    assert len(messages) == 2
    output = capsys.readouterr()
    assert url not in output.out + output.err and "fake-private-token" not in output.out + output.err


def test_redirect_is_not_followed_and_secret_is_not_logged(receiver, capsys):
    url, messages, responses = receiver
    responses.append(302)
    assert not notify.post(url, notify.payload("test"))
    assert len(messages) == 1
    assert "fake-private-token" not in capsys.readouterr().out


def test_oldest_first_batch_and_utf8_truncation(home, receiver):
    url, messages, _ = receiver
    paths = [record(home, index=i + 1, when=NOW - timedelta(minutes=i), message=("<&>字" * 500)) for i in range(7)]
    assert notify.BATCH == 5 and notify.MAX_PENDING == 1000
    assert notify.deliver(home, url, NOW) and len(messages) == 5
    assert [path.exists() for path in paths] == [True, True, False, False, False, False, False]
    assert all(len(item["text"].encode("utf-8")) < 2800 and item["text"].endswith("[truncated]") for item in messages)
    assert messages[0]["text"].splitlines()[1].endswith((NOW - timedelta(minutes=6)).isoformat())


def test_reset_watch_disk_and_full_events_are_deduplicated(home, receiver, monkeypatch):
    url, messages, _ = receiver
    error = home / "status/reset-error.json"
    error.write_text(json.dumps(dict(stage="prepare", failed_at="2026-10-23T01:00:00Z")))
    notify.atomic_json(home / "host-state/watch-alerts.json", dict(freeze=True, stop_web=True, counters_unavailable=True))
    monkeypatch.setattr(notify.shutil, "disk_usage", lambda _: SimpleNamespace(used=85, total=100))
    monkeypatch.setattr(notify, "MAX_PENDING", 1)
    monkeypatch.setattr(notify, "BATCH", 0)
    record(home)
    assert notify.deliver(home, url, NOW) and len(messages) == 6
    assert notify.deliver(home, url, NOW) and len(messages) == 6
    error.write_text(json.dumps(dict(stage="swap", failed_at="2026-10-23T02:00:00Z")))
    assert notify.deliver(home, url, NOW) and len(messages) == 7
    error.unlink()
    assert notify.deliver(home, url, NOW)
    error.write_text(json.dumps(dict(stage="swap", failed_at="2026-10-23T02:00:00Z")))
    assert notify.deliver(home, url, NOW) and len(messages) == 8


def test_failed_operational_notification_is_retried(home, receiver):
    url, messages, responses = receiver
    (home / "status/reset-error.json").write_text(json.dumps(dict(stage="prepare", failed_at="2026-10-23T01:00:00Z")))
    responses.append(500)
    assert not notify.deliver(home, url, NOW)
    assert notify.deliver(home, url, NOW) and len(messages) == 2
    assert notify.deliver(home, url, NOW) and len(messages) == 2


def test_disk_severity_changes_but_small_percentage_changes_do_not_repeat(home, receiver, monkeypatch):
    url, messages, _ = receiver
    usage = SimpleNamespace(used=80, total=100)
    monkeypatch.setattr(notify.shutil, "disk_usage", lambda _: usage)
    assert notify.deliver(home, url, NOW) and len(messages) == 1
    usage.used = 84
    assert notify.deliver(home, url, NOW) and len(messages) == 1
    usage.used = 85
    assert notify.deliver(home, url, NOW) and len(messages) == 2


def test_notification_lock_prevents_overlapping_delivery(home):
    path = home / "host-state/test.lock"
    with notify.delivery_lock(path):
        with pytest.raises(OSError):
            with notify.delivery_lock(path):
                pytest.fail("overlapping delivery must be locked out")
    with notify.delivery_lock(path):
        pass


def test_retention_deletes_only_matching_files_after_90_days(home):
    old = NOW - timedelta(days=90)
    sent = record(home, when=old, sent=True)
    unsent = record(home, index=2, when=old)
    recent = record(home, index=3, when=old + timedelta(seconds=1), sent=True)
    unrelated = home / "contacts/sent/do-not-delete.json"
    unrelated.write_text("preserve")
    os.utime(unrelated, (0, 0))
    named_directory = home / "contacts/sent" / f"contact-{old:%Y%m%dT%H%M%S%fZ}-{'a'*32}.json"
    named_directory.mkdir()
    assert notify.prune(home / "contacts/sent", NOW) == 1
    assert notify.prune(home / "contacts", NOW) == 1
    assert not sent.exists() and not unsent.exists()
    assert recent.exists() and unrelated.exists() and named_directory.is_dir()


def test_missing_webhook_is_one_line_and_noop(home, monkeypatch, capsys):
    monkeypatch.delenv("DEM_BETA_SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["notify.py", str(home)])
    assert notify.main() == 0
    assert capsys.readouterr().out.count("\n") == 1
    assert not list((home / "host-state").iterdir())


def test_record_only_hook_never_sends(home, monkeypatch):
    monkeypatch.setenv("DEM_BETA_SLACK_WEBHOOK_URL", "not-a-real-secret")
    monkeypatch.setattr(sys, "argv", ["notify.py", str(home), "--record-only", "--watch", "85", "1", "0", "0"])
    monkeypatch.setattr(notify, "post", lambda *args: pytest.fail("record-only must not send"))
    assert notify.main() == 0
    assert json.loads((home / "host-state/watch-alerts.json").read_text())["freeze"] is True


def test_invalid_records_are_quarantined_and_bad_state_fails_without_exposing_data(home, receiver, monkeypatch, capsys):
    url, messages, _ = receiver
    path = record(home)
    path.write_text("broken")
    assert notify.deliver(home, url, NOW) and not path.exists()
    assert (home / "contacts/invalid" / path.name).exists()
    assert len(messages) == 1 and "invalid records quarantined" in messages[0]["text"]
    (home / "host-state/notify-state.json").write_text("broken")
    monkeypatch.setenv("DEM_BETA_SLACK_WEBHOOK_URL", url)
    monkeypatch.setattr(sys, "argv", ["notify.py", str(home)])
    assert notify.main() == 1
    output = capsys.readouterr()
    assert url not in output.out + output.err


def test_six_invalid_records_do_not_spend_valid_delivery_slots(home, receiver):
    url, messages, _ = receiver
    broken = [b"{", b"[]", b'{"kind":[]}', b"{}", b"x" * 16385, b"\xff"]
    invalid = []
    for index, contents in enumerate(broken):
        path = record(home, index=index + 1, when=NOW - timedelta(minutes=10))
        path.write_bytes(contents)
        invalid.append(path)
    good = [record(home, index=index + 20) for index in range(7)]
    assert notify.deliver(home, url, NOW)
    assert all(not path.exists() and (home / "contacts/invalid" / path.name).exists() for path in invalid)
    contacts = [item for item in messages if item["text"].startswith("Beta contact: removal")]
    alerts = [item for item in messages if "invalid records quarantined" in item["text"]]
    assert len(contacts) == 5 and len(alerts) == 1 and "count=6" in alerts[0]["text"]
    assert sum(path.exists() for path in good) == 2
    assert notify.deliver(home, url, NOW)
    assert len(messages) == 8  # Only the two remaining good records; no repeated alert.


def test_quarantine_notification_is_retried_without_repeating_acknowledged_files(home, receiver):
    url, messages, responses = receiver
    path = record(home)
    path.write_text("broken")
    responses.append(500)
    assert not notify.deliver(home, url, NOW)
    assert notify.deliver(home, url, NOW) and len(messages) == 2
    assert notify.deliver(home, url, NOW) and len(messages) == 2
    second = record(home, index=2)
    second.write_text("broken")
    assert notify.deliver(home, url, NOW) and len(messages) == 3
    assert "count=1" in messages[-1]["text"]


def test_quarantined_files_expire_without_reannouncing_remaining_files(home, receiver):
    url, messages, _ = receiver
    old = record(home, when=NOW - timedelta(days=89))
    recent = record(home, index=2)
    for path in (old, recent):
        path.write_text("broken")
    assert notify.deliver(home, url, NOW) and len(messages) == 1
    unrelated = home / "contacts/invalid/unrelated.json"
    unrelated.write_text("keep")
    assert notify.deliver(home, url, NOW + timedelta(days=1))
    assert not (home / "contacts/invalid" / old.name).exists()
    assert (home / "contacts/invalid" / recent.name).exists() and unrelated.exists()
    assert len(messages) == 1
    assert notify.deliver(home, url, NOW + timedelta(days=90))
    assert not (home / "contacts/invalid" / recent.name).exists() and unrelated.exists()
