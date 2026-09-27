from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from dem.db.base import Base
from dem.db.engine import make_engine, make_session_factory
from dem.db.seed import seed_inference_rules, seed_language
from dem.services.axiom import AxiomService
from dem.services.definition import DefinitionService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.services.tag import TagService
from dem.services.theorem import TheoremService


class DemServices:
    """Service bundle bound to one SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.symbols = SymbolService(session)
        self.formulas = FormulaService(session, authoring_via="manual")
        self.axioms = AxiomService(session)
        self.theorems = TheoremService(session, authoring_via="manual")
        self.proofs = ProofService(session, authoring_via="manual")
        self.definitions = DefinitionService(session, authoring_via="manual")
        self.tags = TagService(session)


class DemApi:
    """Thin application boundary for schema setup, seeding, and service sessions."""

    def __init__(
        self,
        engine: Engine,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory or make_session_factory(engine)

    @classmethod
    def from_url(cls, url: str, **engine_kwargs: object) -> DemApi:
        return cls(make_engine(url, **engine_kwargs))

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def seed_core(
        self,
        include_inference_rules: bool = True,
        include_hilbert_core: bool = True,
    ) -> None:
        with self.transaction() as dem:
            seed_language(dem.session)
            if include_inference_rules:
                seed_inference_rules(dem.session)
            if include_hilbert_core:
                from dem.db.seeds.hilbert import seed_hilbert_core

                seed_hilbert_core(dem.session)

    def initialize_database(
        self,
        seed: bool = True,
        include_inference_rules: bool = True,
        include_hilbert_core: bool = True,
    ) -> None:
        self.create_schema()
        if seed:
            self.seed_core(
                include_inference_rules=include_inference_rules,
                include_hilbert_core=include_hilbert_core,
            )

    @contextmanager
    def session(self) -> Iterator[DemServices]:
        with self.session_factory() as session:
            yield DemServices(session)

    @contextmanager
    def transaction(self) -> Iterator[DemServices]:
        with self.session_factory() as session:
            with session.begin():
                yield DemServices(session)
