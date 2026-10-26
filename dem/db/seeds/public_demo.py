"""Independent introductory logic demonstrations.

Identity, implication chaining and Peirce's law are elementary textbook facts.
These derivations are assembled directly from the reviewed Hilbert schemas and
kernel rules, without translating any external text or importing a theorem corpus.
Japanese names have English descriptions. All proofs use real kernel validation.
"""
from sqlalchemy import select
from dem.db.models import Theorem, Proof, Definition
from dem.services.axiom import AxiomService
from dem.services.symbol import SymbolService
from dem.services.formula import FormulaService
from dem.services.theorem import TheoremService
from dem.services.proof import ProofService
from dem.services.definition import DefinitionService
from dem.types import (Token, PropSubst, Substitution, AxiomStepInput, MPStepInput,
                       AssumptionStepInput, ImplicationIntroStepInput, PremiseStepInput,
                       TheoremStepInput, LogicalDefinitionInput)

DEMO_NAMES = ("含意の自己適用", "含意の連鎖", "導出の引用", "古典含意の例", "前提の保持")


def seed_public_demo(session):
    existing = {row.name: row for row in session.scalars(select(Theorem).where(Theorem.name.in_(DEMO_NAMES)))}
    proofs = list(session.scalars(select(Proof).where(Proof.theorem_id.in_([row.id for row in existing.values()]))))
    if len(existing) == len(DEMO_NAMES) and all(t.status == "proven" for t in existing.values()) and len(proofs) == 6 and all(p.status == "verified" for p in proofs) and session.scalar(select(Definition.id).where(Definition.name == "同式含意")) is not None:
        return
    if existing:
        raise ValueError("Incomplete public demonstration seed")
    symbols, formulas = SymbolService(session), FormulaService(session)
    axioms, theorems, verifier = AxiomService(session), TheoremService(session), ProofService(session, authoring_via="seed")
    p, q, r = [symbols.get_by_name(name) for name in ("φ", "ψ", "χ")]
    imp = symbols.get_by_role("implication").id
    atom = lambda symbol: [Token(symbol.id)]
    implication = lambda a, b: [Token(imp), *a, *b]
    P, Q, R = map(atom, (p, q, r))
    fid = lambda tokens: formulas.register(tokens).id
    def create(name, conclusion, premises=(), description=""):
        return theorems.register(name, fid(conclusion), [fid(tokens) for tokens in premises], description=description)
    def prove(theorem, name, steps):
        proof = verifier.create_proof(theorem.id, name=name)
        for step, tokens in steps:
            verifier.add_step(proof.id, step, fid(tokens))
        verifier.validate(proof.id)
        return proof
    def axiom(name, bindings):
        return AxiomStepInput(axioms.get_by_name(name).id, Substitution(prop_substs=tuple(PropSubst(symbol.id, fid(tokens)) for symbol, tokens in bindings)))
    identity = implication(P, P)
    theorem = create(DEMO_NAMES[0], identity, description="Identity of implication: a direct K/S derivation and an assumption-discharge derivation.")
    a = implication(P, implication(identity, P))
    b = implication(P, identity)
    c = implication(a, implication(b, identity))
    prove(theorem, "KとSによる証明", [(axiom("hilbert_k", [(p, P), (q, identity)]), a),
        (axiom("hilbert_k", [(p, P), (q, P)]), b),
        (axiom("hilbert_s", [(p, P), (q, identity), (r, P)]), c),
        (MPStepInput(0, 2), implication(b, identity)), (MPStepInput(1, 3), identity)])
    prove(theorem, "含意導入による証明", [(AssumptionStepInput(), P), (ImplicationIntroStepInput(0, 0), identity)])
    premises = (implication(P, Q), implication(Q, R), P)
    chain = create(DEMO_NAMES[1], R, premises, "Chaining two implications by modus ponens.")
    chain_proof = prove(chain, "連続したMP", [(PremiseStepInput(0), premises[0]), (PremiseStepInput(1), premises[1]),
        (PremiseStepInput(2), P), (MPStepInput(2, 0), Q), (MPStepInput(3, 1), R)])
    citation = create(DEMO_NAMES[2], R, premises, "An explicit dependency edge citing the implication-chain proof.")
    prove(citation, "既存の導出の引用", [(PremiseStepInput(i), tokens) for i, tokens in enumerate(premises)] +
          [(TheoremStepInput(chain_proof.id, arg_step_ords=(0, 1, 2)), R)])
    peirce = implication(implication(implication(P, Q), P), P)
    classical = create(DEMO_NAMES[3], peirce, description="Peirce's schema, valid in the classical Hilbert system only.")
    prove(classical, "古典公理の使用", [(AxiomStepInput(axioms.get_by_name("hilbert_peirce").id), peirce)])
    weakening = create(DEMO_NAMES[4], implication(Q, P), (P,), "Retaining a premise through an additional antecedent using K.")
    prove(weakening, "Kによる前提の保持", [(PremiseStepInput(0), P), (axiom("hilbert_k", [(p, P), (q, Q)]), implication(P, implication(Q, P))),
          (MPStepInput(0, 1), implication(Q, P))])
    DefinitionService(session, authoring_via="seed").register(LogicalDefinitionInput(
        name="同式含意", param_symbol_ids=(p.id,), body_formula_id=fid(identity),
        remarks="Self-implication connective: a standard definitional abbreviation.", latex_template=r"\mathsf{Self}(#1)"))
