from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dem.db.models import Base
from dem.db.seed import seed_inference_rules, seed_language
from dem.db.seeds.hilbert import seed_hilbert_core
from dem.db.seeds.hilbert_toolkit import DischargeStep, HilbertToolkit, ProofStepSpec
from dem.types import (
    AxiomStepInput,
    PremiseStepInput,
    Substitution,
    TheoremStepInput,
    Token,
)


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_language(session)
    seed_inference_rules(session)
    seed_hilbert_core(session)
    return session


def _gen_derivation(toolkit: HilbertToolkit):
    """From `phi` (premise, unused) and `x=x` (fact, via hilbert_eq_refl),
    Gen(x) gives `forall x(x=x)`."""
    x = toolkit.symbols.get_by_name("x")
    eq_ = toolkit.symbols.get_by_role("equality")
    phi_tokens = toolkit.atom(toolkit.phi)
    eq_refl_axiom = toolkit.axioms.get_by_name("hilbert_eq_refl")
    eq_x_x_tokens = [Token(symbol_id=eq_.id), Token(symbol_id=x.id), Token(symbol_id=x.id)]
    forall_x_eq_x_x = [
        Token(symbol_id=toolkit.forall_.id),
        Token(symbol_id=eq_.id),
        Token(de_bruijn_index=0),
        Token(de_bruijn_index=0),
    ]
    original = [
        DischargeStep(kind="premise", tokens=phi_tokens, premise_index=0),  # L0
        DischargeStep(
            kind="fact", tokens=eq_x_x_tokens, fact_input=AxiomStepInput(eq_refl_axiom.id)
        ),  # L1
        DischargeStep(
            kind="gen", tokens=forall_x_eq_x_x, gen_body_ord=1, gen_variable_symbol_id=x.id
        ),  # L2
    ]
    return original, phi_tokens, forall_x_eq_x_x


def test_expand_implication_intro_handles_gen_step() -> None:
    """Invariant (E) on the Gen branch (design doc §9.4).

    Eliminating a ⇒intro that reaches across a Gen is the one case that needs
    `hilbert_forall_distribution`, and its side condition -- the discharged
    formula must be vacuous in the generalised variable -- is exactly what the
    kernel's Gen already enforces through `premise_deps`. So the expansion of
    this proof must be accepted by the kernel too.
    """
    with make_session() as session:
        toolkit = HilbertToolkit(session)
        original, phi_tokens, forall_x_eq_x_x = _gen_derivation(toolkit)
        target = toolkit.imp(phi_tokens, forall_x_eq_x_x)

        with_intro = toolkit.discharge(
            original, target_premise_index=0, discharged_tokens=phi_tokens
        )
        expanded = toolkit.expand_implication_intro(with_intro)
        assert expanded[-1].tokens == target
        assert {step.kind for step in expanded} & {"assumption", "imp_intro"} == set()

        theorem = toolkit._get_or_create_theorem("test_expand_gen_closed", target, [])
        assert toolkit._prove(theorem, toolkit.to_proof_step_specs(expanded)).status == (
            "verified"
        )


def test_discharge_handles_gen_step() -> None:
    """`discharge` should be able to close a derivation containing an
    internal Gen step: from `phi` (premise, unused) and `x=x` (fact, via
    hilbert_eq_refl), Gen(x) gives `forall x(x=x)`; discharging `phi` should
    yield the 0-premise fact `phi -> forall x(x=x)`."""
    with make_session() as session:
        toolkit = HilbertToolkit(session)

        x = toolkit.symbols.get_by_name("x")
        eq_ = toolkit.symbols.get_by_role("equality")
        phi_tokens = toolkit.atom(toolkit.phi)
        eq_refl_axiom = toolkit.axioms.get_by_name("hilbert_eq_refl")
        eq_x_x_tokens = [Token(symbol_id=eq_.id), Token(symbol_id=x.id), Token(symbol_id=x.id)]

        original = [
            DischargeStep(kind="premise", tokens=phi_tokens, premise_index=0),  # L0
            DischargeStep(
                kind="fact", tokens=eq_x_x_tokens, fact_input=AxiomStepInput(eq_refl_axiom.id)
            ),  # L1
        ]
        forall_x_eq_x_x = [
            Token(symbol_id=toolkit.forall_.id),
            Token(symbol_id=eq_.id),
            Token(de_bruijn_index=0),
            Token(de_bruijn_index=0),
        ]
        original.append(
            DischargeStep(kind="gen", tokens=forall_x_eq_x_x, gen_body_ord=1, gen_variable_symbol_id=x.id)
        )  # L2

        discharged = toolkit.discharge(original, target_premise_index=0, discharged_tokens=phi_tokens)
        specs = toolkit.to_proof_step_specs(discharged)

        target = toolkit.imp(phi_tokens, forall_x_eq_x_x)
        theorem = toolkit._get_or_create_theorem("test_discharge_gen_closed", target, [])
        proof = toolkit._prove(theorem, specs)

        assert proof.status == "verified"


def test_a_premised_theorem_cited_with_arguments_can_be_discharged() -> None:
    """The shape §5 rule 12 was working around (design doc 9.11 (B)).

    Citing a theorem that has premises makes the line depend on earlier lines,
    so `_ks_lift` cannot K-lift it the way it lifts a plain fact.  It goes
    through the cited theorem's *curried* form instead -- which the toolkit now
    derives on demand, because `ProofService.reconstruct_steps` can replay any
    stored proof (substitutions are persisted).

    The elimination procedure must still reach the same line using nothing but
    MP/Gen and citations: that is invariant (E), the whole justification for
    ⇒introduction being an admissible rule rather than a trusted one.
    """
    session = make_session()
    toolkit = HilbertToolkit(session)
    premises = [toolkit.atom(toolkit.phi), toolkit.atom(toolkit.psi)]
    conclusion = premises[0]
    theorem = toolkit._get_or_create_theorem(
        "probe_two_premise_projection", conclusion, premises
    )
    proof = toolkit._prove(
        theorem,
        [ProofStepSpec(PremiseStepInput(0), conclusion)],
    )

    specs = [ProofStepSpec(PremiseStepInput(i), p) for i, p in enumerate(premises)]
    specs.append(
        ProofStepSpec(
            TheoremStepInput(proof.id, Substitution(), tuple(range(len(premises)))),
            conclusion,
        )
    )
    steps = toolkit.from_proof_step_specs(specs)
    assert [step.kind for step in steps] == ["premise"] * len(premises) + ["applied"]

    for index in reversed(range(len(premises))):
        steps = toolkit.discharge(
            steps, target_premise_index=index, discharged_tokens=premises[index]
        )
    target = conclusion
    for tokens in reversed(premises):
        target = toolkit.imp(tokens, target)
    assert steps[-1].tokens == target

    expanded = toolkit.expand_implication_intro(steps)
    assert expanded[-1].tokens == target
    assert {step.kind for step in expanded} <= {"fact", "mp", "gen"}

    # ...and the kernel accepts the expansion.
    fresh = toolkit._get_or_create_theorem("probe_applied_discharge", target, [])
    toolkit._prove(fresh, toolkit.to_proof_step_specs(expanded))
    assert fresh.status == "proven"
