"""Beta contact spool, deliberately independent of mathematical storage."""
from contextlib import suppress
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from threading import Lock
import tempfile
import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from webapi.beta import BetaReject, enabled, reject_response, source_key

router = APIRouter()
PENDING_LIMIT = 1000
CONTACT_PATTERN = "contact-????????T????????????Z-" + "?" * 32 + ".json"


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["removal", "bug", "other"]
    target_url: str | None = Field(default=None, max_length=500)
    message: str = Field(min_length=1, max_length=2000)
    reply_to: str | None = Field(default=None, max_length=254)

    @field_validator("target_url")
    @classmethod
    def target_prefix(cls, value):
        if value is not None and not value.startswith(("http://", "https://", "/")):
            raise ValueError("target_url must start with http://, https:// or /")
        return value

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value):
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


class ContactRuntime:
    """Single-worker, separate rate counters; failed saves spend no allowance."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = Lock()
        self.sources = {}
        self.day = None
        self.daily = 0

    def save(self, contact: Contact, host: str):
        key = source_key(host)
        with self.lock:
            now, tick = datetime.now(timezone.utc), self.clock()
            self.sources = {key: until for key, until in self.sources.items() if until > tick}
            if self.day != now.date():
                self.day, self.daily = now.date(), 0
            if key in self.sources or self.daily >= 50:
                retry = max(1, math.ceil(self.sources[key] - tick)) if key in self.sources else max(1, 86400 - (now.hour * 3600 + now.minute * 60 + now.second))
                raise BetaReject(429, "beta.rate_limited", "Contact request rate exceeded", retry)
            temporary = None
            try:
                directory = Path(os.environ["DEM_BETA_CONTACT_DIR"])
                # The installer owns directory creation and permissions.
                if not directory.is_dir() or sum(1 for p in directory.glob(CONTACT_PATTERN) if p.is_file()) >= PENDING_LIMIT:
                    raise OSError("contact spool unavailable")
                record = {"received_at": now.isoformat().replace("+00:00", "Z"),
                          **contact.model_dump(), "source": key}
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                                 prefix=".contact-", suffix=".tmp", delete=False) as output:
                    temporary = Path(output.name)
                    os.chmod(temporary, 0o600)
                    json.dump(record, output, ensure_ascii=False)
                    output.flush()
                    os.fsync(output.fileno())
                name = f"contact-{now:%Y%m%dT%H%M%S%fZ}-{uuid4().hex}.json"
                temporary.replace(directory / name)
                temporary = None
            except (KeyError, OSError, ValueError):
                raise BetaReject(503, "beta.contact_unavailable", "Contact service is unavailable") from None
            finally:
                if temporary is not None:
                    with suppress(OSError):
                        temporary.unlink(missing_ok=True)
            self.sources[key] = tick + 600
            self.daily += 1


runtime = ContactRuntime()


@router.post("/contact", include_in_schema=False)
async def contact(request: Request):
    if not enabled():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    try:
        value = Contact.model_validate(await request.json())
    except (ValueError, ValidationError):
        return JSONResponse(status_code=422, content={"code": "beta.contact_invalid", "detail": "Invalid contact fields"})
    try:
        await run_in_threadpool(runtime.save, value, (request.client.host if request.client else "unknown"))
    except BetaReject as error:
        return reject_response(error, "/contact", "contact")
    return JSONResponse(status_code=202, content={"status": "accepted"})
