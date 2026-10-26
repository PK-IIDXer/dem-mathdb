"""Contact intake must work without a mathematical database or its write state."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from webapi import beta, contact, deps
from webapi.main import app
from beta_http import asgi_request

SEED_DATABASE = "sqlite"


@pytest.fixture
def intake(tmp_path, monkeypatch):
    monkeypatch.setenv("DEM_BETA", "1")
    monkeypatch.setenv("DEM_BETA_CONTACT_DIR", str(tmp_path))
    monkeypatch.delenv("DEM_READ_ONLY", raising=False)
    monkeypatch.delenv("DEM_BETA_FLAG_DIR", raising=False)
    tick = [0.0]
    monkeypatch.setattr(contact, "runtime", contact.ContactRuntime(lambda: tick[0]))
    monkeypatch.setattr(beta, "runtime", beta.Runtime())
    def forbidden(*args, **kwargs):
        raise AssertionError("contact must not use mathematical admission or a database")
    monkeypatch.setattr(beta.runtime, "enter_async", forbidden)
    monkeypatch.setattr(deps, "get_workspace_request_context", forbidden)
    monkeypatch.setattr(beta.runtime, "is_full", forbidden)
    def send(body=None, host="192.0.2.1", **kwargs):
        return asyncio.run(asgi_request(app, "POST", "/contact", body if body is not None else {"kind": "other", "message": "hello"}, host=host, **kwargs))
    return tmp_path, send, tick


@pytest.mark.parametrize("kind", ["removal", "bug", "other"])
def test_contact_accepts_and_atomically_saves(intake, kind):
    directory, send, _ = intake
    body = dict(kind=kind, target_url="/theorems/example", message="削除をお願いします", reply_to="optional@example.invalid")
    assert send(body, host="2001:db8:12:34::1")[:2] == (202, {"status": "accepted"})
    paths = list(directory.iterdir())
    assert len(paths) == 1 and paths[0].suffix == ".json"
    value = json.loads(paths[0].read_text(encoding="utf-8"))
    assert value == {**body, "source": "2001:db8:12:34::/64", "received_at": value["received_at"]}
    assert datetime.fromisoformat(value["received_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    assert not list(directory.glob("*.tmp"))


@pytest.mark.parametrize("change", [
    {"kind": "invalid"}, {"kind": 1}, {"message": ""}, {"message": " "}, {"message": "x" * 2001},
    {"message": None}, {"message": 123}, {"target_url": "javascript:alert(1)"}, {"target_url": "ftp://host"},
    {"target_url": "x" * 501}, {"target_url": "/" + "x" * 500}, {"target_url": 12},
    {"reply_to": "x" * 255}, {"reply_to": []}, {"extra": True},
])
def test_contact_rejects_invalid_fields_without_saving(intake, change):
    directory, send, _ = intake
    status, value, _ = send({"kind": "bug", "message": "valid", **change})
    assert status == 422 and value["code"] == "beta.contact_invalid"
    assert not list(directory.iterdir())


@pytest.mark.parametrize("url", [None, "/", "https://example.invalid/path", "http://example.invalid/path", "/" + "x" * 499])
def test_contact_exact_boundaries_and_optional_fields(intake, url):
    directory, send, _ = intake
    assert send(dict(kind="bug", message="字" * 2000, target_url=url, reply_to="x" * 254))[0] == 202
    saved = json.loads(next(directory.glob("*.json")).read_text(encoding="utf-8"))
    assert len(saved["message"]) == 2000 and len(saved["reply_to"]) == 254


def test_contact_missing_optional_fields_and_malformed_json(intake):
    directory, send, _ = intake
    assert send(chunks=[b"{"])[0] == 422
    assert send()[0] == 202
    saved = json.loads(next(directory.glob("*.json")).read_text())
    assert saved["target_url"] is None and saved["reply_to"] is None


def test_contact_separate_source_and_daily_limits(intake):
    directory, send, tick = intake
    assert send()[0] == 202
    status, value, headers = send()
    assert status == 429 and value["code"] == "beta.rate_limited" and int(headers[b"retry-after"]) >= 600
    tick[0] = 599
    assert send()[0] == 429
    tick[0] = 600
    assert send()[0] == 202
    for index in range(48):
        assert send(host=f"198.51.100.{index}")[0] == 202
    assert send(host="203.0.113.1")[0] == 429
    assert len(list(directory.glob("*.json"))) == 50
    assert beta.runtime.clients == {}  # No read/write/heavy tokens spent.


def test_contact_ipv6_source_groups_share_allowance(intake):
    _, send, _ = intake
    assert send(host="2001:db8::1")[0] == 202
    assert send(host="2001:db8::2")[0] == 429
    assert send(host="2001:db8:0:1::1")[0] == 202


def test_contact_daily_limit_resets_at_utc_day_boundary(intake, monkeypatch):
    _, send, tick = intake
    current = [datetime(2026, 10, 23, 23, 59, tzinfo=timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls, tz):
            return current[0]
    monkeypatch.setattr(contact, "datetime", Clock)
    contact.runtime.day, contact.runtime.daily = current[0].date(), 50
    assert send()[0] == 429
    current[0] += timedelta(minutes=1)
    tick[0] += 60
    assert send()[0] == 202 and contact.runtime.daily == 1


def test_concurrent_contact_requests_do_not_bypass_source_limit(intake):
    directory, _, _ = intake
    async def parallel():
        return await asyncio.gather(*(asgi_request(app, "POST", "/contact", {"kind": "bug", "message": "same source"}) for _ in range(8)))
    statuses = [result[0] for result in asyncio.run(parallel())]
    assert statuses.count(202) == 1 and statuses.count(429) == 7
    assert len(list(directory.glob("*.json"))) == 1


def test_contact_works_during_maintenance_full_and_read_only(intake, monkeypatch, tmp_path):
    _, send, _ = intake
    flags = tmp_path / "flags"
    flags.mkdir()
    (flags / "read_only").touch()
    monkeypatch.setenv("DEM_BETA_FLAG_DIR", str(flags))
    monkeypatch.setenv("DEM_READ_ONLY", "1")
    assert send()[0] == 202


@pytest.mark.parametrize("readonly", [False, True])
def test_contact_disabled_is_404_before_validation(intake, monkeypatch, readonly):
    directory, send, _ = intake
    monkeypatch.delenv("DEM_BETA")
    monkeypatch.setenv("DEM_READ_ONLY", str(int(readonly)))
    assert send({"unexpected": "field"})[:2] == (404, {"detail": "Not Found"})
    assert not list(directory.iterdir())


@pytest.mark.parametrize("failure", ["missing", "file", "rename"])
def test_contact_storage_failure_is_generic_503_and_retryable(intake, monkeypatch, failure):
    directory, send, _ = intake
    if failure == "missing":
        monkeypatch.delenv("DEM_BETA_CONTACT_DIR")
    elif failure == "file":
        dest = directory / "not-a-directory"
        dest.touch()
        monkeypatch.setenv("DEM_BETA_CONTACT_DIR", str(dest))
    else:
        def broken(*args):
            raise OSError("sensitive internal storage information")
        monkeypatch.setattr(Path, "replace", broken)
    status, value, _ = send()
    assert status == 503 and value["code"] == "beta.contact_unavailable"
    assert "sensitive" not in str(value) and str(directory) not in str(value)
    assert contact.runtime.daily == 0 and not contact.runtime.sources
    assert not list(directory.glob("*.json")) and not list(directory.glob("*.tmp"))


def test_contact_pending_cap_and_body_limit(intake, monkeypatch):
    directory, send, tick = intake
    monkeypatch.setattr(contact, "PENDING_LIMIT", 1)
    assert send()[0] == 202
    tick[0] += 600
    assert send()[0] == 503
    assert len(list(directory.glob("*.json"))) == 1
    status, value, _ = send(chunks=[b"a" * (beta.Limits().body_bytes + 1)])
    assert status == 413 and value["code"] == "beta.body_too_large"
