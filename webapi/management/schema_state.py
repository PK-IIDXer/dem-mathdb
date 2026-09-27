"""Pure workspace schema-state transitions and persisted error encoding."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime


READY = "ready"
UPGRADING = "upgrading"
UPGRADE_BLOCKED = "upgrade_blocked"


@dataclass(frozen=True)
class SchemaFailure:
    code: str
    message: str
    formula_id: int | None = None

    def encode(self) -> str:
        return json.dumps(
            {
                "code": self.code,
                "formula_id": self.formula_id,
                "message": self.message,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class SchemaStateUpdate:
    state: str
    revision: str | None
    error: str | None
    checked_at: datetime


def ready_update(revision: str) -> SchemaStateUpdate:
    return SchemaStateUpdate(READY, revision, None, datetime.now(UTC))


def upgrading_update(revision: str | None) -> SchemaStateUpdate:
    return SchemaStateUpdate(UPGRADING, revision, None, datetime.now(UTC))


def blocked_update(
    revision: str | None, failure: SchemaFailure
) -> SchemaStateUpdate:
    return SchemaStateUpdate(
        UPGRADE_BLOCKED,
        revision,
        failure.encode(),
        datetime.now(UTC),
    )
