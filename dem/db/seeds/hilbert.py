from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.inference import Axiom, AxiomSystem, AxiomSystemMember
from dem.db.models.language import Formula, Symbol
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seed_labels import (
    axiom_formula_remark,
    axiom_lookup_names,
    axiom_system_lookup_names,
    seed_axiom_name,
    seed_axiom_system_name,
)
from dem.errors import ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.db.seeds._variable_pool import SeedSymbolService as SymbolService
from dem.types import SymbolTypeName, Token


HILBERT_CORE_AXIOM_SYSTEM_NAME = "hilbert_core"
HILBERT_CLASSICAL_AXIOM_SYSTEM_NAME = "hilbert_classical"

HILBERT_CORE_AXIOM_NAMES = (
    "hilbert_k",
    "hilbert_s",
    "hilbert_forall_elim",
    "hilbert_forall_distribution",
    "hilbert_eq_refl",
    "hilbert_eq_subst",
    # φ → ∀x.φ, with φ of arity 0 so it cannot mention the bound variable.
    # Vacuous generalization: an ordinary predicate-calculus axiom, and the one
    # `HilbertToolkit._ks_lift()` needs to push a ⇒introduction across a
    # Gen step. It therefore has to be in the core for `expand_implication_intro`
    # -- the elimination procedure that keeps ImpIntro at Tier 2 -- to exist at
    # all.
    "hilbert_forall_const_intro",
)

HILBERT_CLASSICAL_AXIOM_NAMES = (
    "hilbert_peirce",
)


@dataclass(frozen=True)
class HilbertSeedSummary:
    core_axiom_names: tuple[str, ...]
    classical_axiom_names: tuple[str, ...]


def seed_hilbert_core(session: Session) -> HilbertSeedSummary:
    """Seed the minimal Hilbert-style axiom schemas used by the proof kernel."""

    seeder = _HilbertSeeder(session)
    seeder.seed()
    return HilbertSeedSummary(
        core_axiom_names=HILBERT_CORE_AXIOM_NAMES,
        classical_axiom_names=HILBERT_CLASSICAL_AXIOM_NAMES,
    )


