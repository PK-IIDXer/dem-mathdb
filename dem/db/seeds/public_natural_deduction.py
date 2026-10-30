"""Elementary connective schemas and independently assembled derivations.

The specification and names were supplied by the user. These schemas give
connectives their meaning; they are not derived from the Hilbert core.
Implication introduction and universal introduction are the kernel's ImpIntro
and Gen rules, rather than additional premised theorems in this package.
"""
from sqlalchemy import select

from dem.db.models import Axiom, AxiomSystem, Proof, Theorem
from dem.db.seeds.hilbert import HILBERT_CORE_AXIOM_NAMES
from dem.errors import ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import (
    AssumptionStepInput, AxiomStepInput, ImplicationIntroStepInput,
    MPStepInput, PremiseStepInput, PropSubst, Substitution, TheoremStepInput, Token,
)

AXIOM_NAMES = (
    "矛盾除去公理", "否定導入公理", "否定除去公理", "連言導入公理",
    "連言除去公理（左）", "連言除去公理（右）", "選言導入公理（左）",
    "選言導入公理（右）", "選言除去公理", "存在導入公理", "存在除去公理",
)
SYSTEM_NAMES = ("直観主義論理", "古典論理")
RULE_NAMES = (
    "含意除去", "矛盾除去", "否定導入", "否定除去", "連言導入",
    "連言除去（左）", "連言除去（右）", "選言導入（左）", "選言導入（右）",
    "選言除去", "全称除去", "存在導入", "存在除去", "等号代入",
)
MULTISTEP_NAMES = (
    "二重否定導入", "対偶", "無矛盾律", "連言の交換", "選言の交換",
    "ド・モルガン", "二重否定除去", "排中律",
)
THEOREM_NAMES = (*RULE_NAMES, *MULTISTEP_NAMES)


def seed_public_natural_deduction(session):
    """Add a separate package, with an inexpensive completed-seed check."""
    existing = list(session.scalars(select(Theorem).where(Theorem.name.in_(THEOREM_NAMES))))
    if existing:
        proofs = list(session.scalars(select(Proof).where(Proof.theorem_id.in_([t.id for t in existing]))))
        axioms = list(session.scalars(select(Axiom).where(Axiom.name.in_(AXIOM_NAMES))))
        systems = list(session.scalars(select(AxiomSystem).where(AxiomSystem.name.in_(SYSTEM_NAMES))))
        if (len(existing) == len(THEOREM_NAMES) and all(t.status == "proven" for t in existing)
                and len(proofs) == len(THEOREM_NAMES) and all(p.status == "verified" for p in proofs)
                and len({p.theorem_id for p in proofs}) == len(THEOREM_NAMES)
                and len(axioms) == len(AXIOM_NAMES) and len(systems) == len(SYSTEM_NAMES)):
            return
        raise ValidationError("Incomplete public natural deduction seed")
    _Derivations(session).seed()


