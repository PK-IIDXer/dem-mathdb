"""Public relations and maps with set-valued graphs."""

from dem.db.seeds.public_product import ProductProofs, SLICE, SLICES
from dem.db.seeds.public_relation_definitions import DEFINITIONS, register_definitions
from dem.db.seeds.public_relations_data import COMPOSITION_STATEMENTS, PREIMAGE_STATEMENTS, RELATION_VALUES
from dem.db.seeds.public_relations_data import STATEMENTS
from dem.db.seeds.public_set_tools import PEIRCE, completed
from dem.db.seeds.public_zfc import THEOREM_NAMES as ZF

PACKAGE = "relations"
THEOREM_NAMES = (*(name for name, _, _ in (
    *STATEMENTS[4:20], *RELATION_VALUES, *PREIMAGE_STATEMENTS, *COMPOSITION_STATEMENTS,
)), SLICE, SLICES)
COMPREHENSION = "ZF内包項所属公理図式"
COMPREHENSION_EXTENSIONALITY = "ZF内包項外延性公理図式"


def seed_public_relations(session):
    names = tuple(name for name, *_ in DEFINITIONS[PACKAGE])
    if completed(session, THEOREM_NAMES, tuple(f"{name} 定義公理" for name in names), (), names):
        return
    register_definitions(session, PACKAGE)
    proofs = SetRelationProofs(session, PACKAGE)
    proofs.seed_subset()
    proofs.seed_product()
    proofs.seed_set_relations()
    proofs.seed_maps(16, "IsMap")
    proofs.seed_maximality(False)
    proofs.seed_empty_map()
    proofs.seed_values()
    proofs.seed_map_values()
    proofs.seed_preimages()
    proofs.seed_compositions()


