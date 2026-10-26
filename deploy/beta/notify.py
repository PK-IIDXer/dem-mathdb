"""Host-only Slack delivery. Standard library only; never print credentials."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request
from urllib.parse import urlsplit

CONTACT = re.compile(r"contact-(\d{8}T\d{12}Z)-[0-9a-f]{32}\.json\Z")
MAX_PENDING = 1000
BATCH = 5
RETENTION = 90 * 86400


def atomic_json(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".notify-", delete=False) as output:
            temporary = Path(output.name)
            os.chmod(temporary, 0o600)
            json.dump(value, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def contact_files(directory):
    return sorted((path for path in directory.iterdir()
                   if CONTACT.fullmatch(path.name) and not path.is_symlink() and path.is_file()),
                  key=lambda path: path.name)


def prune(directory, now):
    """Receipt-based retention, restricted to our exact filename shape."""
    deleted = 0
    for path in contact_files(directory):
        received = datetime.strptime(CONTACT.fullmatch(path.name)[1], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
        if (now - received).total_seconds() >= RETENTION:
            path.unlink()
            deleted += 1
    return deleted


def slack_text(text):
    # Escape character by character so truncation cannot cut an entity. Bound
    # UTF-8 bytes too, keeping the block below Slack's 3,000-character limit.
    pieces, size = [], 0
    for char in text:
        escaped = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}.get(char, char)
        if size + len(escaped.encode("utf-8")) > 2700:
            pieces.append("\n[truncated]")
            break
        pieces.append(escaped)
        size += len(escaped.encode("utf-8"))
    return "".join(pieces)


def payload(text):
    escaped = slack_text(text)
    return {"text": escaped, "mrkdwn": False, "parse": "none", "link_names": False,
            "unfurl_links": False, "unfurl_media": False,
            "blocks": [{"type": "section", "text": {"type": "plain_text", "text": escaped, "emoji": False}}]}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(webhook, value):
    try:
        url = urlsplit(webhook)
        # Loopback HTTP is solely for the local fake receiver tests.
        valid = (url.scheme == "https" and url.hostname in {"hooks.slack.com", "hooks.slack-gov.com"} and url.port in {None, 443} and url.path.startswith("/services/")) or (
            url.scheme == "http" and url.hostname in {"127.0.0.1", "::1"})
        if not valid or url.username or url.password or url.query or url.fragment:
            raise ValueError("invalid notification destination")
        request = urllib.request.Request(webhook, data=json.dumps(value).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        # No environment proxies, redirects, response bodies or exception text
        # enter logs. A redirect must never forward this secret URL elsewhere.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=5) as response:
            return response.status == 200 and response.read(32).strip() == b"ok"
    except Exception:
        print("dem-beta notify: delivery failed")
        return False


def read_json(path, maximum=16384):
    if path.is_symlink() or path.stat().st_size > maximum:
        raise ValueError("invalid notification record")
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError("invalid notification record")
    return value


def contact_text(record):
    if (record.get("kind") not in {"removal", "bug", "other"}
            or not isinstance(record.get("received_at"), str)
            or not isinstance(record.get("message"), str)
            or not isinstance(record.get("target_url"), (str, type(None)))):
        raise ValueError("invalid contact record")
    # Neither the source nor the reply address is sent to Slack.
    return (f"Beta contact: {record['kind']}\nReceived: {record['received_at']}\n"
            f"Target: {record.get('target_url') or '(none)'}\n"
            f"Reply address supplied: {'yes' if record.get('reply_to') else 'no'}\n"
            f"Message:\n{record['message'][:2000]}")


def operations(home, pending):
    result = {}
    error = home / "status/reset-error.json"
    if error.exists():
        value = read_json(error)
        if set(value) != {"failed_at", "stage"} or value["stage"] not in {"prepare", "stop", "swap", "start", "ready", "finish", "restore"} or not isinstance(value["failed_at"], str):
            raise ValueError("invalid reset error")
        result["reset"] = f"Beta reset failed: {value['failed_at']} / {value['stage']}"
    watch = home / "host-state/watch-alerts.json"
    if watch.exists():
        value = read_json(watch)
        if value.get("freeze"):
            result["freeze"] = "Beta watch: writes automatically frozen"
        if value.get("stop_web"):
            result["stop_web"] = "Beta watch: web stopped"
        if value.get("counters_unavailable"):
            result["counters"] = "Beta watch: counters unavailable"
    usage = shutil.disk_usage(home)
    disk = 100 * usage.used // usage.total
    if disk >= 80:
        # Deduplicate by severity, not by every changing percentage.
        result["disk"] = "Beta disk: " + ("critical (85% or more)" if disk >= 85 else "warning (80% or more)")
    if pending >= MAX_PENDING:
        result["contact_full"] = "Beta contact spool is full; contact requests cannot be accepted"
    return result


@contextmanager
def delivery_lock(path):
    with path.open("a+b") as file:
        if os.name == "nt":
            import msvcrt
            file.seek(0)
            if not file.read(1):
                file.write(b"0")
                file.flush()
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def deliver(home, webhook, now=None):
    now = now or datetime.now(timezone.utc)
    directory = home / "contacts"
    sent = directory / "sent"
    invalid = directory / "invalid"
    if directory.is_symlink() or sent.is_symlink() or invalid.is_symlink():
        raise ValueError("invalid contact directory")
    sent.mkdir(mode=0o700, exist_ok=True)
    invalid.mkdir(mode=0o700, exist_ok=True)
    prune(sent, now)
    prune(invalid, now)
    prune(directory, now)
    pending = contact_files(directory)
    state_path = home / "host-state/notify-state.json"
    state = read_json(state_path, maximum=1024 * 1024) if state_path.exists() else {"events": {}}
    if not isinstance(state.get("events"), dict) or not isinstance(state.get("quarantined", []), list):
        raise ValueError("invalid notification state")
    ready = []
    for path in pending:
        if len(ready) >= BATCH:
            break
        try:
            text = contact_text(read_json(path))
            text.encode("utf-8")
        except (ValueError, OSError, TypeError):
            path.replace(invalid / path.name)
            print("dem-beta notify: invalid contact record quarantined")
            continue
        ready.append((path, text))
    events = operations(home, len(contact_files(directory)))
    quarantined = contact_files(invalid)
    names = {path.name for path in quarantined}
    announced = set(state.get("quarantined", [])) & names
    unseen = names - announced
    if unseen:
        # Keep the event discoverable after a failed delivery or process exit.
        # A new set of files is a new event, without sending their contents.
        batch = hashlib.sha256("\n".join(sorted(unseen)).encode()).hexdigest()
        events["contact_invalid"] = f"Beta contact: invalid records quarantined; count={len(unseen)}; batch={batch}"
    remembered = {key: value for key, value in state["events"].items() if key in events}
    def save_state():
        atomic_json(state_path, {"events": remembered, "quarantined": sorted(announced)})
    for kind, text in events.items():
        digest = hashlib.sha256(text.encode()).hexdigest()
        if remembered.get(kind) != digest:
            if not post(webhook, payload(text)):
                save_state()
                return False
            remembered[kind] = digest
            if kind == "contact_invalid":
                announced.update(names)
            save_state()
    save_state()
    for path, text in ready:
        if not post(webhook, payload(text)):
            return False
        path.replace(sent / path.name)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("home", type=Path)
    parser.add_argument("--record-only", action="store_true")
    parser.add_argument("--watch", type=int, nargs=4, metavar=("DISK", "FREEZE", "STOP_WEB", "COUNTERS_UNAVAILABLE"))
    args = parser.parse_args()
    try:
        if args.watch is not None:
            disk, freeze, stop, unavailable = args.watch
            atomic_json(args.home / "host-state/watch-alerts.json",
                        dict(disk=disk, freeze=bool(freeze), stop_web=bool(stop), counters_unavailable=bool(unavailable)))
        if args.record_only:
            return 0
        webhook = os.environ.get("DEM_BETA_SLACK_WEBHOOK_URL", "")
        if not webhook:
            print("dem-beta notify: webhook is not configured; skipped")
            return 0
        with delivery_lock(args.home / "host-state/notify.lock"):
            return 0 if deliver(args.home, webhook) else 1
    except Exception:
        print("dem-beta notify: processing failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
