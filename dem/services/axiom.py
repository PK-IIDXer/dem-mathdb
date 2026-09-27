from __future__ import annotations

import json
from datetime import datetime
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from dem.db.models.definition import Definition
from dem.db.models.foundation_records import AxiomRecord
from dem.db.models.inference import Axiom, AxiomSystem, AxiomSystemMember
from dem.db.models.language import Formula
from dem.db.seed_labels import axiom_lookup_names, axiom_system_lookup_names
from dem.db.models.tag import AxiomTag
from dem.db.models.theorem import Proof, ProofStep, Theorem
from dem.errors import ConflictError, NotFoundError, ValidationError
from dem.identity import DEFAULT_NAMESPACE_NAME, ensure_namespace, new_entity_public_id
from dem.services.used_axioms import (
    load_definition_axioms,
    load_proof_edges,
    used_axiom_ids_by_proof,
)
from dem.types import FormulaTypeName


class AxiomService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def register(
        self,
        name: str,
        formula_id: int,
        description: str | None = None,
        remarks: str | None = None,
        namespace: str = DEFAULT_NAMESPACE_NAME,
        public_id_key: str | None = None,
    ) -> Axiom:
        """Register a primitive axiom.

        ``public_id_key`` is the seed / package-import path for keeping an
        axiom's birth identity (``dem.identity.public_id_from_key``); the REST
        API never passes it.
        """
        return self._register(
            name=name,
            formula_id=formula_id,
            origin_kind="primitive",
            definition_id=None,
            description=description,
            remarks=remarks,
            namespace=namespace,
            public_id_key=public_id_key,
        )

    def get(self, id: int) -> Axiom:
        row = self._session.get(Axiom, id)
        if row is None:
            raise NotFoundError("Axiom", id)
        return row

    def get_by_public_id(self, public_id: str) -> Axiom:
        row = self._session.scalar(select(Axiom).where(Axiom.public_id == public_id))
        if row is None:
            raise NotFoundError("Axiom", public_id)
        return row

    def get_by_name(self, name: str) -> Axiom:
        row = self._session.scalar(select(Axiom).where(Axiom.name.in_(axiom_lookup_names(name))))
        if row is None:
            raise NotFoundError("Axiom", name)
        return row

    def list_axioms(
        self, search: str | None = None, tag_ids: list[int] | None = None
    ) -> list[Axiom]:
        stmt = select(Axiom).order_by(Axiom.id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Axiom.name.ilike(like), Axiom.description.ilike(like)))
        if tag_ids:
            stmt = (
                stmt.join(AxiomTag, AxiomTag.axiom_id == Axiom.id)
                .where(AxiomTag.tag_id.in_(tag_ids))
                .distinct()
            )
        return list(self._session.scalars(stmt))

    def set_description(self, id: int, description: str | None) -> Axiom:
        axiom = self.get(id)
        axiom.description = description.strip() if description and description.strip() else None
        self._session.flush()
        return axiom

    def list_used_in_theorems(self, id: int) -> list[Theorem]:
        """Theorems with a proof that cites this axiom directly in a step.
        Does not follow theorem-application chains transitively (unlike
        ProofService.list_used_axioms), so a theorem that only reaches this
        axiom through a cited lemma's proof will not appear here."""
        self.get(id)
        theorem_ids = list(
            self._session.scalars(
                select(Proof.theorem_id)
                .join(ProofStep, ProofStep.proof_id == Proof.id)
                .where(ProofStep.step_kind == "axiom", ProofStep.axiom_id == id)
                .distinct()
            )
        )
        if not theorem_ids:
            return []
        return list(
            self._session.scalars(select(Theorem).where(Theorem.id.in_(theorem_ids)).order_by(Theorem.id))
        )

    def register_system(self, name: str, remarks: str | None = None) -> AxiomSystem:
        existing = self._session.scalar(select(AxiomSystem).where(AxiomSystem.name == name))
        if existing is not None:
            raise ConflictError("AxiomSystem", "name", name)

        system = AxiomSystem(name=name, remarks=remarks)
        self._session.add(system)
        self._session.flush()
        return system

    def record_introduction(
        self,
        axiom_id: int,
        *,
        reason: str,
        theory: Sequence[str],
        source: str,
        relation: str,
        strength: str,
        foundation_version: str,
        introduced_by: str,
        reviewed_by: str,
        introduced_at: datetime,
    ) -> AxiomRecord:
        """Record why a non-definitional axiom was introduced (WHITEPAPER §7.4,
        lean-import-design §2.8).  Written by the person introducing the axiom;
        never read by validation or the axiom-dependency computation."""
        axiom = self.get(axiom_id)
        if axiom.origin_kind != "primitive":
            raise ValidationError(
                "only a non-definitional axiom has an introduction record",
                code="axiom.record_definition_derived",
            )
        if self._session.get(AxiomRecord, axiom_id) is not None:
            raise ConflictError("AxiomRecord", "axiom_id", str(axiom_id))
        texts = {
            "reason": reason,
            "source": source,
            "relation": relation,
            "strength": strength,
            "foundation_version": foundation_version,
            "introduced_by": introduced_by,
            "reviewed_by": reviewed_by,
        }
        for field, value in texts.items():
            if not value.strip():
                raise ValidationError(f"axiom record {field} must not be empty")
        systems = list(theory)
        if not systems:
            raise ValidationError("axiom record theory must name an axiom system")
        for name in systems:
            self.get_system_by_name(name)
        record = AxiomRecord(
            axiom_id=axiom_id,
            theory=json.dumps(systems, ensure_ascii=False),
            introduced_at=introduced_at,
            **texts,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_system(self, id: int) -> AxiomSystem:
        row = self._session.get(AxiomSystem, id)
        if row is None:
            raise NotFoundError("AxiomSystem", id)
        return row

    def get_system_by_name(self, name: str) -> AxiomSystem:
        row = self._session.scalar(
            select(AxiomSystem).where(AxiomSystem.name.in_(axiom_system_lookup_names(name)))
        )
        if row is None:
            raise NotFoundError("AxiomSystem", name)
        return row

    def list_systems(self) -> list[AxiomSystem]:
        return list(self._session.scalars(select(AxiomSystem).order_by(AxiomSystem.id)))

    def add_to_system(self, axiom_system_id: int, axiom_id: int) -> None:
        self.get_system(axiom_system_id)
        self.get(axiom_id)
        existing = self._session.get(
            AxiomSystemMember,
            {"axiom_system_id": axiom_system_id, "axiom_id": axiom_id},
        )
        if existing is not None:
            raise ConflictError("AxiomSystemMember", "axiom_id", str(axiom_id))

        self._session.add(AxiomSystemMember(axiom_system_id=axiom_system_id, axiom_id=axiom_id))
        self._session.flush()

    def remove_from_system(self, axiom_system_id: int, axiom_id: int) -> None:
        self.get_system(axiom_system_id)
        self.get(axiom_id)
        existing = self._session.get(
            AxiomSystemMember,
            {"axiom_system_id": axiom_system_id, "axiom_id": axiom_id},
        )
        if existing is not None:
            self._session.delete(existing)
            self._session.flush()

    def list_system_members(self, axiom_system_id: int) -> list[Axiom]:
        self.get_system(axiom_system_id)
        return list(
            self._session.scalars(
                select(Axiom)
                .join(AxiomSystemMember, Axiom.id == AxiomSystemMember.axiom_id)
                .where(AxiomSystemMember.axiom_system_id == axiom_system_id)
                .order_by(Axiom.id)
            )
        )

    def is_subset(self, child_system_id: int, parent_system_id: int) -> bool:
        self.get_system(child_system_id)
        self.get_system(parent_system_id)

        child_axioms = select(AxiomSystemMember.axiom_id).where(
            AxiomSystemMember.axiom_system_id == child_system_id
        )
        parent_axioms = select(AxiomSystemMember.axiom_id).where(
            AxiomSystemMember.axiom_system_id == parent_system_id
        )
        missing = self._session.scalar(child_axioms.except_(parent_axioms).limit(1))
        return missing is None

    def list_theorems_provable_in_system(self, axiom_system_id: int) -> list[Theorem]:
        """Theorems of the verified proofs that are valid in this system.

        This is the bulk form of ProofService.is_valid_in_system(): the same
        dependency edges and the same defining-axiom filter, taken from
        dem/services/used_axioms.py, evaluated for every verified proof at
        once rather than one proof at a time.  The result is exactly
        ``{p.theorem_id for p in verified proofs if is_valid_in_system(p)}``
        and tests/test_axiom_system_provable_theorems.py holds it there."""
        self.get_system(axiom_system_id)
        system_axiom_ids = set(
            self._session.scalars(
                select(AxiomSystemMember.axiom_id).where(
                    AxiomSystemMember.axiom_system_id == axiom_system_id
                )
            )
        )
        definition_axioms = load_definition_axioms(self._session)
        used_axiom_ids = used_axiom_ids_by_proof(
            load_proof_edges(self._session), definition_axioms
        )
        theorem_ids = {
            theorem_id
            for proof_id, theorem_id in self._session.execute(
                select(Proof.id, Proof.theorem_id).where(Proof.status == "verified")
            )
            if definition_axioms.drop_defining(used_axiom_ids.get(proof_id, frozenset()))
            <= system_axiom_ids
        }
        if not theorem_ids:
            return []
        return list(
            self._session.scalars(select(Theorem).where(Theorem.id.in_(theorem_ids)).order_by(Theorem.id))
        )

    def _register_definition_derived(
        self,
        name: str,
        formula_id: int,
        definition_id: int,
        remarks: str | None = None,
        namespace: str = DEFAULT_NAMESPACE_NAME,
        public_id_key: str | None = None,
    ) -> Axiom:
        if self._session.get(Definition, definition_id) is None:
            raise NotFoundError("Definition", definition_id)
        return self._register(
            name=name,
            formula_id=formula_id,
            origin_kind="definition_derived",
            definition_id=definition_id,
            remarks=remarks,
            namespace=namespace,
            public_id_key=public_id_key,
        )

    def _register(
        self,
        name: str,
        formula_id: int,
        origin_kind: str,
        definition_id: int | None,
        remarks: str | None,
        description: str | None = None,
        namespace: str = DEFAULT_NAMESPACE_NAME,
        public_id_key: str | None = None,
    ) -> Axiom:
        namespace_row = ensure_namespace(self._session, namespace)
        public_id = new_entity_public_id(
            "axiom", namespace_row.name, name, public_id_key
        )
        formula = self._get_proposition_formula(formula_id, "axiom formula must be a proposition")
        existing = self._session.scalar(select(Axiom).where(Axiom.name == name))
        if existing is not None:
            raise ConflictError("Axiom", "name", name)
        if public_id_key is not None and self._session.scalar(
            select(Axiom.id).where(Axiom.public_id == public_id)
        ) is not None:
            raise ConflictError("Axiom", "public_id", public_id)

        axiom = Axiom(
            public_id=public_id,
            name=name,
            namespace_id=namespace_row.id,
            formula_id=formula.id,
            origin_kind=origin_kind,
            definition_id=definition_id,
            description=description.strip() if description and description.strip() else None,
            remarks=remarks,
        )
        self._session.add(axiom)
        self._session.flush()
        return axiom

    def _get_proposition_formula(self, formula_id: int, message: str) -> Formula:
        formula = self._session.get(Formula, formula_id)
        if formula is None:
            raise NotFoundError("Formula", formula_id)
        if formula.formula_type.name != FormulaTypeName.PROPOSITION.value:
            raise ValidationError(message)
        return formula