class SetRelationProofs(ProductProofs):
    # 値:集合性 splits on whether the value is defined, by Peirce's law.
    extra_logic = {"peirce": PEIRCE}

    def seed_subset(self):
        a,b,c,x = map(self.atom, ("a", "b", "c", "x"))
        m = self.assume(self.member(x, a))
        self.subset_in(a, a, self.gen(self.close(m, m), "x"))
        self.prove(5)

        ab, bc = self.begin(6)
        m = self.assume(self.member(x, a))
        result = self.subset_at(bc, x, self.subset_at(ab, x, m))
        self.subset_in(a, c, self.gen(self.close(m, result), "x"))
        self.prove(6)

        sa, sb, ab, ba = self.begin(7)
        pointwise = self.subset_equivalence(ab, ba, x, a, b)
        ext = self.uis(self.ax("ZF外延性公理"), a, b)
        self.apply(ext, sa, sb, pointwise)
        self.prove(7)

        empty = self.atom("∅")
        no_element = self.ui(self.cite(ZF[12]), x)
        pointwise = self.gen(self.from_impossible_membership(self.member(x, empty), no_element, self.member(x, a)), "x")
        self.subset_in(empty, a, pointwise)
        self.prove(8)

    def relation_members(self, subset, product_membership, relation):
        q = self.atom("q")
        assumption = self.assume(self.member(q, relation))
        member = self.subset_at(subset, q, assumption)
        result = self.iff_out(self.ui(product_membership, q), member)
        return self.gen(self.close(assumption, result), "q")

    def seed_set_relations(self):
        X,Y,R,S,a,b,x,y,q,v = map(self.atom, ("X","Y","R","S","a","b","x","y","q","v"))
        sx, sy, sa, sb = self.begin(11)
        cartesian_product = self.op("×", X, Y)
        pair = self.ordered(a,b)
        iff = self.ui(self.named(10, sx, sy), pair)
        m = self.assume(self.member(pair, cartesian_product))
        ex = self.iff_out(iff, m)

        def coordinates(witness):
            mx, rest = self.left(witness), self.right(witness)
            my, eq = self.left(rest), self.right(rest)
            same = self.cite(ZF[10], terms={"c": x, "d": y},
                             args=(sa, sb, self.set_member(mx), self.set_member(my), eq))
            ma = self.transport(self.sym(self.left(same)), mx, "v", self.member(v,X))
            mb = self.transport(self.sym(self.right(same)), my, "v", self.member(v,Y))
            return self.pair(ma,mb)

        forward = self.close(m, self.using_witness(ex, "x", lambda e: self.using_witness(e, "y", coordinates)))
        m = self.assume(self.conj(self.member(a,X), self.member(b,Y)))
        ex = self.product_witness(pair,X,Y,a,b,self.left(m),self.right(m),self.refl(pair))
        reverse = self.close(m, self.iff_out(iff,ex,True))
        self.iff_in(forward, reverse)
        self.prove(11)

        sx, sy, rel = self.begin(12)
        subset = self.right(self.iff_out(self.definition("IsRelation",R,X,Y),rel))
        self.relation_members(subset, self.named(10, sx, sy), R)
        self.prove(12)

        sx, sy = self.begin(13)
        pset = self.named(9, sx, sy)
        self.iff_out(self.definition("IsRelation",cartesian_product,X,Y),
                     self.pair(pset,self.named(5,a=cartesian_product)),True)
        self.prove(13)

        empty = self.atom("∅")
        self.iff_out(self.definition("IsRelation",empty,X,Y),
                     self.pair(self.cite(ZF[11]),self.named(8,a=cartesian_product)),True)
        self.prove(14)

        sx, sy, rel_r, rel_s, agreement = self.begin(15)
        members_r = self.named(12, sx, sy, rel_r)
        members_s = self.named(12, sx, sy, rel_s, R=S)
        forward = self.relation_inclusion(R,S,members_r,agreement)
        reverse = self.relation_inclusion(S,R,members_s,agreement,reverse=True)
        set_r = self.left(self.iff_out(self.definition("IsRelation",R,X,Y),rel_r))
        set_s = self.left(self.iff_out(self.definition("IsRelation",S,X,Y),rel_s))
        self.named(7, set_r, set_s, forward, reverse, a=R, b=S)
        self.prove(15)

    def relation_inclusion(self, source, target, members, agreement, *, reverse=False):
        q,x,y,v = map(self.atom, ("q","x","y","v"))
        membership = self.assume(self.member(q,source))
        exists = self.mp(self.ui(members,q),membership)

        def transfer(witness):
            mx,rest = self.left(witness),self.right(witness)
            my,eq = self.left(rest),self.right(rest)
            pair_member = self.transport(eq,membership,"v",self.member(v,source))
            same = self.apply(self.uis(agreement,x,y),mx,my)
            result = self.iff_out(same,pair_member,reverse)
            return self.transport(self.sym(eq),result,"v",self.member(v,target))

        result = self.using_witness(exists,"x",lambda e:self.using_witness(e,"y",transfer))
        return self.subset_in(source,target,self.gen(self.close(membership,result),"q"))

    def map_parts(self, kind, graph, X, Y, membership):
        return self.iff_out(self.definition(kind, graph, X, Y), membership)

    def value(self, graph, Y, argument, result):
        f,x,y = graph,argument,result
        return self.conj(self.member(y,Y), self.member(self.ordered(x,y),f))

    def seed_maps(self, first, kind):
        f,X,Y,x,y,z,w = map(self.atom, ("f","X","Y","x","y","z","w"))
        given, = self.begin(first)
        self.left(self.map_parts(kind,f,X,Y,given))
        self.prove(first)

        given, = self.begin(first + 1)
        mx = self.assume(self.member(x,X))
        total = self.right(self.map_parts(kind,f,X,Y,given))
        unique = self.mp(self.ui(total,x),mx)
        pred = self.value(f,Y,x,w)
        existence = self.cite(STATEMENTS[1][0], {"φ¹": (pred, ("w",))}, args=(unique,))
        self.gen(self.close(mx,existence),"x")
        self.prove(first + 1)

        given, = self.begin(first + 2)
        xy,xz = self.ordered(x,y),self.ordered(x,z)
        mx,my,mz,mxy,mxz = (self.assume(t) for t in (
            self.member(x,X),self.member(y,Y),self.member(z,Y),self.member(xy,f),self.member(xz,f),
        ))
        total = self.right(self.map_parts(kind,f,X,Y,given))
        unique = self.mp(self.ui(total,x),mx)
        result = self.cite(STATEMENTS[2][0], {"φ¹": (pred, ("w",))}, {"t": z},
                           args=(unique, self.pair(my,mxy), self.pair(mz,mxz)))
        result = self.close_many((mx,my,mz,mxy,mxz),result)
        for name in ("z","y","x"):
            result = self.gen(result,name)
        self.prove(first + 2)

    def seed_empty_map(self):
        empty,X,Y,x,y = map(self.atom, ("∅","X","Y","x","y"))
        relation = self.named(14,X=empty)
        no = self.ui(self.cite(ZF[12]),x)
        target = self.quant("∃!","y",self.value(empty,Y,x,y))
        total = self.gen(self.from_impossible_membership(self.member(x,empty),no,target),"x")
        self.iff_out(self.definition("IsMap",empty,empty,Y),self.pair(relation,total),True)
        self.prove(20)

    def seed_maximality(self, class_map):
        X,Y,f,g,q,x,y,z,v = map(self.atom, ("X","Y","f","g","q","x","y","z","v"))
        index = 30 if class_map else 19
        *guards, fm, gm, fg = self.begin(index)
        relation = self.named(23 if class_map else 16, gm, f=g)
        members = self.named(27 if class_map else 12, *guards, relation, R=g)
        mq = self.assume(self.member(q,g))
        decomposition = self.mp(self.ui(members,q),mq)

        def from_pair(witness):
            mx,rest = self.left(witness),self.right(witness)
            my,eq = self.left(rest),self.right(rest)
            in_g = self.transport(eq,mq,"v",self.member(v,g))
            total = self.named(24 if class_map else 17, fm)
            exists = self.mp(self.ui(total,x),mx)

            def from_value(value):
                mz,in_f = self.left(value),self.right(value)
                pair = self.ordered(x,z)
                second_in_g = self.subset_at(fg,pair,in_f)
                unique = self.named(25 if class_map else 18, gm, f=g)
                same = self.apply(self.uis(unique,x,z,y),mx,mz,my,second_in_g,in_g)
                in_f = self.transport(same,in_f,"v",self.member(self.ordered(x,v),f))
                return self.transport(self.sym(eq),in_f,"v",self.member(v,f))

            return self.using_witness(exists,"z",from_value)

        in_f = self.using_witness(decomposition,"x",lambda w:self.using_witness(w,"y",from_pair))
        gf = self.subset_in(g,f,self.gen(self.close(mq,in_f),"q"))
        if class_map:
            same = self.subset_equivalence(fg,gf,x,f,g)
            self.mp(self.uis(self.ax("MK類外延性公理"),f,g),same)
        else:
            sf = self.left(self.iff_out(self.definition("IsRelation",f,X,Y),self.named(16, fm)))
            sg = self.left(self.iff_out(self.definition("IsRelation",g,X,Y),relation))
            self.named(7, sf, sg, fg, gf, a=f, b=g)
        self.prove(index)

    def value_condition(self, f, x, value):
        return self.conj(self.isset(value), self.member(self.ordered(x, value), f))

    def value_term(self, f, x):
        definition = self.definition("ev", f, x)
        term = self.parts(self.tokens(definition))[1]
        return definition, term, self.opened(term, "z")

    def seed_values(self):
        f,x,y,z,u,w,v = map(self.atom, ("f","x","y","z","u","w","v"))
        bottom = self.atom("⊥")

        sx, sy, pair_in, unique = self.begin(31)
        definition, term, body = self.value_term(f, x)
        found = self.parts(body)[1]

        def member_of_value(member):
            def from_witness(witness):
                rest = self.right(witness)
                same = self.mp(self.ui(self.left(self.right(rest)), y), self.pair(sy, pair_in))
                return self.transport(self.sym(same), self.right(self.right(rest)), "v", self.member(z, v))
            return self.using_witness(self.right(member), "u", from_witness)

        def value_member(member):
            fact = self.pair(sy, self.pair(pair_in, self.pair(unique, member)))
            return self.pair(sx, self.ei(fact, "u", self.opened(found, "u"), y))

        restricted_body = self.conj(self.member(z, y), body)
        separated = self.mp(self.ui(self.ax("ZF分出公理図式", {"φ¹": (body, ("z",))}), y), sy)
        forward = self.by_assumption(body, lambda m: self.pair(member_of_value(m), m))
        reverse = self.by_assumption(restricted_body, self.right)
        restricted = self.mp(self.ax(COMPREHENSION_EXTENSIONALITY, {
            "φ¹": (body, ("z",)), "ψ¹": (restricted_body, ("z",)),
        }), self.gen(self.iff_in(forward, reverse), "z"))
        term_set = self.transport(self.sym(restricted), separated, "v", self.isset(v))
        criterion = self.comprehension("z", body, z, axiom=COMPREHENSION, sethood=term_set)
        forward = self.by_assumption(self.member(z, term),
                                     lambda m: member_of_value(self.right(self.iff_out(criterion, m))))
        reverse = self.by_assumption(self.member(z, y), lambda m: self.iff_out(
            criterion, self.pair(self.element(self.set_member(m)), value_member(m)), True))
        pointwise = self.gen(self.iff_in(forward, reverse), "z")
        equal = self.apply(self.uis(self.ax("ZF外延性公理"), term, y), term_set, sy, pointwise)
        self.trans(definition, equal)
        self.prove(31)

        undefined, = self.begin(32)
        definition, term, body = self.value_term(f, x)
        condition = (self.value_condition(f, x, v), ("v",))

        def refute(member):
            def from_witness(witness):
                rest = self.right(witness)
                satisfied = self.pair(self.left(witness), self.left(rest))
                unique = self.cite(STATEMENTS[0][0], {"φ¹": condition}, {"t": u},
                                   args=(satisfied, self.left(self.right(rest))))
                return self.not_out(undefined, self.pair(self.left(member), unique))
            return self.using_witness(self.right(member), "u", from_witness)

        forward = self.by_assumption(body, refute)
        reverse = self.by_assumption(bottom, lambda m: self.mp(self.ax("false", {"φ": body}), m))
        empty_term = self.mp(self.ax(COMPREHENSION_EXTENSIONALITY, {
            "φ¹": (body, ("z",)), "ψ¹": (bottom, ("z",)),
        }), self.gen(self.iff_in(forward, reverse), "z"))
        self.trans(self.trans(definition, empty_term), self.sym(self.definition("∅")))
        self.prove(32)

        self.begin(33)
        target = self.isset(self.op("ev", f, x))
        refuted = self.assume(self.imp(target, bottom))
        defined = self.conj(self.isset(x), self.quant("∃!", "y", self.value_condition(f, x, y)))

        def contradiction(assumption):
            sx, unique = self.left(assumption), self.right(assumption)
            exists = self.cite(STATEMENTS[1][0], {"φ¹": condition}, args=(unique,))

            def from_witness(witness):
                other = self.assume(self.value_condition(f, x, w))
                same = self.cite(STATEMENTS[2][0], {"φ¹": condition}, {"y": w, "t": u},
                                 args=(unique, other, witness))
                uniqueness = self.gen(self.close(other, same), "w")
                equal = self.named(31, sx, self.left(witness), self.right(witness), uniqueness, y=u)
                sethood = self.transport(self.sym(equal), self.left(witness), "v", self.isset(v))
                return self.mp(refuted, sethood)

            return self.using_witness(exists, "u", from_witness)

        empty = self.named(32, self.not_in(self.by_assumption(defined, contradiction)))
        sethood = self.transport(self.sym(empty), self.cite("ZF:空集合の集合性"), "v", self.isset(v))
        self.mp(self.ax("peirce", {"φ": target, "ψ": bottom}), self.close(refuted, sethood))
        self.prove(33)

    def map_value_uniqueness(self, sets, map_, f, X, Y, x, y, belongs, value_belongs, pair_in):
        w = self.atom("w")
        other = self.assume(self.value_condition(f, x, w))
        relation = self.named(16, map_)
        subset = self.right(self.iff_out(self.definition("IsRelation", f, X, Y), relation))
        in_product = self.subset_at(subset, self.ordered(x, w), self.right(other))
        coordinates = self.named(11, *sets, self.set_member(belongs), self.left(other), a=x, b=w)
        other_belongs = self.right(self.iff_out(coordinates, in_product))
        same = self.apply(self.uis(self.named(18, map_), x, w, y),
                          belongs, other_belongs, value_belongs, self.right(other), pair_in)
        return self.gen(self.close(other, same), "w")

    def value_of_graph(self, belongs, value_belongs, pair_in, unique):
        return self.named(31, self.set_member(belongs), self.set_member(value_belongs), pair_in, unique)

    def value_predicate(self, f, Y, x):
        v = self.atom("v")
        return self.conj(self.member(v, Y), self.member(self.ordered(x, v), f))

    def seed_map_values(self):
        f,X,Y,x,y = map(self.atom, ("f","X","Y","x","y"))
        sX, sY, map_, belongs = self.begin(34)
        exists = self.mp(self.ui(self.named(17, map_), x), belongs)

        def from_value(value):
            value_belongs, pair_in = self.left(value), self.right(value)
            unique = self.map_value_uniqueness((sX, sY), map_, f, X, Y, x, y, belongs, value_belongs, pair_in)
            equal = self.value_of_graph(belongs, value_belongs, pair_in, unique)
            return self.transport(self.sym(equal), value, "v", self.value_predicate(f, Y, x))

        self.using_witness(exists, "y", from_value)
        self.prove(34)

        sX, sY, map_, belongs = self.begin(35)

        def forward(value):
            value_belongs, pair_in = self.left(value), self.right(value)
            unique = self.map_value_uniqueness((sX, sY), map_, f, X, Y, x, y, belongs, value_belongs, pair_in)
            return self.value_of_graph(belongs, value_belongs, pair_in, unique)

        def reverse(equal):
            return self.transport(equal, self.named(34, sX, sY, map_, belongs), "v", self.value_predicate(f, Y, x))

        graph = self.conj(self.member(y, Y), self.member(self.ordered(x, y), f))
        self.iff_in(self.by_assumption(graph, forward),
                    self.by_assumption(self.eq(self.op("ev", f, x), y), reverse))
        self.prove(35)

    def seed_preimages(self):
        f, a, X, Y, x, y, v = map(self.atom, ("f", "a", "X", "Y", "x", "y", "v"))
        preimage = self.op("Preimage", f, a)
        evaluated = self.op("ev", f, x)
        in_domain = self.member(x, X)
        in_preimage = self.member(x, preimage)
        in_target = self.member(evaluated, a)

        def opened_definition():
            definition = self.definition("Preimage", f, a)
            return definition, self.opened(self.parts(self.tokens(definition))[1], "x")

        def coordinates_for(sX, sY, map_):
            relation = self.named(16, map_)
            subset = self.right(self.iff_out(self.definition("IsRelation", f, X, Y), relation))

            def coordinates(set_x, witness):
                in_product = self.subset_at(subset, self.ordered(x, y), self.right(witness))
                criterion = self.named(11, sX, sY, set_x, self.set_member(self.left(witness)), a=x, b=y)
                return self.iff_out(criterion, in_product)

            return coordinates

        # Sethood comes from separation on X: every member of the preimage lies in X.
        sX, sY, map_ = self.begin(37)
        definition, body = opened_definition()
        coordinates = coordinates_for(sX, sY, map_)

        def restrict(condition):
            belongs = self.using_witness(
                self.right(condition), "y", lambda w: self.left(coordinates(self.left(condition), w)),
            )
            return self.pair(belongs, condition)

        restricted = self.conj(in_domain, body)
        pointwise = self.iff_in(self.by_assumption(body, restrict), self.by_assumption(restricted, self.right))
        equal = self.mp(self.ax(COMPREHENSION_EXTENSIONALITY, {
            "φ¹": (body, ("x",)), "ψ¹": (restricted, ("x",)),
        }), self.gen(pointwise, "x"))
        separated = self.mp(self.ui(self.ax("ZF分出公理図式", {"φ¹": (body, ("x",))}), X), sX)
        term_set = self.transport(self.sym(equal), separated, "v", self.isset(v))
        self.transport(self.sym(definition), term_set, "v", self.isset(v))
        self.prove(37)

        # The ZF comprehension axiom applies once the term is known to be a set.
        sX, sY, map_ = self.begin(38)
        definition, body = opened_definition()
        witness_body = self.opened(self.parts(body)[1], "y")
        coordinates = coordinates_for(sX, sY, map_)
        term_set = self.transport(definition, self.named(37, sX, sY, map_), "v", self.isset(v))
        comprehension = self.comprehension("x", body, x, axiom=COMPREHENSION, sethood=term_set)
        membership = self.iff(self.member(x, v), self.conj(self.exists_member(x), body))
        criterion = self.transport(self.sym(definition), comprehension, "v", membership)

        def forward(member):
            condition = self.right(self.iff_out(criterion, member))

            def from_pair(witness):
                xy = coordinates(self.left(condition), witness)
                belongs = self.left(xy)
                graph = self.pair(self.right(xy), self.right(witness))
                value = self.iff_out(self.named(35, sX, sY, map_, belongs), graph)
                return self.pair(belongs, self.transport(self.sym(value), self.left(witness), "v", self.member(v, a)))

            return self.using_witness(self.right(condition), "y", from_pair)

        def reverse(condition):
            belongs = self.left(condition)
            set_x = self.set_member(belongs)
            graph = self.right(self.named(34, sX, sY, map_, belongs))
            witness = self.ei(self.pair(self.right(condition), graph), "y", witness_body, evaluated)
            return self.iff_out(criterion, self.pair(self.element(set_x), self.pair(set_x, witness)), True)

        self.iff_in(self.by_assumption(in_preimage, forward),
                    self.by_assumption(self.conj(in_domain, in_target), reverse))
        self.prove(38)

        sX, sY, map_ = self.begin(39)
        criterion = self.named(38, sX, sY, map_)
        pointwise = self.by_assumption(in_preimage, lambda m: self.left(self.iff_out(criterion, m)))
        self.subset_in(preimage, X, self.gen(pointwise, "x"))
        self.prove(39)

    def graph_subset(self, map_, f, X, Y):
        relation = self.named(16, map_, f=f, X=X, Y=Y)
        return self.right(self.iff_out(self.definition("IsRelation", f, X, Y), relation))

    def pair_coordinates(self, sets, subset, a, b, set_a, set_b, membership, X, Y):
        in_product = self.subset_at(subset, self.ordered(a, b), membership)
        criterion = self.named(11, *sets, set_a, set_b, X=X, Y=Y, a=a, b=b)
        return self.iff_out(criterion, in_product)

    def composition_witness(self, witness):
        # IsSet(x) ∧ (IsSet(y) ∧ (IsSet(z) ∧ (q = ⟨x, z⟩ ∧ (⟨x, y⟩ ∈ f ∧ ⟨y, z⟩ ∈ g))))
        parts = []
        for _ in range(4):
            parts.append(self.left(witness))
            witness = self.right(witness)
        return (*parts, self.left(witness), self.right(witness))

    def composite_value(self, maps, belongs):
        # ev(g, ev(f, x)) lies in Z and the pair ⟨x, ev(g, ev(f, x))⟩ lies in g ∘ f.
        sX, sY, sZ, mf, mg = maps
        f, g, x, y, Y = map(self.atom, ("f", "g", "x", "y", "Y"))
        first = self.op("ev", f, x)
        result = self.op("ev", g, first)
        value_f = self.named(34, sX, sY, mf, belongs)
        in_y = self.left(value_f)
        value_g = self.named(34, sY, sZ, mg, in_y, f=g, X=Y, Y=self.atom("Z"), x=first)
        in_z = self.left(value_g)
        criterion = self.named(41, *maps, self.set_member(belongs), self.set_member(in_z), z=result)
        path = self.conj(self.member(y, Y), self.conj(
            self.member(self.ordered(x, y), f), self.member(self.ordered(y, result), g)))
        exists = self.ei(self.pair(in_y, self.pair(self.right(value_f), self.right(value_g))), "y", path, first)
        return self.pair(in_z, self.iff_out(criterion, exists, True))

    def seed_compositions(self):
        f, g, h, X, Y, Z, W = map(self.atom, ("f", "g", "h", "X", "Y", "Z", "W"))
        q, x, y, z, u, w, v = map(self.atom, ("q", "x", "y", "z", "u", "w", "v"))
        composite = self.op("∘", g, f)

        def opened_definition():
            definition = self.definition("∘", g, f)
            term = self.parts(self.tokens(definition))[1]
            return definition, term, self.opened(term, "q")

        # Every member of g ∘ f is a pair in X × Z, so separation on X × Z gives sethood.
        maps = self.begin(40)
        sX, sY, sZ, mf, mg = maps
        definition, term, body = opened_definition()
        cartesian_product = self.op("×", X, Z)
        in_f, in_g = self.graph_subset(mf, f, X, Y), self.graph_subset(mg, g, Y, Z)

        def located(witness):
            sx, sy, sz, equal, xy, yz = self.composition_witness(witness)
            in_x = self.left(self.pair_coordinates((sX, sY), in_f, x, y, sx, sy, xy, X, Y))
            in_z = self.right(self.pair_coordinates((sY, sZ), in_g, y, z, sy, sz, yz, Y, Z))
            pair_in = self.iff_out(self.named(11, sX, sZ, sx, sz, Y=Z, a=x, b=z), self.pair(in_x, in_z), True)
            return self.transport(self.sym(equal), pair_in, "v", self.member(v, cartesian_product))

        bounded = self.by_assumption(body, lambda condition: self.using_witness(
            condition, "x", lambda a: self.using_witness(a, "y", lambda b: self.using_witness(b, "z", located))))
        restricted = self.conj(self.member(q, cartesian_product), body)
        pointwise = self.iff_in(self.by_assumption(body, lambda c: self.pair(self.mp(bounded, c), c)),
                                self.by_assumption(restricted, self.right))
        equal = self.mp(self.ax(COMPREHENSION_EXTENSIONALITY, {
            "φ¹": (body, ("q",)), "ψ¹": (restricted, ("q",)),
        }), self.gen(pointwise, "q"))
        separated = self.mp(self.ui(self.ax("ZF分出公理図式", {"φ¹": (body, ("q",))}), cartesian_product),
                            self.named(9, sX, sZ, Y=Z))
        term_set = self.transport(self.sym(equal), separated, "v", self.isset(v))
        criterion = self.comprehension("q", body, q, axiom=COMPREHENSION, sethood=term_set)

        def inside(member):
            unfolded = self.transport(definition, member, "v", self.member(q, v))
            return self.mp(bounded, self.right(self.iff_out(criterion, unfolded)))

        pointwise = self.gen(self.by_assumption(self.member(q, composite), inside), "q")
        subset = self.subset_in(composite, cartesian_product, pointwise)
        sethood = self.transport(self.sym(definition), term_set, "v", self.isset(v))
        self.iff_out(self.definition("IsRelation", composite, X, Z), self.pair(sethood, subset), True)
        self.prove(40)

        # Membership of a pair, once the composite is known to be a set.
        *maps, sx, sz = self.begin(41)
        sX, sY, sZ, mf, mg = maps
        definition, term, body = opened_definition()
        relation = self.named(40, *maps)
        sethood = self.left(self.iff_out(self.definition("IsRelation", composite, X, Z), relation))
        term_set = self.transport(definition, sethood, "v", self.isset(v))
        pair = self.ordered(x, z)
        comprehension = self.comprehension("q", body, pair, axiom=COMPREHENSION, sethood=term_set)
        unfolded = self.parts(self.tokens(comprehension))[1]
        criterion = self.transport(self.sym(definition), comprehension, "v", self.iff(self.member(pair, v), unfolded))
        in_f = self.graph_subset(mf, f, X, Y)
        path = self.conj(self.member(y, Y), self.conj(
            self.member(self.ordered(x, y), f), self.member(self.ordered(y, z), g)))

        def found(witness):
            su, sy, sw, equal, uy, yw = self.composition_witness(witness)
            same = self.cite(ZF[10], terms={"a": x, "b": z, "c": u, "d": w}, args=(sx, sz, su, sw, equal))
            xy = self.transport(self.sym(self.left(same)), uy, "v", self.member(self.ordered(v, y), f))
            yz = self.transport(self.sym(self.right(same)), yw, "v", self.member(self.ordered(y, v), g))
            in_y = self.right(self.pair_coordinates((sX, sY), in_f, x, y, sx, sy, xy, X, Y))
            return self.ei(self.pair(in_y, self.pair(xy, yz)), "y", path, y)

        def forward(member):
            condition = self.right(self.iff_out(criterion, member))
            return self.using_witness(condition, "u", lambda a: self.using_witness(
                a, "y", lambda b: self.using_witness(b, "w", found)))

        witnessed = self.parts(unfolded)[1]
        at_x = self.opened(witnessed, "x")
        at_y = self.opened(at_x, "y")

        def build(witness):
            in_y, rest = self.left(witness), self.right(witness)
            xy, yz = self.left(rest), self.right(rest)
            guard = self.pair(sx, self.pair(self.set_member(in_y), self.pair(sz, self.pair(
                self.refl(pair), self.pair(xy, yz)))))
            exists = self.ei(guard, "w", self.opened(at_y, "w"), z)
            exists = self.ei(exists, "y", at_y, y)
            exists = self.ei(exists, "u", self.opened(witnessed, "u"), x)
            return self.iff_out(criterion, self.pair(self.pair_element(x, z), exists), True)

        exists_path = self.some("y", path)
        self.iff_in(self.by_assumption(self.member(pair, composite), forward),
                    self.by_assumption(exists_path, lambda e: self.using_witness(e, "y", build)))
        self.prove(41)

        # Each x in X has exactly one image ev(g, ev(f, x)) under g ∘ f.
        maps = self.begin(42)
        sX, sY, sZ, mf, mg = maps
        belongs = self.assume(self.member(x, X))
        result = self.op("ev", g, self.op("ev", f, x))
        holds = self.composite_value(maps, belongs)
        candidate = self.assume(self.conj(self.member(w, Z), self.member(self.ordered(x, w), composite)))
        set_x = self.set_member(belongs)
        decomposed = self.iff_out(self.named(41, *maps, set_x, self.set_member(self.left(candidate)), z=w),
                                  self.right(candidate))

        def agrees(witness):
            in_y, rest = self.left(witness), self.right(witness)
            xy, yw = self.left(rest), self.right(rest)
            first = self.iff_out(self.named(35, sX, sY, mf, belongs), self.pair(in_y, xy))
            second = self.iff_out(self.named(35, sY, sZ, mg, in_y, f=g, X=Y, Y=Z, x=y, y=w),
                                  self.pair(self.left(candidate), yw))
            moved = self.transport(self.sym(first), second, "v", self.eq(self.op("ev", g, v), w))
            return self.sym(moved)

        unique = self.gen(self.close(candidate, self.using_witness(decomposed, "y", agrees)), "w")
        image = (self.conj(self.member(v, Z), self.member(self.ordered(x, v), composite)), ("v",))
        exists_unique = self.cite(STATEMENTS[0][0], {"φ¹": image}, {"t": result}, args=(holds, unique))
        total = self.gen(self.close(belongs, exists_unique), "x")
        self.iff_out(self.definition("IsMap", composite, X, Z), self.pair(self.named(40, *maps), total), True)
        self.prove(42)

        *maps, belongs = self.begin(43)
        sX, sY, sZ, mf, mg = maps
        result = self.op("ev", g, self.op("ev", f, x))
        holds = self.composite_value(maps, belongs)
        graph = self.named(35, sX, sZ, self.named(42, *maps), belongs, f=composite, Y=Z, y=result)
        self.iff_out(graph, holds)
        self.prove(43)

        # Both sides are maps from X to W with the same values, so one contains the other.
        sX, sY, sZ, sW, mf, mg, mh = self.begin(44)
        inner, outer = composite, self.op("∘", h, g)
        left_side, right_side = self.op("∘", h, inner), self.op("∘", outer, f)
        map_inner = self.named(42, sX, sY, sZ, mf, mg)
        map_outer = self.named(42, sY, sZ, sW, mg, mh, f=g, g=h, X=Y, Y=Z, Z=W)
        map_left = self.named(42, sX, sZ, sW, map_inner, mh, f=inner, g=h, Y=Z, Z=W)
        map_right = self.named(42, sX, sY, sW, mf, map_outer, g=outer, Z=W)
        members = self.named(12, sX, sW, self.named(16, map_left, f=left_side, Y=W), R=left_side, Y=W)
        member = self.assume(self.member(q, left_side))
        decomposition = self.mp(self.ui(members, q), member)

        def transfer(witness):
            belongs, rest = self.left(witness), self.right(witness)
            in_w, equal = self.left(rest), self.right(rest)
            in_left = self.transport(equal, member, "v", self.member(v, left_side))
            value_left = self.iff_out(self.named(35, sX, sW, map_left, belongs, f=left_side, Y=W),
                                      self.pair(in_w, in_left))
            first = self.op("ev", f, x)
            e1 = self.named(43, sX, sZ, sW, map_inner, mh, belongs, f=inner, g=h, Y=Z, Z=W)
            e2 = self.named(43, sX, sY, sZ, mf, mg, belongs)
            e3 = self.named(43, sX, sY, sW, mf, map_outer, belongs, g=outer, Z=W)
            in_y = self.left(self.named(34, sX, sY, mf, belongs))
            e4 = self.named(43, sY, sZ, sW, mg, mh, in_y, f=g, g=h, X=Y, Y=Z, Z=W, x=first)
            chain = self.trans(e3, e4)
            right_value = self.op("ev", right_side, x)
            chain = self.transport(self.sym(e2), chain, "v", self.eq(right_value, self.op("ev", h, v)))
            chain = self.trans(self.trans(chain, self.sym(e1)), value_left)
            graph = self.named(35, sX, sW, map_right, belongs, f=right_side, Y=W)
            in_right = self.right(self.iff_out(graph, chain, True))
            return self.transport(self.sym(equal), in_right, "v", self.member(v, right_side))

        moved = self.using_witness(decomposition, "x", lambda a: self.using_witness(a, "y", transfer))
        included = self.subset_in(left_side, right_side, self.gen(self.close(member, moved), "q"))
        self.named(19, sX, sW, map_left, map_right, included, f=left_side, g=right_side, Y=W)
        self.prove(44)