class _Derivations:
    def __init__(self, session):
        self.session = session
        self.symbols = SymbolService(session)
        self.formulas = FormulaService(session)
        self.axioms = AxiomService(session)
        self.theorems = TheoremService(session)
        self.proofs = ProofService(session, authoring_via="seed")
        self.variables = {name: self.symbols.get_by_name(name) for name in ("φ", "ψ", "χ", "φ¹", "x", "y", "t")}
        self.references = {}

    def atom(self, name):
        return [Token(self.variables[name].id)]

    def op(self, role, *args):
        names = {"bottom": "⊥", "negation": "¬", "conjunction": "∧",
                 "disjunction": "∨", "existential_quantifier": "∃"}
        symbol = self.symbols.get_by_name(names[role]) if role in names else self.symbols.get_by_role(role)
        return [Token(symbol.id), *(t for arg in args for t in arg)]

    def imp(self, a, b):
        return self.op("implication", a, b)

    def neg(self, a):
        return self.op("negation", a)

    def conj(self, a, b):
        return self.op("conjunction", a, b)

    def disj(self, a, b):
        return self.op("disjunction", a, b)

    def fid(self, tokens):
        return self.formulas.register(tokens).id

    def substitution(self, bindings):
        return Substitution(prop_substs=tuple(
            PropSubst(self.variables[name].id, self.fid(tokens)) for name, tokens in bindings.items()))

    def line(self, step, tokens):
        index = len(self.lines)
        self.lines.append((step, tokens))
        return index

    def ax(self, name, **bindings):
        row = self.axioms.get_by_name(name)
        substitution = self.substitution(bindings)
        # Compute the instance through the real formula service.
        tokens = self.proofs.compute_substituted_tokens(row.formula_id, substitution)
        return self.line(AxiomStepInput(row.id, substitution), tokens)

    def assume(self, tokens):
        return self.line(AssumptionStepInput(), tokens)

    def mp(self, antecedent, implication, conclusion):
        return self.line(MPStepInput(antecedent, implication), conclusion)

    def close(self, assumption, body):
        return self.line(ImplicationIntroStepInput(assumption, body),
                         self.imp(self.lines[assumption][1], self.lines[body][1]))

    def cite(self, name, conclusion, args=(), **bindings):
        return self.line(TheoremStepInput(self.references[name].id, self.substitution(bindings),
                                         arg_step_ords=tuple(args)), conclusion)

    def start(self, premises=()):
        self.lines = [(PremiseStepInput(i), tokens) for i, tokens in enumerate(premises)]

    def finish(self, name, conclusion, premises=()):
        theorem = self.theorems.register(
            name, self.fid(conclusion), [self.fid(p) for p in premises],
            description=("教科書的な論理の規則・基本定理。含意導入はImpIntro、全称導入はGenに相当します。"
                         "各証明は使用した公理に相対的に妥当です。"),
            public_id_key="dem.public.natural-deduction::" + name)
        proof = self.proofs.create_proof(theorem.id, name=name + "の証明")
        for step, tokens in self.lines:
            self.proofs.add_step(proof.id, step, self.fid(tokens))
        self.proofs.validate(proof.id)
        self.references[name] = proof

    def seed(self):
        P, Q, R = [self.atom(n) for n in ("φ", "ψ", "χ")]
        B = self.op("bottom")
        I, N, C, D = self.imp, self.neg, self.conj, self.disj
        px, py, pt = [[*self.atom("φ¹"), *self.atom(n)] for n in ("x", "y", "t")]
        bound = [*self.atom("φ¹"), Token(de_bruijn_index=0)]
        every = self.op("universal_quantifier", bound)
        some = self.op("existential_quantifier", bound)
        every_imp = self.op("universal_quantifier", I(bound, Q))
        equality = self.op("equality", self.atom("x"), self.atom("y"))
        schemas = (
            I(B, P), I(I(P, B), N(P)), I(N(P), I(P, B)), I(P, I(Q, C(P, Q))),
            I(C(P, Q), P), I(C(P, Q), Q), I(P, D(P, Q)), I(Q, D(P, Q)),
            I(I(P, R), I(I(Q, R), I(D(P, Q), R))), I(pt, some), I(every_imp, I(some, Q)),
        )
        for name, tokens in zip(AXIOM_NAMES, schemas, strict=True):
            self.axioms.register(name, self.fid(tokens),
                description="Hilbert coreから導出したものではなく、結合子の意味を与えるために採用したスキーマ。",
                public_id_key="dem.public.natural-deduction::" + name)
        for index, name in enumerate(SYSTEM_NAMES):
            system = self.axioms.register_system(name,
                remarks="Hilbert coreの量化・等号公理と、結合子・存在量化のスキーマ。" + ("パース公理を含む。" if index else "パース公理を含まない。"),
                public_id_key="dem.public.natural-deduction::" + name)
            for axiom in (*HILBERT_CORE_AXIOM_NAMES, *AXIOM_NAMES, *(("hilbert_peirce",) if index else ())):
                self.axioms.add_to_system(system.id, self.axioms.get_by_name(axiom).id)

        # The premised rules retain the precise premise order in the specification.
        specs = (
            ("含意除去", (I(P, Q), P), Q, None),
            ("矛盾除去", (B,), P, "矛盾除去公理"),
            ("否定導入", (I(P, B),), N(P), "否定導入公理"),
            ("否定除去", (N(P), P), B, "否定除去公理"),
            ("連言導入", (P, Q), C(P, Q), "連言導入公理"),
            ("連言除去（左）", (C(P, Q),), P, "連言除去公理（左）"),
            ("連言除去（右）", (C(P, Q),), Q, "連言除去公理（右）"),
            ("選言導入（左）", (P,), D(P, Q), "選言導入公理（左）"),
            ("選言導入（右）", (Q,), D(P, Q), "選言導入公理（右）"),
            ("選言除去", (D(P, Q), I(P, R), I(Q, R)), R, "選言除去公理"),
            ("全称除去", (every,), pt, "hilbert_forall_elim"),
            ("存在導入", (pt,), some, "存在導入公理"),
            ("存在除去", (some, every_imp), Q, "存在除去公理"),
            ("等号代入", (equality, px), py, "hilbert_eq_subst"),
        )
        for name, premises, conclusion, axiom in specs:
            self.start(premises)
            if axiom is None:
                self.mp(1, 0, conclusion)
            else:
                current = self.ax(axiom)
                order = (1, 2, 0) if name == "選言除去" else (1, 0) if name == "存在除去" else tuple(range(len(premises)))
                for index in order:
                    # Each current formula is an implication; obtain its consequent structurally.
                    from dem.services.proof import decompose_implication_pure
                    tokens = self.lines[current][1]
                    _, consequent = decompose_implication_pure(tokens, self.symbols.get_by_role("implication").id,
                                                              self.formulas._load_symbol_meta(tokens))
                    current = self.mp(index, current, consequent)
            self.finish(name, conclusion, premises)

        self.start()
        a, b = self.assume(P), self.assume(N(P))
        contradiction = self.cite("否定除去", B, (b, a))
        implication = self.close(b, contradiction)
        double = self.mp(implication, self.ax("否定導入公理", φ=N(P)), N(N(P)))
        self.close(a, double)
        self.finish("二重否定導入", I(P, N(N(P))))

        self.start()
        a, b, c = self.assume(I(P, Q)), self.assume(N(Q)), self.assume(P)
        q = self.mp(c, a, Q)
        contradiction = self.cite("否定除去", B, (b, q), φ=Q)
        implication = self.close(c, contradiction)
        not_p = self.mp(implication, self.ax("否定導入公理"), N(P))
        self.close(a, self.close(b, not_p))
        self.finish("対偶", I(I(P, Q), I(N(Q), N(P))))

        self.start()
        a = self.assume(C(P, N(P)))
        p = self.mp(a, self.ax("連言除去公理（左）", ψ=N(P)), P)
        np = self.mp(a, self.ax("連言除去公理（右）", ψ=N(P)), N(P))
        contradiction = self.cite("否定除去", B, (np, p))
        implication = self.close(a, contradiction)
        self.mp(implication, self.ax("否定導入公理", φ=C(P, N(P))), N(C(P, N(P))))
        self.finish("無矛盾律", N(C(P, N(P))))

        self.start()
        a = self.assume(C(P, Q))
        p = self.mp(a, self.ax("連言除去公理（左）"), P)
        q = self.mp(a, self.ax("連言除去公理（右）"), Q)
        combined = self.cite("連言導入", C(Q, P), (q, p), φ=Q, ψ=P)
        self.close(a, combined)
        self.finish("連言の交換", I(C(P, Q), C(Q, P)))

        self.start()
        target = D(Q, P)
        a = self.assume(D(P, Q))
        b = self.assume(P)
        branch = self.mp(b, self.ax("選言導入公理（右）", φ=Q, ψ=P), target)
        left = self.close(b, branch)
        c = self.assume(Q)
        branch = self.mp(c, self.ax("選言導入公理（左）", φ=Q, ψ=P), target)
        right = self.close(c, branch)
        result = self.cite("選言除去", target, (a, left, right), χ=target)
        self.close(a, result)
        self.finish("選言の交換", I(D(P, Q), target))

        self.start()
        a = self.assume(N(D(P, Q)))
        negatives = []
        for formula, axiom in ((P, "選言導入公理（左）"), (Q, "選言導入公理（右）")):
            b = self.assume(formula)
            disjunction = self.mp(b, self.ax(axiom), D(P, Q))
            contradiction = self.cite("否定除去", B, (a, disjunction), φ=D(P, Q))
            implication = self.close(b, contradiction)
            negatives.append(self.mp(implication, self.ax("否定導入公理", φ=formula), N(formula)))
        combined = self.cite("連言導入", C(N(P), N(Q)), negatives, φ=N(P), ψ=N(Q))
        self.close(a, combined)
        self.finish("ド・モルガン", I(N(D(P, Q)), C(N(P), N(Q))))

        # The user's independently verified thirteen-line derivation, unchanged.
        self.start()
        a = self.assume(N(N(P)))                       # 0
        removal = self.ax("否定除去公理", φ=N(P))       # 1
        to_bottom = self.mp(a, removal, I(N(P), B))    # 2
        b = self.assume(I(P, B))                      # 3
        introduction = self.ax("否定導入公理")          # 4
        np = self.mp(b, introduction, N(P))           # 5
        contradiction = self.mp(np, to_bottom, B)    # 6
        explosion = self.ax("矛盾除去公理")             # 7
        p = self.mp(contradiction, explosion, P)      # 8
        antecedent = self.close(b, p)                 # 9
        peirce = self.ax("hilbert_peirce", ψ=B)       # 10
        p = self.mp(antecedent, peirce, P)            # 11
        self.close(a, p)                             # 12
        self.finish("二重否定除去", I(N(N(P)), P))

        self.start()
        target = D(P, N(P))
        a = self.assume(N(target))
        b = self.assume(P)
        disjunction = self.mp(b, self.ax("選言導入公理（左）", ψ=N(P)), target)
        contradiction = self.cite("否定除去", B, (a, disjunction), φ=target)
        implication = self.close(b, contradiction)
        np = self.mp(implication, self.ax("否定導入公理"), N(P))
        disjunction = self.mp(np, self.ax("選言導入公理（右）", ψ=N(P)), target)
        contradiction = self.cite("否定除去", B, (a, disjunction), φ=target)
        implication = self.close(a, contradiction)
        double = self.mp(implication, self.ax("否定導入公理", φ=N(target)), N(N(target)))
        removal = self.cite("二重否定除去", I(N(N(target)), target), φ=target)
        self.mp(double, removal, target)
        self.finish("排中律", target)
