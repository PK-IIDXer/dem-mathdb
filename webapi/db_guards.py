"""Recognize only errors raised by DEM's installed mathematical guards."""
from dem.db.package_triggers import PUBLISHED_GUARDS
from dem.db.triggers import (
    TIER_A_TRIGGER_SPECS,
    _sqlite_guard,
    _SQLITE_TIER_B_IMMUTABILITY_GUARDS,
)


MESSAGES = {message: name for name, (_, message) in _SQLITE_TIER_B_IMMUTABILITY_GUARDS.items()}
MESSAGES.update({_sqlite_guard(spec)[1]: spec.name for spec in TIER_A_TRIGGER_SPECS})
MESSAGES["formula is not well-formed"] = "formula_wellformed"
MESSAGES.update({f"published release is immutable: {guard.name}": guard.name for guard in PUBLISHED_GUARDS})


def known_guard(exc):
    original = exc.orig
    # Neither generic constraint violations nor arbitrary text containing a
    # message qualify. PostgreSQL context/SQL is never returned to the caller.
    if getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_TRIGGER":
        return MESSAGES.get(str(original))
    if getattr(original, "sqlstate", None) == "23514" or getattr(original, "pgcode", None) == "23514":
        return MESSAGES.get(getattr(getattr(original, "diag", None), "message_primary", None))
    return None
