"""Public relations and maps with set-valued graphs."""

from dem.db.seeds.public_product import ProductProofs, SLICE, SLICES
from dem.db.seeds.public_relation_definitions import DEFINITIONS, register_definitions
from dem.db.seeds.public_relations_data import STATEMENTS
from dem.db.seeds.public_set_tools import completed
from dem.db.seeds.public_zfc import THEOREM_NAMES as ZF

PACKAGE = "relations"
THEOREM_NAMES = (*(name for name, _ in STATEMENTS[4:20]), SLICE, SLICES)


def seed_public_relations(session):
    names = tuple(name for name, *_ in DEFINITIONS[PACKAGE])
    if completed(session, THEOREM_NAMES, tuple(f"{name} 定義公理" for name in names), (), names):
        return
    register_definitions(session, PACKAGE)
    proofs = SetRelationProofs(session, PACKAGE)
    proofs.seed_subset()
    proofs.seed_product()
    proofs.seed_set_relations()
    proofs.seed_maps(16, "IsMap", "IsRelation")
    proofs.seed_maximality(False)
    proofs.seed_empty_map()


class SetRelationProofs(ProductProofs):
    def seed_subset(self):
        a,b,c,x = map(self.atom, ("a", "b", "c", "x"))
        m = self.assume(self.member(x, a))
        self.prove(5, (), self.subset_in(a, a, self.gen(self.close(m, m), "x")))

        ab, bc = self.assume(self.subset(a, b)), self.assume(self.subset(b, c))
        m = self.assume(self.member(x, a))
        result = self.subset_at(bc, x, self.subset_at(ab, x, m))
        self.prove(6, (ab, bc), self.subset_in(a, c, self.gen(self.close(m, result), "x")))

        sa, sb, ab, ba = (self.assume(t) for t in (self.isset(a), self.isset(b), self.subset(a,b), self.subset(b,a)))
        pointwise = self.subset_equivalence(ab, ba, x, a, b)
        ext = self.uis(self.ax("ZF外延性公理"), a, b)
        self.prove(7, (sa, sb, ab, ba), self.apply(ext, sa, sb, pointwise))

        empty = self.atom("∅")
        no_element = self.ui(self.cite(ZF[12]), x)
        pointwise = self.gen(self.from_impossible_membership(self.member(x, empty), no_element, self.member(x, a)), "x")
        self.prove(8, (), self.subset_in(empty, a, pointwise))

    def relation_members(self, subset, product_membership, relation):
        q = self.atom("q")
        assumption = self.assume(self.member(q, relation))
        member = self.subset_at(subset, q, assumption)
        result = self.iff_out(self.ui(product_membership, q), member)
        return self.gen(self.close(assumption, result), "q")

    def seed_set_relations(self):
        X,Y,R,S,a,b,x,y,q,v = map(self.atom, ("X","Y","R","S","a","b","x","y","q","v"))
        sx,sy,sa,sb = (self.assume(self.isset(t)) for t in (X,Y,a,b))
        cartesian_product = self.op("×", X, Y)
        pair = self.ordered(a,b)
        iff = self.ui(self.apply(self.named(10), sx, sy), pair)
        m = self.assume(self.member(pair, cartesian_product))
        ex = self.iff_out(iff, m)

        def coordinates(witness):
            mx, rest = self.left(witness), self.right(witness)
            my, eq = self.left(rest), self.right(rest)
            same = self.apply(self.cite(ZF[10], terms={"c":x,"d":y}), sa, sb,
                              self.set_member(mx), self.set_member(my), eq)
            ma = self.transport(self.sym(self.left(same)), mx, "v", self.member(v,X))
            mb = self.transport(self.sym(self.right(same)), my, "v", self.member(v,Y))
            return self.pair(ma,mb)

        forward = self.close(m, self.using_witness(ex, "x", lambda e: self.using_witness(e, "y", coordinates)))
        m = self.assume(self.conj(self.member(a,X), self.member(b,Y)))
        ex = self.product_witness(pair,X,Y,a,b,self.left(m),self.right(m),self.refl(pair))
        reverse = self.close(m, self.iff_out(iff,ex,True))
        self.prove(11,(sx,sy,sa,sb),self.iff_in(forward,reverse))

        sx,sy,rel = (self.assume(t) for t in (self.isset(X),self.isset(Y),self.op("IsRelation",R,X,Y)))
        subset = self.right(self.iff_out(self.definition("IsRelation",R,X,Y),rel))
        self.prove(12,(sx,sy,rel),self.relation_members(subset,self.apply(self.named(10),sx,sy),R))

        sx,sy = self.assume(self.isset(X)),self.assume(self.isset(Y))
        pset = self.apply(self.named(9),sx,sy)
        self.prove(13,(sx,sy),self.iff_out(self.definition("IsRelation",cartesian_product,X,Y),
                                          self.pair(pset,self.named(5,a=cartesian_product)),True))

        empty = self.atom("∅")
        self.prove(14,(),self.iff_out(self.definition("IsRelation",empty,X,Y),
                                     self.pair(self.cite(ZF[11]),self.named(8,a=cartesian_product)),True))

        sx,sy,rel_r,rel_s = (self.assume(t) for t in (
            self.isset(X),self.isset(Y),self.op("IsRelation",R,X,Y),self.op("IsRelation",S,X,Y),
        ))
        ordered = self.ordered(x,y)
        agreement = self.assume(self.all("x",self.all("y",self.imp(self.member(x,X),self.imp(
            self.member(y,Y),self.iff(self.member(ordered,R),self.member(ordered,S)),
        )))))
        members_r = self.apply(self.named(12),sx,sy,rel_r)
        members_s = self.apply(self.named(12,R=S),sx,sy,rel_s)
        forward = self.relation_inclusion(R,S,members_r,agreement)
        reverse = self.relation_inclusion(S,R,members_s,agreement,reverse=True)
        set_r = self.left(self.iff_out(self.definition("IsRelation",R,X,Y),rel_r))
        set_s = self.left(self.iff_out(self.definition("IsRelation",S,X,Y),rel_s))
        result = self.apply(self.named(7,a=R,b=S),set_r,set_s,forward,reverse)
        self.prove(15,(sx,sy,rel_r,rel_s,agreement),result)

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

    def seed_maps(self, first, kind, relation):
        f,X,Y,x,y,z,w = map(self.atom, ("f","X","Y","x","y","z","w"))
        form = self.op(kind,f,X,Y)
        given = self.assume(form)
        self.prove(first,(given,),self.left(self.map_parts(kind,f,X,Y,given)))

        given, mx = self.assume(form), self.assume(self.member(x,X))
        total = self.right(self.map_parts(kind,f,X,Y,given))
        unique = self.mp(self.ui(total,x),mx)
        pred = self.value(f,Y,x,w)
        existence = self.mp(self.cite(STATEMENTS[1][0],{"φ¹":(pred,("w",))}),unique)
        self.prove(first+1,(given,),self.gen(self.close(mx,existence),"x"))

        given = self.assume(form)
        xy,xz = self.ordered(x,y),self.ordered(x,z)
        mx,my,mz,mxy,mxz = (self.assume(t) for t in (
            self.member(x,X),self.member(y,Y),self.member(z,Y),self.member(xy,f),self.member(xz,f),
        ))
        total = self.right(self.map_parts(kind,f,X,Y,given))
        unique = self.mp(self.ui(total,x),mx)
        uniqueness = self.cite(STATEMENTS[2][0],{"φ¹":(pred,("w",))},{"t":z})
        result = self.apply(uniqueness,unique,self.pair(my,mxy),self.pair(mz,mxz))
        result = self.close_many((mx,my,mz,mxy,mxz),result)
        for name in ("z","y","x"):
            result = self.gen(result,name)
        self.prove(first+2,(given,),result)

    def seed_empty_map(self):
        empty,X,Y,x,y = map(self.atom, ("∅","X","Y","x","y"))
        relation = self.named(14,X=empty)
        no = self.ui(self.cite(ZF[12]),x)
        target = self.quant("∃!","y",self.value(empty,Y,x,y))
        total = self.gen(self.from_impossible_membership(self.member(x,empty),no,target),"x")
        self.prove(20,(),self.iff_out(self.definition("IsMap",empty,empty,Y),self.pair(relation,total),True))

    def seed_maximality(self, class_map):
        X,Y,f,g,q,x,y,z,v = map(self.atom, ("X","Y","f","g","q","x","y","z","v"))
        kind = "IsClassMap" if class_map else "IsMap"
        assumptions = [] if class_map else [self.assume(self.isset(t)) for t in (X,Y)]
        fm,gm,fg = (self.assume(t) for t in (self.op(kind,f,X,Y),self.op(kind,g,X,Y),self.subset(f,g)))
        relation = self.mp(self.named(23 if class_map else 16,f=g),gm)
        members = self.apply(self.named(27 if class_map else 12,R=g),*assumptions,relation)
        mq = self.assume(self.member(q,g))
        decomposition = self.mp(self.ui(members,q),mq)

        def from_pair(witness):
            mx,rest = self.left(witness),self.right(witness)
            my,eq = self.left(rest),self.right(rest)
            in_g = self.transport(eq,mq,"v",self.member(v,g))
            total = self.mp(self.named(24 if class_map else 17),fm)
            exists = self.mp(self.ui(total,x),mx)

            def from_value(value):
                mz,in_f = self.left(value),self.right(value)
                pair = self.ordered(x,z)
                second_in_g = self.subset_at(fg,pair,in_f)
                unique = self.mp(self.named(25 if class_map else 18,f=g),gm)
                same = self.apply(self.uis(unique,x,z,y),mx,mz,my,second_in_g,in_g)
                in_f = self.transport(same,in_f,"v",self.member(self.ordered(x,v),f))
                return self.transport(self.sym(eq),in_f,"v",self.member(v,f))

            return self.using_witness(exists,"z",from_value)

        in_f = self.using_witness(decomposition,"x",lambda w:self.using_witness(w,"y",from_pair))
        gf = self.subset_in(g,f,self.gen(self.close(mq,in_f),"q"))
        if class_map:
            same = self.subset_equivalence(fg,gf,x,f,g)
            result = self.mp(self.uis(self.ax("MK類外延性公理"),f,g),same)
        else:
            sf = self.left(self.iff_out(self.definition("IsRelation",f,X,Y),self.mp(self.named(16),fm)))
            sg = self.left(self.iff_out(self.definition("IsRelation",g,X,Y),relation))
            result = self.apply(self.named(7,a=f,b=g),sf,sg,fg,gf)
        self.prove(30 if class_map else 19,(*assumptions,fm,gm,fg),result)

