from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from dem.api import DemServices
from dem.db.models import Axiom, Base, Definition, Formula, Proof, Symbol, Theorem
from dem.db.seed import seed_language
from dem.db.seeds import seed_all
from dem.errors import ConflictError, FormulaValidationError, ValidationError
from dem.services.formula import compute_hash
from dem.types import SymbolTypeName, Token


@pytest.fixture
def dem():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        yield DemServices(session)
    engine.dispose()


def _colliding_symbols(dem: DemServices):
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    first = dem.symbols.register("collision", kind.id, 0, namespace="local.alpha")
    second = dem.symbols.register("collision", kind.id, 0, namespace="local.beta")
    return first, second


def test_ambiguous_short_name_requires_qualification(dem: DemServices) -> None:
    _colliding_symbols(dem)
    with pytest.raises(FormulaValidationError) as caught:
        dem.formulas.parse_text("collision")
    assert caught.value.code == "formula.ambiguous_symbol"
    with pytest.raises(ValidationError) as lookup:
        dem.symbols.get_by_name("collision")
    assert lookup.value.code == "symbol.ambiguous_name"


def test_printer_qualifies_only_ambiguous_symbols(dem: DemServices) -> None:
    first, _ = _colliding_symbols(dem)
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    solo = dem.symbols.register("solo", kind.id, 0, namespace="local.alpha")
    assert dem.formulas.print_text([Token(symbol_id=first.id)]) == "local.alpha::collision"
    assert dem.formulas.print_text([Token(symbol_id=solo.id)]) == "solo"


def test_round_trip_survives_a_name_collision(dem: DemServices) -> None:
    first, second = _colliding_symbols(dem)
    for symbol in (first, second):
        tokens = [Token(symbol_id=symbol.id)]
        rendered = dem.formulas.print_text(tokens)
        parsed, _ = dem.formulas.parse_text(rendered)
        assert parsed == tokens


def test_display_collision_across_packages_is_allowed(dem: DemServices) -> None:
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    dem.symbols.register("left", kind.id, 0, latex_template="shared", namespace="local.alpha")
    dem.symbols.register("right", kind.id, 0, latex_template="shared", namespace="local.beta")


def test_display_collision_inside_one_package_is_rejected(dem: DemServices) -> None:
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    dem.symbols.register("left", kind.id, 0, latex_template="shared", namespace="local.alpha")
    with pytest.raises(ConflictError) as caught:
        dem.symbols.register("right", kind.id, 0, latex_template="shared", namespace="local.alpha")
    assert caught.value.code == "symbol.display_collision"


def test_theorem_names_are_namespace_scoped(dem: DemServices) -> None:
    kind = dem.symbols.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value)
    symbol = dem.symbols.register("statement", kind.id, 0)
    formula = dem.formulas.register([Token(symbol_id=symbol.id)])
    first = dem.theorems.register("same", formula.id, namespace="local.alpha")
    second = dem.theorems.register("same", formula.id, namespace="local.beta")
    assert first.id != second.id
    with pytest.raises(ValidationError) as caught:
        dem.theorems.get_by_name("same")
    assert caught.value.code == "theorem.ambiguous_name"


def test_seed_public_ids_are_stable(all_seeded_session: Session) -> None:
    models = (Symbol, Formula, Axiom, Definition, Theorem, Proof)

    def public_ids():
        return {
            model.__tablename__: tuple(
                all_seeded_session.execute(
                    select(model.id, model.public_id).order_by(model.id)
                ).all()
            )
            for model in models
        }

    before = public_ids()
    seed_all(all_seeded_session)
    after = public_ids()
    assert after == before


def test_rollback_discards_namespace_and_symbol_identity_caches() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_language(session)
        session.commit()
        dem = DemServices(session)
        kind = dem.symbols.get_symbol_type_by_name(
            SymbolTypeName.FREE_PROP_VAR.value
        )
        rolled_back = dem.symbols.register(
            "rolled_back_symbol", kind.id, 0, namespace="local.rollback"
        )
        dem.formulas.register([Token(symbol_id=rolled_back.id)])
        reused_id = rolled_back.id
        stale_public_id = rolled_back.public_id
        assert reused_id in session.info["_symbol_public_id_cache"]
        assert "local.rollback" in session.info["_namespace_cache"]

        session.rollback()

        replacement = dem.symbols.register(
            "replacement_symbol", kind.id, 0, namespace="local.rollback"
        )
        assert replacement.id == reused_id
        assert replacement.public_id != stale_public_id
        formula = dem.formulas.register([Token(symbol_id=replacement.id)])
        assert formula.hash == compute_hash(
            [Token(symbol_id=replacement.id)],
            {replacement.id: replacement.public_id},
        )
    engine.dispose()
