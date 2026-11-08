"""Biconditional schemas supplied in the public-package request."""
from sqlalchemy import select
from dem.db.models import Axiom, AxiomSystem, AxiomSystemMember
from dem.errors import ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService

AXIOM_NAMES = ('同値導入公理', '同値除去公理（左）', '同値除去公理（右）')
SYSTEM_NAMES = ('直観主義論理（同値つき）', '古典論理（同値つき）')
TEXTS = ('(φ → ψ) → (ψ → φ) → (φ ↔ ψ)', '(φ ↔ ψ) → φ → ψ', '(φ ↔ ψ) → ψ → φ')


def seed_public_equivalence(session):
    axioms = list(session.scalars(select(Axiom).where(Axiom.name.in_(AXIOM_NAMES))))
    systems = list(session.scalars(select(AxiomSystem).where(AxiomSystem.name.in_(SYSTEM_NAMES))))
    if axioms or systems:
        if len(axioms) == 3 and len(systems) == 2: return
        raise ValidationError('Incomplete public equivalence seed')
    service, formulas = AxiomService(session), FormulaService(session)
    for name, text in zip(AXIOM_NAMES, TEXTS, strict=True):
        service.register(name, formulas.register(formulas.parse_text(text)[0]).id,
                         public_id_key='dem.public.equivalence::'+name,
                         description='Biconditional schema. 同値の意味を与える公理図式。')
    for old, name in zip(('直観主義論理', '古典論理'), SYSTEM_NAMES, strict=True):
        system = service.register_system(name, remarks='First-order logic with biconditional schemas.',
                                         public_id_key='dem.public.equivalence::'+name)
        source = service.get_system_by_name(old)
        ids = session.scalars(select(AxiomSystemMember.axiom_id).where(AxiomSystemMember.axiom_system_id == source.id))
        for ax in [*ids, *(service.get_by_name(n).id for n in AXIOM_NAMES)]: service.add_to_system(system.id, ax)
