from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.models.definition import Definition
from dem.db.models.inference import Axiom
from dem.db.models.language import SymbolAlias
from dem.db.models.theorem import Theorem
from dem.db.ordering import utf8_sort_key
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seeds.hilbert import seed_hilbert_core
from dem.errors import ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.services.tag import TagService
from dem.services.theorem import TheoremService
from dem.types import Token


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    seed_inference_rules(session)
    seed_hilbert_core(session)
    return session


def test_tag_get_or_create_is_idempotent_and_lists_alphabetically() -> None:
    with make_session() as session:
        tags = TagService(session)
        a = tags.get_or_create("集合論")
        b = tags.get_or_create("論理学")
        c = tags.get_or_create("aiueo")
        again = tags.get_or_create("集合論")

        assert again.id == a.id
        assert [t.name for t in tags.list_all()] == sorted(
            [a.name, b.name, c.name], key=lambda name: name.encode("utf-8")
        )


def test_tag_relationships_use_utf8_binary_name_order_with_id_tiebreaker() -> None:
    expected_by_dialect = {
        sqlite.dialect(): ["CAST(tag.name AS BLOB)", "tag.id"],
        postgresql.dialect(): ["convert_to(tag.name, 'UTF8')", "tag.id"],
    }
    for dialect, expected in expected_by_dialect.items():
        for model in (Axiom, Theorem, Definition):
            relationship = model.__mapper__.relationships["tags"]
            assert [str(clause.compile(dialect=dialect)) for clause in relationship.order_by] == expected


def test_tag_and_alias_names_use_utf8_byte_order_in_sqlite() -> None:
    with make_session() as session:
        tags = TagService(session)
        symbols = SymbolService(session)

        for name in (r"\review-tag", "日本語タグ"):
            tags.get_or_create(name)
        for alias in (r"\review-alias", "日本語別名"):
            symbols.add_alias(_phi_id(session), alias)

        listed_tags = tags.list_all()
        assert {r"\review-tag", "日本語タグ"} <= {
            tag.name for tag in listed_tags
        }
        assert [(tag.name, tag.id) for tag in listed_tags] == sorted(
            ((tag.name, tag.id) for tag in listed_tags),
            key=lambda item: (item[0].encode("utf-8"), item[1]),
        )

        listed_aliases = symbols.list_aliases()
        assert {r"\review-alias", "日本語別名"} <= {
            alias.alias for alias in listed_aliases
        }
        assert [(alias.alias, alias.id) for alias in listed_aliases] == sorted(
            ((alias.alias, alias.id) for alias in listed_aliases),
            key=lambda item: (item[0].encode("utf-8"), item[1]),
        )


def test_symbol_alias_order_compiles_for_each_dialect() -> None:
    statement = select(SymbolAlias).order_by(
        utf8_sort_key(SymbolAlias.alias), SymbolAlias.id
    )

    sqlite_sql = str(statement.compile(dialect=sqlite.dialect()))
    postgres_sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY CAST(symbol_alias.alias AS BLOB), symbol_alias.id" in sqlite_sql
    assert (
        "ORDER BY convert_to(symbol_alias.alias, 'UTF8'), symbol_alias.id"
        in postgres_sql
    )
    assert " AS BYTEA" not in postgres_sql


def test_tag_name_must_not_be_empty() -> None:
    with make_session() as session:
        tags = TagService(session)
        try:
            tags.get_or_create("   ")
            assert False, "expected ValidationError"
        except ValidationError:
            pass


def test_axiom_can_be_tagged_and_filtered_by_tag() -> None:
    with make_session() as session:
        axioms = AxiomService(session)
        tags = TagService(session)
        k_axiom = axioms.get_by_name("hilbert_k")
        s_axiom = axioms.get_by_name("hilbert_s")

        set_tag = tags.get_or_create("命題論理")
        tags.attach("axiom", k_axiom.id, set_tag.id)

        tagged = {a.id for a in axioms.list_axioms(tag_ids=[set_tag.id])}
        assert tagged == {k_axiom.id}
        assert s_axiom.id not in tagged

        assert [t.name for t in tags.list_for("axiom", k_axiom.id)] == ["命題論理"]

        tags.detach("axiom", k_axiom.id, set_tag.id)
        assert tags.list_for("axiom", k_axiom.id) == []


def test_axiom_description_is_set_and_searchable() -> None:
    with make_session() as session:
        axioms = AxiomService(session)
        k_axiom = axioms.get_by_name("hilbert_k")

        updated = axioms.set_description(k_axiom.id, "  常に真である公理  ")
        assert updated.description == "常に真である公理"

        found = axioms.list_axioms(search="常に真")
        assert [a.id for a in found] == [k_axiom.id]

        assert axioms.list_axioms(search="nonexistent term") == []

        cleared = axioms.set_description(k_axiom.id, "")
        assert cleared.description is None


def test_theorem_description_and_search_and_tag_filter() -> None:
    with make_session() as session:
        formulas = FormulaService(session)
        theorems = TheoremService(session)
        tags = TagService(session)

        phi_formula = formulas.register([Token(symbol_id=_phi_id(session))])
        theorem = theorems.register(
            name="search_test_theorem",
            conclusion_formula_id=phi_formula.id,
            description="これはテスト用の定理です",
        )

        assert theorem.description == "これはテスト用の定理です"
        assert [t.id for t in theorems.list_all(search="テスト用")] == [theorem.id]

        tag = tags.get_or_create("テストタグ")
        tags.attach("theorem", theorem.id, tag.id)
        assert [t.id for t in theorems.list_all(tag_ids=[tag.id])] == [theorem.id]


def _phi_id(session: Session) -> int:
    return SymbolService(session).get_by_name("φ").id
