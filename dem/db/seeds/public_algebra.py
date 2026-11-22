"""Public binary operations, semigroups and monoids over set maps."""

from sqlalchemy import select

from dem.db.models import Symbol
from dem.db.seeds.public_relations import SetRelationProofs
from dem.db.seeds.public_set_tools import completed
from dem.db.seeds.public_zfc import THEOREM_NAMES as ZF
from dem.services.definition import DefinitionPublicIdKeys, DefinitionService
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.types import FunctionDefinitionInput, PredicateDefinitionInput, SymbolTypeName

PACKAGE = "algebra"
ASSOCIATIVITY = ("(∀ x. ∀ y. ∀ z. (x ∈ S → (y ∈ S → (z ∈ S → "
                 "op(m, op(m, x, y), z) = op(m, x, op(m, y, z))))))")
IDENTITY = "(∀ x. (x ∈ S → (op(m, e, x) = x ∧ op(m, x, e) = x)))"
DEFINITIONS = (
    ("op", FunctionDefinitionInput, ("m", "x", "y"), "ev(m, ⟨,⟩(x, y))", r"#2 \cdot_{#1} #3"),
    ("IsSemigroup", PredicateDefinitionInput, ("S", "m"),
     f"IsSet(S) ∧ (IsMap(m, S × S, S) ∧ {ASSOCIATIVITY})",
     r"\left(#1, #2\right) \mathrel{\mathsf{IsSemigroup}}"),
    ("IsMonoid", PredicateDefinitionInput, ("S", "m", "e"),
     f"IsSemigroup(S, m) ∧ (e ∈ S ∧ {IDENTITY})",
     r"\left(#1, #2, #3\right) \mathrel{\mathsf{IsMonoid}}"),
)
VARIABLES = ("m", "e")
MAP = "IsMap(m, S × S, S)"
ONE_POINT = "{}(⟨,⟩(⟨,⟩(a, a), a))"
STATEMENTS = (
    ("演算:値の所属", ("IsSet(S)", MAP, "x ∈ S", "y ∈ S"), "op(m, x, y) ∈ S"),
    ("演算:グラフと値", ("IsSet(S)", MAP, "x ∈ S", "y ∈ S", "z ∈ S"),
     "(⟨,⟩(⟨,⟩(x, y), z) ∈ m ↔ op(m, x, y) = z)"),
    ("半群:台の集合性", ("IsSemigroup(S, m)",), "IsSet(S)"),
    ("半群:演算は写像", ("IsSemigroup(S, m)",), MAP),
    ("半群:演算の所属", ("IsSemigroup(S, m)", "x ∈ S", "y ∈ S"), "op(m, x, y) ∈ S"),
    ("半群:結合律", ("IsSemigroup(S, m)", "x ∈ S", "y ∈ S", "z ∈ S"),
     "op(m, op(m, x, y), z) = op(m, x, op(m, y, z))"),
    ("半群:導入", ("IsSet(S)", MAP, ASSOCIATIVITY), "IsSemigroup(S, m)"),
    ("半群:一点半群", ("IsSet(a)",), f"IsSemigroup({{}}(a), {ONE_POINT})"),
    ("半群:空半群", (), "IsSemigroup(∅, ∅)"),
    ("モノイド:半群である", ("IsMonoid(S, m, e)",), "IsSemigroup(S, m)"),
    ("モノイド:単位元の所属", ("IsMonoid(S, m, e)",), "e ∈ S"),
    ("モノイド:左単位律", ("IsMonoid(S, m, e)", "x ∈ S"), "op(m, e, x) = x"),
    ("モノイド:右単位律", ("IsMonoid(S, m, e)", "x ∈ S"), "op(m, x, e) = x"),
    ("モノイド:導入", ("IsSemigroup(S, m)", "e ∈ S", IDENTITY), "IsMonoid(S, m, e)"),
    ("モノイド:単位元の一意性", ("IsMonoid(S, m, e)", "IsMonoid(S, m, u)"), "e = u"),
    ("モノイド:一点モノイド", ("IsSet(a)",), f"IsMonoid({{}}(a), {ONE_POINT}, a)"),
    ("モノイド:空集合はモノイドでない", (), "¬(IsMonoid(∅, m, e))"),
)
THEOREM_NAMES = tuple(name for name, _, _ in STATEMENTS)


