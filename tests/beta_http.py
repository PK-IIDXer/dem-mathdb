"""Seed-independent ASGI request harness."""
import asyncio
import json

async def asgi_request(application, method, path, body=None, *, host="127.0.0.1", headers=None, chunks=None, raise_app_exceptions=True):
    payload = json.dumps(body).encode() if body is not None else b""
    pieces = iter(enumerate(chunks if chunks is not None else [payload]))
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "method": method, "scheme": "http", "path": path,
             "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": headers if headers is not None else [(b"host", b"test"), (b"content-type", b"application/json")],
             "server": ("test", 80), "client": (host, 1234)}
    messages = []

    async def receive():
        try:
            index, piece = next(pieces)
        except StopIteration:
            await asyncio.Event().wait()
        return {"type": "http.request", "body": piece, "more_body": chunks is not None and index < len(chunks) - 1}

    async def send(message):
        messages.append(message)

    try:
        await asyncio.wait_for(application(scope, receive, send), 30)
    except Exception:
        if raise_app_exceptions:
            raise
    start = next(m for m in messages if m["type"] == "http.response.start")
    raw = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    try:
        result = json.loads(raw) if raw else None
    except ValueError:
        result = raw.decode()
    return start["status"], result, dict(start.get("headers", []))


