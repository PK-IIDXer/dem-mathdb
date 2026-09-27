from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dem.db.models.language import Formula, FormulaToken


def test_public_hash_replaces_local_hash_one_to_one(
    all_seeded_session: Session,
) -> None:
    pairs: set[tuple[str, str]] = set()
    current_formula_id = None
    legacy_parts: list[str] = []
    current_hash = ""
    rows = all_seeded_session.execute(
        select(
            FormulaToken.formula_id,
            FormulaToken.symbol_id,
            FormulaToken.de_bruijn_index,
            Formula.hash,
        )
        .join(Formula, Formula.id == FormulaToken.formula_id)
        .order_by(FormulaToken.formula_id, FormulaToken.position)
        .execution_options(yield_per=10_000)
    )
    for formula_id, symbol_id, bound_index, formula_hash in rows:
        if current_formula_id is not None and formula_id != current_formula_id:
            legacy_hash = hashlib.sha256("".join(legacy_parts).encode()).hexdigest()
            pairs.add((legacy_hash, current_hash))
            legacy_parts = []
        current_formula_id = formula_id
        current_hash = formula_hash
        legacy_parts.append(
            f"S{symbol_id};" if symbol_id is not None else f"B{bound_index};"
        )
    if current_formula_id is not None:
        pairs.add(
            (hashlib.sha256("".join(legacy_parts).encode()).hexdigest(), current_hash)
        )

    formula_count = all_seeded_session.scalar(select(func.count()).select_from(Formula))
    assert formula_count == 8
    assert len({old for old, _new in pairs}) == formula_count
    assert len({_new for _old, _new in pairs}) == formula_count
