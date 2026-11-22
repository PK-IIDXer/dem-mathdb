"""Public class relations and maps, with explicit MK dependencies."""

from dem.db.seeds.public_relation_definitions import DEFINITIONS, register_definitions
from dem.db.seeds.public_relations import SetRelationProofs
from dem.db.seeds.public_relations_data import CLASS_VALUES, STATEMENTS
from dem.db.seeds.public_set_tools import completed
from dem.db.seeds.public_zfc import THEOREM_NAMES as ZF

PACKAGE = "class-relations"
GRAPH_IMAGE = "類写像:集合を定義域とする類写像の順序対の像は集合"
THEOREM_NAMES = (*(name for name, _, _ in (*STATEMENTS[20:30], *CLASS_VALUES)), GRAPH_IMAGE)
COMPREHENSION = "MK類内包公理図式"
EXTENSIONALITY = "MK類外延性公理"


def seed_public_class_relations(session):
    names = tuple(name for name, *_ in DEFINITIONS[PACKAGE])
    if completed(session, THEOREM_NAMES, tuple(f"{name} 定義公理" for name in names), (), names):
        return
    register_definitions(session, PACKAGE)
    proofs = ClassRelationProofs(session, PACKAGE)
    proofs.seed_bridges()
    proofs.seed_maps(23, "IsClassMap")
    proofs.seed_class_members()
    proofs.seed_bounded_graphs()
    proofs.seed_graph_image()
    proofs.seed_graph_set()
    proofs.seed_maximality(True)
    proofs.seed_class_map_value()


