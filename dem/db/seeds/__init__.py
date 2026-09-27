"""Public A-only seed orchestration.

The public seed deliberately contains only the generic language, the three
kernel inference rules, and the eight reviewed Hilbert schemas. It registers
no derived theorem or proof corpus.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seeds.hilbert import (
    HILBERT_CLASSICAL_AXIOM_NAMES,
    HILBERT_CLASSICAL_AXIOM_SYSTEM_NAME,
    HILBERT_CORE_AXIOM_NAMES,
    HILBERT_CORE_AXIOM_SYSTEM_NAME,
    seed_hilbert_core,
)

__all__ = [
    "PublicSeedSummary",
    "refresh_symbol_display",
    "refresh_symbol_usage_counts",
    "seed_all",
]


@dataclass(frozen=True)
class PublicSeedSummary:
    axiom_names: tuple[str, ...]
    axiom_system_names: tuple[str, ...]
    theorem_names: tuple[str, ...] = ()


def refresh_symbol_usage_counts(session: Session) -> None:
    """Recalculate completion-ranking counts on a populated database."""
    from dem.services.symbol import SymbolService

    SymbolService(session).recalculate_usage_counts()


def refresh_symbol_display(session: Session) -> None:
    """Apply content-neutral display metadata and built-in aliases."""
    from dem.db.seeds._aliases import apply_builtin_aliases
    from dem.db.seeds._notation import apply_symbol_notation, validate_display_shapes

    apply_symbol_notation(session)
    validate_display_shapes(session)
    apply_builtin_aliases(session)


def seed_all(session: Session) -> PublicSeedSummary:
    """Create the complete public A-only seed."""
    seed_language(session)
    seed_inference_rules(session)
    seed_hilbert_core(session)
    refresh_symbol_display(session)
    refresh_symbol_usage_counts(session)
    return PublicSeedSummary(
        axiom_names=(*HILBERT_CORE_AXIOM_NAMES, *HILBERT_CLASSICAL_AXIOM_NAMES),
        axiom_system_names=(
            HILBERT_CORE_AXIOM_SYSTEM_NAME,
            HILBERT_CLASSICAL_AXIOM_SYSTEM_NAME,
        ),
    )