def register_definitions(session):
    symbols, formulas = SymbolService(session), FormulaService(session)
    definitions = DefinitionService(session, authoring_via="seed")
    variable_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    for name in VARIABLES:
        if session.scalar(select(Symbol.id).where(Symbol.name == name)) is None:
            symbols.register(name, variable_type.id, 0, public_id_key=f"dem.foundation.logic::{name}")
    for name, kind, params, body, latex in DEFINITIONS:
        ids = tuple(symbols.get_by_name(param).id for param in params)
        formula_id = formulas.register(formulas.parse_text(body)[0]).id
        key = f"dem.public.{PACKAGE}::{name}"
        definitions.register(kind(name, ids, formula_id, latex_template=latex),
                             public_id_keys=DefinitionPublicIdKeys(key, key, key))


def seed_public_algebra(session):
    names = tuple(name for name, *_ in DEFINITIONS)
    if completed(session, THEOREM_NAMES, tuple(f"{name} 定義公理" for name in names), (), names):
        return
    register_definitions(session)
    proofs = AlgebraProofs(session, PACKAGE)
    proofs.seed_operations()
    proofs.seed_semigroups()
    proofs.seed_examples()
    proofs.seed_monoids()


class AlgebraProofs(SetRelationProofs):
    def statement(self, index):
        return STATEMENTS[index - 1]

    def algebra(self, index, *args, **terms):
        return self.cite(self.statement(index)[0], terms=terms, args=args)

    def open_statement(self, index):
        return self.start(tuple(self.parse(text) for text in self.statement(index)[1]))

    def close_statement(self, index):
        name, premises, conclusion = self.statement(index)
        self.finish(name, self.parse(conclusion), premises=tuple(map(self.parse, premises)))
        self.start()

    def square(self, S):
        return self.op("×", S, S)

    def pair_in_square(self, sS, S, mx, my, x, y):
        coordinates = self.named(11, sS, sS, self.set_member(mx), self.set_member(my), X=S, Y=S, a=x, b=y)
        return self.iff_out(coordinates, self.pair(mx, my), True)

    def seed_operations(self):
        S, m, x, y, z, v = map(self.atom, ("S", "m", "x", "y", "z", "v"))
        square, pair = self.square(S), self.ordered(x, y)

        sS, map_, mx, my = self.open_statement(1)
        square_set = self.named(9, sS, sS, X=S, Y=S)
        belongs = self.pair_in_square(sS, S, mx, my, x, y)
        value = self.named(34, square_set, sS, map_, belongs, f=m, X=square, Y=S, x=pair)
        definition = self.definition("op", m, x, y)
        self.transport(self.sym(definition), self.left(value), "v", self.member(v, S))
        self.close_statement(1)

        sS, map_, mx, my, mz = self.open_statement(2)
        square_set = self.named(9, sS, sS, X=S, Y=S)
        belongs = self.pair_in_square(sS, S, mx, my, x, y)
        graph = self.named(35, square_set, sS, map_, belongs, f=m, X=square, Y=S, x=pair, y=z)
        definition = self.definition("op", m, x, y)
        in_graph = self.member(self.ordered(pair, z), m)
        forward = self.by_assumption(in_graph, lambda g: self.trans(definition, self.iff_out(graph, self.pair(mz, g))))
        reverse = self.by_assumption(self.eq(self.op("op", m, x, y), z), lambda e: self.right(
            self.iff_out(graph, self.trans(self.sym(definition), e), True)))
        self.iff_in(forward, reverse)
        self.close_statement(2)

    def semigroup_parts(self, given, S, m):
        return self.iff_out(self.definition("IsSemigroup", S, m), given)

    def seed_semigroups(self):
        S, m, x, y, z = map(self.atom, ("S", "m", "x", "y", "z"))
        given, = self.open_statement(3)
        self.left(self.semigroup_parts(given, S, m))
        self.close_statement(3)

        given, = self.open_statement(4)
        self.left(self.right(self.semigroup_parts(given, S, m)))
        self.close_statement(4)

        given, mx, my = self.open_statement(5)
        self.algebra(1, self.algebra(3, given), self.algebra(4, given), mx, my)
        self.close_statement(5)

        given, mx, my, mz = self.open_statement(6)
        associative = self.right(self.right(self.semigroup_parts(given, S, m)))
        self.apply(self.uis(associative, x, y, z), mx, my, mz)
        self.close_statement(6)

        sS, map_, associative = self.open_statement(7)
        self.iff_out(self.definition("IsSemigroup", S, m), self.pair(sS, self.pair(map_, associative)), True)
        self.close_statement(7)

    def seed_examples(self):
        a, q, x, y, z, v = map(self.atom, ("a", "q", "x", "y", "z", "v"))
        S, point = self.single(a), self.ordered(a, a)
        graph = self.single(self.ordered(point, a))
        square = self.square(S)

        sa, = self.open_statement(8)
        sS = self.set_single(a)
        a_in = self.iff_out(self.smem(sa, a), self.refl(a), True)
        square_set = self.named(9, sS, sS, X=S, Y=S)
        point_in = self.pair_in_square(sS, S, a_in, a_in, a, a)
        only_point = self.square_member_is_point(sS, sa, S, a, q)
        triple = self.ordered(point, a)
        triple_in = self.iff_out(self.smem(self.set_ordered(point, a), triple), self.refl(triple), True)
        product_coordinates = self.named(11, square_set, sS, self.set_ordered(a, a), sa,
                                         X=square, Y=S, a=point, b=a)
        triple_in_product = self.iff_out(product_coordinates, self.pair(point_in, a_in), True)
        member = self.assume(self.member(q, graph))
        is_triple = self.iff_out(self.smem(self.set_ordered(point, a), q), member)
        target = self.op("×", square, S)
        in_product = self.transport(self.sym(is_triple), triple_in_product, "v", self.member(v, target))
        subset = self.subset_in(graph, target, self.gen(self.close(member, in_product), "q"))
        relation = self.iff_out(self.definition("IsRelation", graph, square, S),
                                self.pair(self.set_single(triple), subset), True)

        belongs = self.assume(self.member(x, square))
        is_point = self.mp(only_point(x), belongs)
        value = (self.value(graph, S, x, self.atom("w")), ("w",))
        holds = self.pair(a_in, self.transport(self.sym(is_point), triple_in, "v",
                                                 self.member(self.ordered(v, a), graph)))
        candidate = self.assume(self.value(graph, S, x, y))
        same = self.iff_out(self.smem(sa, y), self.left(candidate))
        unique = self.cite("一意存在:導入", {"φ¹": value}, {"t": a},
                           args=(holds, self.gen(self.close(candidate, same), "y")))
        total = self.gen(self.close(belongs, unique), "x")
        map_ = self.iff_out(self.definition("IsMap", graph, square, S), self.pair(relation, total), True)

        def collapse(term_in):
            return self.iff_out(self.smem(sa, self.parts(self.tokens(term_in))[0]), term_in)

        mx, my, mz = (self.assume(self.member(t, S)) for t in (x, y, z))
        xy, yz = self.op("op", graph, x, y), self.op("op", graph, y, z)
        xy_in = self.algebra(1, sS, map_, mx, my, S=S, m=graph)
        yz_in = self.algebra(1, sS, map_, my, mz, S=S, m=graph, x=y, y=z)
        left = collapse(self.algebra(1, sS, map_, xy_in, mz, S=S, m=graph, x=xy, y=z))
        right = collapse(self.algebra(1, sS, map_, mx, yz_in, S=S, m=graph, y=yz))
        equal = self.trans(left, self.sym(right))
        associative = self.close_many((mx, my, mz), equal)
        for name in ("z", "y", "x"):
            associative = self.gen(associative, name)
        self.algebra(7, sS, map_, associative, S=S, m=graph)
        self.close_statement(8)

        empty = self.atom("∅")
        empty_set = self.cite(ZF[11])
        no_element = self.cite(ZF[12])
        square = self.square(empty)
        member = self.assume(self.member(q, square))
        exists = self.iff_out(self.ui(self.named(10, empty_set, empty_set, X=empty, Y=empty), q), member)
        in_empty = self.using_witness(exists, "x", lambda outer: self.using_witness(outer, "y", lambda witness: self.mp(
            self.ax("false", {"φ": self.member(q, empty)}),
            self.not_out(self.ui(no_element, x), self.left(witness)))))
        smaller = self.subset_in(square, empty, self.gen(self.close(member, in_empty), "q"))
        square_set = self.named(9, empty_set, empty_set, X=empty, Y=empty)
        equal = self.named(7, square_set, empty_set, smaller, self.named(8, a=square), a=square, b=empty)
        map_ = self.transport(self.sym(equal), self.named(20, Y=empty), "v", self.op("IsMap", empty, v, empty))
        expanded = self.definition("IsSemigroup", empty, empty)
        associative = self.parts(self.parts(self.parts(self.tokens(expanded))[1])[1])[1]
        body = self.opened(self.opened(self.opened(associative, "x"), "y"), "z")
        hypothesis, rest = self.parts(body)
        result = self.from_impossible_membership(hypothesis, self.ui(no_element, x), rest)
        for name in ("z", "y", "x"):
            result = self.gen(result, name)
        self.iff_out(expanded, self.pair(empty_set, self.pair(map_, result)), True)
        self.close_statement(9)

    def square_member_is_point(self, sS, sa, S, a, q):
        """For each term t, a derivation of t ∈ S × S → t = ⟨a, a⟩ for S = {a}."""
        # The witnesses are c and d, which never occur in the term being tested.
        c, d = self.atom("c"), self.atom("d")
        membership = self.named(10, sS, sS, X=S, Y=S)

        def at(term):
            belongs = self.assume(self.member(term, self.square(S)))
            exists = self.iff_out(self.ui(membership, term), belongs)

            def coordinates(witness):
                first, rest = self.left(witness), self.right(witness)
                second, equality = self.left(rest), self.right(rest)
                c_is = self.iff_out(self.smem(sa, c), first)
                d_is = self.iff_out(self.smem(sa, d), second)
                shifted = self.transport(c_is, equality, "v", self.eq(term, self.ordered(self.atom("v"), d)))
                return self.transport(d_is, shifted, "v", self.eq(term, self.ordered(a, self.atom("v"))))

            result = self.using_witness(exists, "c", lambda e: self.using_witness(e, "d", coordinates))
            return self.close(belongs, result)

        return at

    def monoid_parts(self, given, S, m, e):
        return self.iff_out(self.definition("IsMonoid", S, m, e), given)

    def seed_monoids(self):
        S, m, e, u, x, a = map(self.atom, ("S", "m", "e", "u", "x", "a"))
        given, = self.open_statement(10)
        self.left(self.monoid_parts(given, S, m, e))
        self.close_statement(10)

        given, = self.open_statement(11)
        self.left(self.right(self.monoid_parts(given, S, m, e)))
        self.close_statement(11)

        for index, side in ((12, self.left), (13, self.right)):
            given, mx = self.open_statement(index)
            identity = self.right(self.right(self.monoid_parts(given, S, m, e)))
            side(self.mp(self.ui(identity, x), mx))
            self.close_statement(index)

        semigroup, me, identity = self.open_statement(14)
        self.iff_out(self.definition("IsMonoid", S, m, e), self.pair(semigroup, self.pair(me, identity)), True)
        self.close_statement(14)

        first, second = self.open_statement(15)
        e_in, u_in = self.algebra(11, first), self.algebra(11, second, e=u)
        towards_u = self.algebra(12, first, u_in, x=u)
        towards_e = self.algebra(13, second, e_in, e=u, x=e)
        self.trans(self.sym(towards_e), towards_u)
        self.close_statement(15)

        sa, = self.open_statement(16)
        S, graph = self.single(a), self.single(self.ordered(self.ordered(a, a), a))
        semigroup = self.algebra(8, sa)
        sS, map_ = self.algebra(3, semigroup, S=S, m=graph), self.algebra(4, semigroup, S=S, m=graph)
        a_in = self.iff_out(self.smem(sa, a), self.refl(a), True)
        mx = self.assume(self.member(x, S))
        x_is = self.iff_out(self.smem(sa, x), mx)

        def collapse(term_in):
            value_is = self.iff_out(self.smem(sa, self.parts(self.tokens(term_in))[0]), term_in)
            return self.trans(value_is, self.sym(x_is))

        left = collapse(self.algebra(1, sS, map_, a_in, mx, S=S, m=graph, x=a, y=x))
        right = collapse(self.algebra(1, sS, map_, mx, a_in, S=S, m=graph, y=a))
        identity = self.gen(self.close(mx, self.pair(left, right)), "x")
        self.algebra(14, semigroup, a_in, identity, S=S, m=graph, e=a)
        self.close_statement(16)

        empty = self.atom("∅")
        self.open_statement(17)
        given = self.assume(self.op("IsMonoid", empty, m, e))
        e_in = self.algebra(11, given, S=empty)
        contradiction = self.not_out(self.ui(self.cite(ZF[12]), e), e_in)
        self.not_in(self.close(given, contradiction))
        self.close_statement(17)