class _HilbertSeeder:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.symbols = SymbolService(session)
        self.formulas = FormulaService(session)
        self.axioms = AxiomService(session)

        self.imp_: Symbol
        self.forall_: Symbol
        self.eq_: Symbol
        self.phi: Symbol
        self.psi: Symbol
        self.chi: Symbol
        self.phi1: Symbol
        self.psi1: Symbol
        self.x: Symbol
        self.y: Symbol
        self.t: Symbol

    def seed(self) -> None:
        self._load_symbols()
        axioms = self._seed_axioms()
        self._seed_axiom_systems(axioms)

    def _load_symbols(self) -> None:
        self.imp_ = self.symbols.get_by_role("implication")
        self.forall_ = self.symbols.get_by_role("universal_quantifier")
        self.eq_ = self.symbols.get_by_role("equality")

        self.phi = self._ensure_symbol("φ", SymbolTypeName.FREE_PROP_VAR, 0)
        self.psi = self._ensure_symbol("ψ", SymbolTypeName.FREE_PROP_VAR, 0)
        self.chi = self._ensure_symbol("χ", SymbolTypeName.FREE_PROP_VAR, 0)
        self.phi1 = self._ensure_symbol("φ¹", SymbolTypeName.FREE_PROP_VAR, 1)
        self.psi1 = self._ensure_symbol("ψ¹", SymbolTypeName.FREE_PROP_VAR, 1)
        self.x = self._ensure_symbol("x", SymbolTypeName.FREE_TERM_VAR, 0)
        self.y = self._ensure_symbol("y", SymbolTypeName.FREE_TERM_VAR, 0)
        self.t = self._ensure_symbol("t", SymbolTypeName.FREE_TERM_VAR, 0)

    def _ensure_symbol(
        self,
        name: str,
        symbol_type_name: SymbolTypeName,
        arity: int,
    ) -> Symbol:
        if symbol_type_name == SymbolTypeName.FREE_TERM_VAR:
            from dem.db.seeds._variable_pool import ensure_variable
            return ensure_variable(self.session, name)
        existing = self.session.scalar(select(Symbol).where(Symbol.name == name))
        if existing is not None:
            if existing.symbol_type.name != symbol_type_name.value or existing.arity != arity:
                raise ValidationError(f"existing symbol {name!r} does not match Hilbert seed shape")
            return existing

        symbol_type = self.symbols.get_symbol_type_by_name(symbol_type_name.value)
        return self.symbols.register(name=name, symbol_type_id=symbol_type.id, arity=arity)

    def _seed_axioms(self) -> dict[str, Axiom]:
        phi = self.atom(self.phi)
        psi = self.atom(self.psi)
        chi = self.atom(self.chi)
        phi_to_psi = self.imp(phi, psi)
        psi_to_chi = self.imp(psi, chi)
        phi_to_psi_to_chi = self.imp(phi, psi_to_chi)
        phi_to_chi = self.imp(phi, chi)
        forall_phi1 = self.forall(self.prop1_bound(self.phi1))
        forall_psi1 = self.forall(self.prop1_bound(self.psi1))
        phi1_t = self.prop1(self.phi1, self.t)
        eq_x_y = self.eq(self.term(self.x), self.term(self.y))
        eq_x_x = self.eq(self.term(self.x), self.term(self.x))
        phi1_x = self.prop1(self.phi1, self.x)
        phi1_y = self.prop1(self.phi1, self.y)
        forall_imp_phi1_psi1 = self.forall(
            self.imp(self.prop1_bound(self.phi1), self.prop1_bound(self.psi1))
        )

        axiom_tokens = {
            "hilbert_k": self.imp(phi, self.imp(psi, phi)),
            "hilbert_s": self.imp(
                phi_to_psi_to_chi,
                self.imp(phi_to_psi, phi_to_chi),
            ),
            "hilbert_forall_elim": self.imp(forall_phi1, phi1_t),
            "hilbert_forall_distribution": self.imp(
                forall_imp_phi1_psi1,
                self.imp(forall_phi1, forall_psi1),
            ),
            "hilbert_eq_refl": eq_x_x,
            "hilbert_eq_subst": self.imp(eq_x_y, self.imp(phi1_x, phi1_y)),
            "hilbert_forall_const_intro": self.imp(phi, self.forall(phi)),
            "hilbert_peirce": self.imp(self.imp(phi_to_psi, phi), phi),
        }

        return {
            name: self._get_or_create_axiom(name, tokens)
            for name, tokens in axiom_tokens.items()
        }

    def _seed_axiom_systems(self, axioms: dict[str, Axiom]) -> None:
        core = self._get_or_create_axiom_system(
            HILBERT_CORE_AXIOM_SYSTEM_NAME,
            "最小限のヒルベルト流コア公理スキーマ。",
        )
        classical = self._get_or_create_axiom_system(
            HILBERT_CLASSICAL_AXIOM_SYSTEM_NAME,
            "ヒルベルト流コアに古典含意論理を加えた公理系。",
        )

        for name in HILBERT_CORE_AXIOM_NAMES:
            self._ensure_system_member(core, axioms[name])
            self._ensure_system_member(classical, axioms[name])
        for name in HILBERT_CLASSICAL_AXIOM_NAMES:
            self._ensure_system_member(classical, axioms[name])

    def _get_or_create_axiom(
        self,
        name: str,
        tokens: list[Token],
    ) -> Axiom:
        display_name = seed_axiom_name(name)
        formula = self._formula(tokens, remarks=axiom_formula_remark(name))
        existing = self.session.scalar(
            select(Axiom).where(Axiom.name.in_(axiom_lookup_names(name)))
        )
        if existing is not None:
            if existing.formula_id != formula.id:
                raise ValidationError(f"existing axiom {name!r} has a different formula")
            existing.name = display_name
            existing.remarks = "ヒルベルト体系のシード"
            self.session.flush()
            return existing
        return self.axioms.register(
            name=display_name,
            formula_id=formula.id,
            remarks="ヒルベルト体系のシード",
        )

    def _get_or_create_axiom_system(self, name: str, remarks: str) -> AxiomSystem:
        display_name = seed_axiom_system_name(name)
        existing = self.session.scalar(
            select(AxiomSystem).where(AxiomSystem.name.in_(axiom_system_lookup_names(name)))
        )
        if existing is not None:
            existing.name = display_name
            existing.remarks = remarks
            self.session.flush()
            return existing
        return self.axioms.register_system(name=display_name, remarks=remarks)

    def _ensure_system_member(self, system: AxiomSystem, axiom: Axiom) -> None:
        existing = self.session.get(
            AxiomSystemMember,
            {"axiom_system_id": system.id, "axiom_id": axiom.id},
        )
        if existing is None:
            self.session.add(AxiomSystemMember(axiom_system_id=system.id, axiom_id=axiom.id))
            self.session.flush()

    def _formula(self, tokens: list[Token], remarks: str | None = None) -> Formula:
        formula = self.formulas.register(tokens, remarks=remarks)
        if remarks is not None and formula.remarks != remarks:
            formula.remarks = remarks
        return formula

    def atom(self, symbol: Symbol) -> list[Token]:
        return [Token(symbol_id=symbol.id)]

    def term(self, symbol: Symbol) -> list[Token]:
        return [Token(symbol_id=symbol.id)]

    def prop1(self, prop_symbol: Symbol, term_symbol: Symbol) -> list[Token]:
        return [Token(symbol_id=prop_symbol.id), Token(symbol_id=term_symbol.id)]

    def prop1_bound(self, prop_symbol: Symbol) -> list[Token]:
        return [Token(symbol_id=prop_symbol.id), Token(de_bruijn_index=0)]

    def app(self, symbol: Symbol, *args: list[Token]) -> list[Token]:
        tokens = [Token(symbol_id=symbol.id)]
        for arg in args:
            tokens.extend(arg)
        return tokens

    def imp(self, left: list[Token], right: list[Token]) -> list[Token]:
        return self.app(self.imp_, left, right)

    def forall(self, body: list[Token]) -> list[Token]:
        return self.app(self.forall_, body)

    def eq(self, left: list[Token], right: list[Token]) -> list[Token]:
        return self.app(self.eq_, left, right)


def _database_url() -> str:
    return os.environ.get("DEM_DATABASE_URL", "sqlite:///./dem_dev.db")


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def main() -> None:
    from dem.api import DemApi

    url = _database_url()
    connect_args = {"check_same_thread": False} if _is_sqlite(url) else {}
    api = DemApi.from_url(url, connect_args=connect_args)

    if _is_sqlite(url):
        api.create_schema()

    with api.transaction() as dem:
        seed_language(dem.session)
        seed_inference_rules(dem.session)
        summary = seed_hilbert_core(dem.session)

    print(
        "Seeded Hilbert core: "
        f"{len(summary.core_axiom_names)} core axioms, "
        f"{len(summary.classical_axiom_names)} classical axioms."
    )


if __name__ == "__main__":
    main()
