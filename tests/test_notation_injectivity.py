"""Verify the complete seed and upgrade display metadata without changing logic."""
from collections import defaultdict
import hashlib

from sqlalchemy import func, inspect, select

from dem.db.models.language import FormulaToken, Symbol
from dem.db.seeds import refresh_symbol_display
from dem.db.seeds._notation import validate_display_shapes
from dem.services.symbol import symbol_shape

def collisions(session):
    groups = defaultdict(list)
    for symbol in session.scalars(select(Symbol)):
        groups[symbol_shape(symbol)].append(symbol.name)
    return [names for names in groups.values() if len(names) > 1]


def test_seeded_symbol_usage_counts_match_formula_tokens(seeded_session):
    expected = dict(
        seeded_session.execute(
            select(
                FormulaToken.symbol_id,
                func.count(func.distinct(FormulaToken.formula_id)),
            )
            .where(FormulaToken.symbol_id.is_not(None))
            .group_by(FormulaToken.symbol_id)
        ).all()
    )
    actual = {
        symbol.id: symbol.usage_count
        for symbol in seeded_session.scalars(select(Symbol))
    }
    assert actual == {symbol_id: expected.get(symbol_id, 0) for symbol_id in actual}


def logical_digest(session):
    digest = hashlib.sha256()
    connection = session.connection()
    inspector = inspect(connection)
    quote = connection.dialect.identifier_preparer.quote
    for table in ("formula", "formula_token", "proof", "proof_step",
                  "proof_step_arg", "proof_step_subst_term", "proof_step_subst_prop",
                  "proof_step_subst_prop_param"):
        primary_key = inspector.get_pk_constraint(table)["constrained_columns"]
        assert primary_key
        order_by = ", ".join(quote(column) for column in primary_key)
        query = f"SELECT * FROM {quote(table)} ORDER BY {order_by}"
        for row in connection.exec_driver_sql(query):
            digest.update(repr(tuple(row)).encode())
    return digest.hexdigest()


def test_complete_seed_has_no_display_collisions(seeded_session):
    assert not collisions(seeded_session)
    validate_display_shapes(seeded_session)
