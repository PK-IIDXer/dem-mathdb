"""Public products of sets, from replacement and union."""

from dem.db.seeds.public_relation_proofs import RelationProofs


SLICE = "直積:順序対の片側の像の集合性"
SLICES = "直積:順序対の片側の像を集めた集合"
COMPREHENSION = "ZF内包項所属公理図式"


class ProductProofs(RelationProofs):
    def functional_replacement(self, domain, sethood, image, image_element):
        def select_value(x, belongs):
            value = image(x)
            w = self.atom("w")
            element = image_element(x, belongs)
            possible = self.assume(self.exists_member(w))
            equality = self.assume(self.eq(w, value))
            unique = self.gen(self.close_many((possible, equality), equality), "w")
            return value, element, self.refl(value), unique

        return self.replacement(domain, sethood, lambda x, q: self.eq(q, image(x)), select_value)

    def slice(self, X, b):
        r, k = map(self.atom, ("r", "k"))
        return self.comp("k", self.some("r", self.conj(self.member(r, X), self.eq(k, self.ordered(r, b)))))

    def slice_set(self, sx, belongs_y, y):
        return self.cite(SLICE, terms={"b": y}, args=(sx, self.set_member(belongs_y)))

    def slice_membership(self, X, y, q, sethood):
        return self.comprehension("q", self.opened(self.slice(X, y), "q"), q,
                                  axiom=COMPREHENSION, sethood=sethood)

    def seed_product(self):
        X, Y, b, q = map(self.atom, ("X", "Y", "b", "q"))
        premises = (self.isset(X), self.isset(b))
        sx, _ = self.start(premises)
        self.functional_replacement(
            X, sx, lambda x: self.ordered(x, b),
            lambda x, belongs: self.pair_element(x, b),
        )
        self.finish(SLICE, self.isset(self.slice(X, b)), premises=premises)

        premises = (self.isset(X), self.isset(Y))
        sx, sy = self.start(premises)
        self.functional_replacement(
            Y, sy, lambda y: self.slice(X, y),
            lambda y, belongs: self.element(self.slice_set(sx, belongs, y)),
        )
        self.finish(SLICES, self.parse(
            "IsSet({|} w. ∃ y. (y ∈ Y ∧ w = ({|} q. ∃ x. (x ∈ X ∧ q = ⟨,⟩(x,y)))))",
        ), premises=premises)

        sx, sy = self.begin(9)
        slices_set = self.cite(SLICES, args=(sx, sy))
        slices = self.parts(self.tokens(slices_set))[0]
        union_set = self.mp(self.ui(self.ax("ZF和集合公理"), slices), slices_set)
        union = self.parts(self.tokens(union_set))[0]
        union_body = self.opened(union, "q")
        product_body = self.product_body(q, X, Y)
        forward = self.by_assumption(union_body, lambda member: self.union_to_product(
            member, slices, slices_set, X, Y, sx, q,
        ))
        reverse = self.by_assumption(product_body, lambda member: self.product_to_union(
            member, union_body, slices, slices_set, X, Y, sx, q,
        ))
        same_members = self.gen(self.iff_in(forward, reverse), "q")
        equality = self.mp(self.ax("ZF内包項外延性公理図式", {
            "φ¹": (union_body, ("q",)), "ψ¹": (product_body, ("q",)),
        }), same_members)
        v = self.atom("v")
        result = self.transport(equality, union_set, "v", self.isset(v))
        self.transport(self.sym(self.definition("×", X, Y)), result, "v", self.isset(v))
        self.prove(9)

        sx, sy = self.begin(10)
        self.product_membership(COMPREHENSION, self.named(9, sx, sy))
        self.prove(10)

    def union_to_product(self, member, slices, slices_set, X, Y, sx, q):
        x, y, u, v = map(self.atom, ("x", "y", "u", "v"))

        def from_slice(witness):
            in_slices, in_slice = self.left(witness), self.right(witness)
            iff = self.comprehension("u", self.opened(slices, "u"), u, axiom=COMPREHENSION, sethood=slices_set)
            choices = self.right(self.iff_out(iff, in_slices))

            def from_y(witness):
                my, eq = self.left(witness), self.right(witness)
                in_y_slice = self.transport(eq, in_slice, "v", self.member(q, v))
                membership = self.slice_membership(X, y, q, self.slice_set(sx, my, y))
                members = self.right(self.iff_out(membership, in_y_slice))
                return self.using_witness(members, "x", lambda pair: self.product_witness(
                    q, X, Y, x, y, self.left(pair), my, self.right(pair),
                ))

            return self.using_witness(choices, "y", from_y)

        return self.using_witness(member, "u", from_slice)

    def product_to_union(self, member, union_body, slices, slices_set, X, Y, sx, q):
        x, y, u, h = map(self.atom, ("x", "y", "u", "h"))

        def from_pair(witness):
            mx, rest = self.left(witness), self.right(witness)
            my, eq = self.left(rest), self.right(rest)
            sliced = self.slice(X, y)
            in_slices_iff = self.comprehension("u", self.opened(slices, "u"), sliced,
                                               axiom=COMPREHENSION, sethood=slices_set)
            image = self.ei(self.pair(my, self.refl(sliced)), "h",
                            self.conj(self.member(h, Y), self.eq(sliced, self.slice(X, h))), y)
            sliced_set = self.slice_set(sx, my, y)
            in_slices = self.iff_out(in_slices_iff, self.pair(self.element(sliced_set), image), True)
            element = self.transport(self.sym(eq), self.pair_element(x, y), "v", self.exists_member(self.atom("v")))
            body = self.opened(self.opened(sliced, "q"), "x")
            in_slice_predicate = self.ei(self.pair(mx, eq), "x", body, x)
            in_slice = self.iff_out(self.slice_membership(X, y, q, sliced_set),
                                    self.pair(element, in_slice_predicate), True)
            return self.ei(self.pair(in_slices, in_slice), "u", self.opened(union_body, "u"), sliced)

        return self.using_witness(member, "x", lambda witness: self.using_witness(witness, "y", from_pair))



