"""Proof utilities for the public relations and maps packages."""

from dem.db.seeds.public_relations_data import STATEMENTS
from dem.db.seeds.public_zfc import _Proofs


class RelationProofs(_Proofs):
    extra_logic = {}

    def named(self, index, **terms):
        return self.cite(STATEMENTS[index - 1][0], terms=terms)

    def prove(self, index, assumptions, result):
        self.close_many(assumptions, result)
        name, text = STATEMENTS[index - 1]
        self.finish(name, self.parse(text))
        self.start()

    def using_witness(self, existential, variable, derive):
        witness = self.assume(self.opened(self.tokens(existential), variable))
        return self.ee(existential, variable, witness, derive(witness))

    def by_assumption(self, formula, derive):
        assumption = self.assume(formula)
        return self.close(assumption, derive(assumption))

    def subset(self, a, b):
        return self.op("⊂", a, b)

    def subset_at(self, included, element, membership):
        a, b = self.parts(self.tokens(included))
        expanded = self.iff_out(self.definition("⊂", a, b), included)
        return self.mp(self.ui(expanded, element), membership)

    def subset_in(self, a, b, pointwise):
        return self.iff_out(self.definition("⊂", a, b), pointwise, True)

    def set_member(self, membership):
        a, b = self.parts(self.tokens(membership))
        return self.mp(self.uis(self.ax("ZF純粋性公理"), a, b), membership)

    def comprehension(self, variable, predicate, element, *, axiom, sethood=None):
        expanded = self.ax(axiom, {"φ¹": (predicate, (variable,))})
        return self.ui(expanded if sethood is None else self.mp(expanded, sethood), element)

    def product_body(self, q, X, Y):
        x, y = self.atom("x"), self.atom("y")
        return self.some("x", self.some("y", self.conj(
            self.member(x, X), self.conj(self.member(y, Y), self.eq(q, self.ordered(x, y))),
        )))

    def product_witness(self, q, X, Y, a, b, belongs_a, belongs_b, equality):
        y = self.atom("y")
        inner = self.conj(self.member(a, X), self.conj(self.member(y, Y), self.eq(q, self.ordered(a, y))))
        exists_y = self.ei(self.pair(belongs_a, self.pair(belongs_b, equality)), "y", inner, b)
        return self.ei(exists_y, "x", self.opened(self.product_body(q, X, Y), "x"), a)

    def pair_element(self, a, b):
        return self.element(self.set_ordered(a, b))

    def expand_product(self, q, X, Y, *, axiom, sethood=None):
        body = self.product_body(self.atom("q"), X, Y)
        definition = self.definition("×", X, Y)
        v = self.atom("v")
        if sethood is not None:
            sethood = self.transport(definition, sethood, "v", self.isset(v))
        comprehension = self.comprehension("q", body, q, axiom=axiom, sethood=sethood)
        v = self.atom("v")
        predicate = self.iff(self.member(q, v), self.conj(self.exists_member(q), body))
        return self.transport(self.sym(definition), comprehension, "v", predicate)

    def product_membership(self, axiom, sethood=None):
        q, X, Y, x, y = map(self.atom, ("q", "X", "Y", "x", "y"))
        condition = self.product_body(q, X, Y)
        cartesian_product = self.member(q, self.op("×", X, Y))
        equivalence = self.expand_product(q, X, Y, axiom=axiom, sethood=sethood)
        forward = self.by_assumption(cartesian_product, lambda m: self.right(self.iff_out(equivalence, m)))

        def backwards(exists):
            def from_pair(witness):
                second = self.right(witness)
                element = self.pair_element(x, y)
                return self.transport(self.sym(self.right(second)), element, "v",
                                      self.exists_member(self.atom("v")))

            element = self.using_witness(exists, "x", lambda u: self.using_witness(u, "y", from_pair))
            return self.iff_out(equivalence, self.pair(element, exists), True)

        return self.gen(self.iff_in(forward, self.by_assumption(condition, backwards)), "q")

    def subset_equivalence(self, ab, ba, x, a, b):
        forward = self.by_assumption(self.member(x, a), lambda m: self.subset_at(ab, x, m))
        reverse = self.by_assumption(self.member(x, b), lambda m: self.subset_at(ba, x, m))
        return self.gen(self.iff_in(forward, reverse), "x")

    def exists_member(self, term):
        variable = "u" if self.symbols["w"].id in {t.symbol_id for t in term} else "w"
        return self.some(variable, self.member(term, self.atom(variable)))

    def replacement(self, domain, sethood, predicate, select_value):
        x, q, w = map(self.atom, ("x", "q", "w"))
        belongs = self.assume(self.member(x, domain))
        witness, element, relation, unique = select_value(x, belongs)
        body = self.conj(self.exists_member(q), self.conj(
            predicate(x, q), self.all("w", self.imp(
                self.exists_member(w), self.imp(predicate(x, w), self.eq(w, q)),
            )),
        ))
        exists = self.ei(self.pair(element, self.pair(relation, unique)), "q", body, witness)
        total = self.gen(self.close(belongs, exists), "x")
        rule = self.ax("ZF置換公理図式", {"φ²": (predicate(x, q), ("x", "q"))})
        return self.apply(self.ui(rule, domain), sethood, total)