class ClassRelationProofs(SetRelationProofs):
    def seed_class_map_value(self):
        f,X,Y,x,y,w,v = map(self.atom, ("f","X","Y","x","y","w","v"))
        class_map, belongs = self.begin(36)
        exists = self.mp(self.ui(self.named(24, class_map), x), belongs)

        def from_value(value):
            value_belongs, pair_in = self.left(value), self.right(value)
            other = self.assume(self.value_condition(f, x, w))
            subset = self.iff_out(self.definition("IsClassRelation", f, X, Y), self.named(23, class_map))
            pair = self.ordered(x, w)
            in_product = self.subset_at(subset, pair, self.right(other))
            decomposition = self.iff_out(self.ui(self.named(26), pair), in_product)

            def coordinates(witness):
                first, rest = self.left(witness), self.right(witness)
                second, equality = self.left(rest), self.right(rest)
                same = self.cite(ZF[10], terms={"a": x, "b": w}, args=(
                    self.set_member(belongs), self.left(other),
                    self.set_member(first), self.set_member(second), equality,
                ))
                return self.transport(self.sym(self.right(same)), second, "v", self.member(v, Y))

            other_belongs = self.using_witness(
                decomposition, "c", lambda e: self.using_witness(e, "d", coordinates))
            same = self.apply(self.uis(self.named(25, class_map), x, w, y),
                              belongs, other_belongs, value_belongs, self.right(other), pair_in)
            unique = self.gen(self.close(other, same), "w")
            equal = self.value_of_graph(belongs, value_belongs, pair_in, unique)
            return self.transport(self.sym(equal), value, "v", self.value_predicate(f, Y, x))

        self.using_witness(exists, "y", from_value)
        self.prove(36)

    def seed_bridges(self):
        R,X,Y,f = map(self.atom, ("R","X","Y","f"))
        relation = self.definition("IsRelation",R,X,Y)
        class_relation = self.definition("IsClassRelation",R,X,Y)
        forward = self.assume(self.op("IsRelation",R,X,Y))
        expanded = self.iff_out(relation,forward)
        class_rel = self.iff_out(class_relation,self.right(expanded),True)
        forward = self.close(forward,self.pair(self.left(expanded),class_rel))
        reverse = self.assume(self.conj(self.isset(R),self.op("IsClassRelation",R,X,Y)))
        subset = self.iff_out(class_relation,self.right(reverse))
        reverse = self.close(reverse,self.iff_out(relation,self.pair(self.left(reverse),subset),True))
        self.iff_in(forward,reverse)
        self.prove(21)

        fmap = self.definition("IsMap",f,X,Y)
        cmap = self.definition("IsClassMap",f,X,Y)
        bridge = self.named(21,R=f)
        forward = self.assume(self.op("IsMap",f,X,Y))
        expanded = self.iff_out(fmap,forward)
        both = self.iff_out(bridge,self.left(expanded))
        class_map = self.iff_out(cmap,self.pair(self.right(both),self.right(expanded)),True)
        forward = self.close(forward,self.pair(self.left(both),class_map))
        reverse = self.assume(self.conj(self.isset(f),self.op("IsClassMap",f,X,Y)))
        expanded = self.iff_out(cmap,self.right(reverse))
        relation = self.iff_out(bridge,self.pair(self.left(reverse),self.left(expanded)),True)
        reverse = self.close(reverse,self.iff_out(fmap,self.pair(relation,self.right(expanded)),True))
        self.iff_in(forward,reverse)
        self.prove(22)

    def seed_class_members(self):
        R,X,Y = map(self.atom, ("R","X","Y"))
        self.product_membership(COMPREHENSION)
        self.prove(26)
        rel, = self.begin(27)
        subset = self.iff_out(self.definition("IsClassRelation",R,X,Y),rel)
        self.relation_members(subset, self.named(26), R)
        self.prove(27)

    def seed_bounded_graphs(self):
        R,X,Y,q,v = map(self.atom, ("R","X","Y","q","v"))
        cartesian_product = self.op("×",X,Y)
        sx, sy, rel = self.begin(28)
        subset = self.iff_out(self.definition("IsClassRelation",R,X,Y),rel)
        product_set = self.named(9, sx, sy)
        separated = self.mp(self.ui(self.ax("ZF分出公理図式",{"φ¹":(self.member(q,R),("q",))}),cartesian_product),product_set)
        restricted = self.parts(self.tokens(separated))[0]
        condition = self.conj(self.member(q,cartesian_product),self.member(q,R))
        criterion = self.comprehension("q",condition,q,axiom=COMPREHENSION)
        member = self.assume(self.member(q,R))
        exists = self.element(self.set_member(member))
        in_product = self.subset_at(subset,q,member)
        forward = self.close(member,self.iff_out(criterion,self.pair(exists,self.pair(in_product,member)),True))
        reverse = self.by_assumption(self.member(q,restricted), lambda m: self.right(self.right(self.iff_out(criterion,m))))
        equivalent = self.gen(self.iff_in(forward,reverse),"q")
        equality = self.mp(self.uis(self.ax(EXTENSIONALITY),R,restricted),equivalent)
        sethood = self.transport(self.sym(equality),separated,"v",self.isset(v))
        self.iff_out(self.named(21), self.pair(sethood,rel), True)
        self.prove(28)

    def image_predicate(self, x, q):
        h,f,Y = map(self.atom, ("h","f","Y"))
        p = self.ordered(x,h)
        return self.some("h",self.conj(self.member(h,Y),self.conj(self.member(p,f),self.eq(q,p))))

    def image_membership(self, X, q):
        x = self.atom("x")
        return self.some("x",self.conj(self.member(x,X),self.image_predicate(x,q)))

    def image_witness(self, x, q, y, my, member, equality):
        h = self.atom("h")
        p = self.ordered(x,h)
        body = self.conj(self.member(h,self.atom("Y")),self.conj(self.member(p,self.atom("f")),self.eq(q,p)))
        return self.ei(self.pair(my,self.pair(member,equality)),"h",body,y)

    def seed_graph_image(self):
        X,Y,f,x,y,z,q,w,v = map(self.atom, ("X","Y","f","x","y","z","q","w","v"))
        premises = (self.isset(X), self.op("IsClassMap", f, X, Y))
        sx, cmap = self.start(premises)

        def select_value(x, mx):
            existence = self.mp(self.ui(self.named(24, cmap),x),mx)
            value = self.assume(self.opened(self.tokens(existence),"y"))
            my, member = self.left(value),self.right(value)
            pair = self.ordered(x,y)
            element = self.pair_element(x,y)
            relation = self.image_witness(x,pair,y,my,member,self.refl(pair))
            possible, other = self.assume(self.exists_member(w)),self.assume(self.image_predicate(x,w))

            def compare(witness):
                mz, rest = self.left(witness),self.right(witness)
                in_graph, equality = self.left(rest),self.right(rest)
                unique = self.named(25, cmap)
                same = self.apply(self.uis(unique,x,z,y),mx,mz,my,in_graph,member)
                return self.transport(same,equality,"v",self.eq(w,self.ordered(x,v)))

            same = self.using_witness(other,"z",compare)
            unique = self.gen(self.close_many((possible,other),same),"w")
            return pair, element, relation, unique, existence, value

        # The choice of y must be discharged after introducing the image witness.
        belongs = self.assume(self.member(x,X))
        pair, element, relation, unique, existence, value = select_value(x,belongs)
        body = self.conj(self.exists_member(q),self.conj(self.image_predicate(x,q),self.all(
            "w",self.imp(self.exists_member(w),self.imp(self.image_predicate(x,w),self.eq(w,q))),
        )))
        result = self.ei(self.pair(element,self.pair(relation,unique)),"q",body,pair)
        total = self.gen(self.close(belongs,self.ee(existence,"y",value,result)),"x")
        replacement = self.ax("ZF置換公理図式",{"φ²":(self.image_predicate(x,q),("x","q"))})
        self.apply(self.ui(replacement,X),sx,total)
        self.finish(GRAPH_IMAGE,self.parse(
            "IsSet({|} q. ∃ x. (x ∈ X ∧ (∃ y. (y ∈ Y ∧ (⟨,⟩(x,y) ∈ f ∧ q = ⟨,⟩(x,y))))))",
        ), premises=premises)
        self.start()

    def seed_graph_set(self):
        X,Y,f,x,y,q,v = map(self.atom, ("X","Y","f","x","y","q","v"))
        sx, cmap = self.begin(29)
        image_set = self.cite(GRAPH_IMAGE, args=(sx, cmap))
        image = self.parts(self.tokens(image_set))[0]
        body = self.image_membership(X,q)
        criterion = self.comprehension("q",body,q,axiom=COMPREHENSION)
        mq = self.assume(self.member(q,f))
        relation = self.named(23, cmap)
        members = self.named(27, relation, R=f)
        exists = self.mp(self.ui(members,q),mq)

        def from_pair(witness):
            mx, rest = self.left(witness),self.right(witness)
            my, eq = self.left(rest),self.right(rest)
            member = self.transport(eq,mq,"v",self.member(v,f))
            in_image = self.image_witness(x,q,y,my,member,eq)
            return self.ei(self.pair(mx,in_image),"x",self.opened(body,"x"),x)

        in_image = self.using_witness(exists,"x",lambda e:self.using_witness(e,"y",from_pair))
        forward = self.close(mq,self.iff_out(criterion,self.pair(self.element(self.set_member(mq)),in_image),True))
        mq = self.assume(self.member(q,image))
        exists = self.right(self.iff_out(criterion,mq))

        def from_image(witness):
            rest = self.right(witness)
            return self.transport(self.sym(self.right(rest)),self.left(rest),"v",self.member(v,f))

        in_graph = self.using_witness(exists,"x",lambda w:self.using_witness(self.right(w),"y",from_image))
        same = self.gen(self.iff_in(forward,self.close(mq,in_graph)),"q")
        equality = self.mp(self.uis(self.ax(EXTENSIONALITY),f,image),same)
        sethood = self.transport(self.sym(equality),image_set,"v",self.isset(v))
        self.iff_out(self.named(22), self.pair(sethood,cmap), True)
        self.prove(29)
