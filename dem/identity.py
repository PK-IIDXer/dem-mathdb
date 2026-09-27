from __future__ import annotations

import re
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.errors import ValidationError


PUBLIC_ID_NAMESPACE = UUID("a5643d59-43f3-5ce2-9c31-633b24415486")
DEFAULT_NAMESPACE_NAME = "dem.foundation.logic"
_NAMESPACE_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+){1,4}$")


def new_public_id() -> str:
    return str(uuid4())


def deterministic_public_id(entity_kind: str, key: str) -> str:
    return str(uuid5(PUBLIC_ID_NAMESPACE, f"{entity_kind}::{key}"))


def public_id_from_key(entity_kind: str, key: str) -> str:
    """Return the public ID for an explicit birth key ``<namespace>::<name>``.

    A public ID is fixed when an entity is created and never recomputed from
    its current namespace (seed-package-spec §4.1, §4.2).  Foundation data
    that moves an entity to another namespace names the key the entity was
    born with, so its public ID and every formula hash that depends on it stay
    the same.  Only seed data and package import may pass such a key; the REST
    API never does, so a request cannot claim another package's identity.
    """
    namespace, separator, name = key.partition("::")
    if not separator or not name or name != name.strip():
        raise ValueError("public ID key must be '<namespace>::<name>'")
    validate_namespace_name(namespace)
    return deterministic_public_id(entity_kind, key)


def new_entity_public_id(
    entity_kind: str, namespace: str, name: str, key: str | None
) -> str:
    """The public ID of a new row: from its explicit birth key when one is
    given (seed data and package import only), otherwise from the namespace
    and name it is created with."""
    if key is None:
        return deterministic_public_id(entity_kind, f"{namespace}::{name}")
    try:
        return public_id_from_key(entity_kind, key)
    except ValueError as exc:
        raise ValidationError(str(exc), code="identity.invalid_public_id_key") from exc


def validate_namespace_name(name: str) -> str:
    normalized = name.strip().lower()
    if normalized != name or not _NAMESPACE_RE.fullmatch(normalized):
        raise ValueError(
            "namespace must contain 2-5 lowercase alphanumeric/hyphen segments"
        )
    return normalized


def ensure_namespace(session: Session, name: str = DEFAULT_NAMESPACE_NAME):
    from dem.db.models.language import Namespace

    normalized = validate_namespace_name(name)
    cached = session.info.setdefault("_namespace_cache", {}).get(normalized)
    if cached is not None:
        return cached
    row = session.scalar(select(Namespace).where(Namespace.name == normalized))
    if row is None:
        parent = None
        parent_name = normalized.rpartition(".")[0]
        if "." in parent_name:
            parent = ensure_namespace(session, parent_name)
        row = Namespace(name=normalized, parent_id=parent.id if parent else None)
        session.add(row)
        session.flush()
    session.info["_namespace_cache"][normalized] = row
    return row
