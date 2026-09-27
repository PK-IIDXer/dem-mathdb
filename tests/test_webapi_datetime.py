from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from webapi.schemas import TagOut


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 9, 14, 12, 24, 15), "2026-09-14T12:24:15Z"),
        (
            datetime(2026, 9, 14, 21, 24, 15, tzinfo=timezone(timedelta(hours=9))),
            "2026-09-14T12:24:15Z",
        ),
        (
            datetime(2026, 9, 14, 21, 24, 15, 285357, tzinfo=timezone(timedelta(hours=9))),
            "2026-09-14T12:24:15.285357Z",
        ),
    ],
)
def test_api_datetime_is_serialized_as_utc(value: datetime, expected: str) -> None:
    output = TagOut(id=1, name="time", created_at=value)
    assert output.model_dump(mode="json")["created_at"] == expected
