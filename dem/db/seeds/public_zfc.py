"""Public ZF/ZFC data and independently constructed short proofs."""
from sqlalchemy import select
from dem.db.models import AxiomSystemMember, Symbol
from dem.errors import ValidationError
from dem.identity import public_id_from_key
from dem.services.symbol import SymbolService
from dem.services.formula import FormulaService
from dem.services.axiom import AxiomService
from dem.services.definition import DefinitionService, DefinitionPublicIdKeys
from dem.types import SymbolTypeName, FunctionDefinitionInput, AxiomStepInput
from dem.db.seeds.public_zfc_data import AXIOMS
from dem.db.seeds.public_set_tools import Builder, completed

SYSTEM_NAMES = ('ZF', 'ZFC')
THEOREM_NAMES = ('ZF:単集合の集合性', 'ZF:非順序対の集合性', 'ZF:順序対の集合性',
                 'ZF:単集合の所属', 'ZF:非順序対の所属', 'ZF:ラッセル',
                 'ZF:順序対の第一成分', 'ZF:順序対の成分範囲', 'ZF:対の共通成分消去',
                 'ZF:順序対の第二成分', 'ZF:順序対の成分一致')


def seed_public_zfc(session):
    if completed(session, THEOREM_NAMES, [a[0] for a in AXIOMS], SYSTEM_NAMES, ('{}','{,}','⟨,⟩')): return
    ss, fs, axs = SymbolService(session), FormulaService(session), AxiomService(session)
    for name, kind, arity, key, notation, precedence, latex, primitive in (
        ('∈', 'PREDICATE', 2, 'dem.foundation.logic::∈', 'infix', 50, r'#1 \in #2', True),
        ('IsSet', 'PREDICATE', 1, 'dem.lean.foundation::IsSet[zf]', 'prefix', None, r'\operatorname{IsSet}(#1)', True),
        ('{|}', 'QUANT_TERM', 1, 'dem.lean.foundation::{|}[zf]', 'prefix', None, r'\{#1 \mid #2\}', True),
        ('φ²', 'FREE_PROP_VAR', 2, 'dem.foundation.logic::φ²', 'prefix', None, None, False),
    ):
        row = ss.register(name, ss.get_symbol_type_by_name(SymbolTypeName[kind].value).id, arity,
                          is_primitive=primitive, notation_kind=notation, precedence=precedence,
                          public_id_key=key, latex_template=latex)
        if row.public_id != public_id_from_key('symbol', key): raise ValidationError('Shared symbol ID mismatch')
    for name in ('a', 'b', 'c', 'd', 'w', 'u', 'z', 'v', 'q', 'g', 'Z', 'r', 's', 'h', 'k'):
        if session.scalar(select(Symbol).where(Symbol.name == name)) is None:
            ss.register(name, ss.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value).id, 0,
                        public_id_key='dem.foundation.logic::'+name)
    for name, text, pid, digest in AXIOMS:
        formula = fs.register(fs.parse_text(text)[0])
        axiom = axs.register(name, formula.id, public_id_key='dem.lean.foundation::'+name,
                             description='Set-theory axiom schema supplied for the public foundation.')
        if axiom.public_id != pid or formula.hash != digest: raise ValidationError(f'Shared axiom identity mismatch: {name}')
    logic = axs.get_system_by_name('古典論理（同値つき）')
    base = list(session.scalars(select(AxiomSystemMember.axiom_id).where(AxiomSystemMember.axiom_system_id == logic.id)))
    for name in SYSTEM_NAMES:
        system = axs.register_system(name, public_id_key='dem.public.zfc::'+name,
                                     remarks='Pure sets with IsSet guards and comprehension terms.' + (' Choice included.' if name == 'ZFC' else ' Choice excluded.'))
        ids = [axs.get_by_name(a[0]).id for a in AXIOMS if name == 'ZFC' or a[0] != 'ZF選択公理']
        for ax in [*base, *ids]: axs.add_to_system(system.id, ax)
    defs = DefinitionService(session, authoring_via='seed')
    for name, params, text, latex in (
        ('{}', ('a',), '{|} x. x = a', r'\{#1\}'),
        ('{,}', ('a', 'b'), '{|} x. (x = a ∨ x = b)', r'\{#1,#2\}'),
        ('⟨,⟩', ('a', 'b'), '{,}({}(a), {,}(a, b))', r'\langle #1,#2\rangle'),
    ):
        key = 'dem.public.zfc::'+name
        defs.register(FunctionDefinitionInput(name, tuple(ss.get_by_name(p).id for p in params),
                                              fs.register(fs.parse_text(text)[0]).id,
                                              remarks='Explicit term abbreviation.', latex_template=latex),
                      public_id_keys=DefinitionPublicIdKeys(key, key, key))
    _Proofs(session, 'zfc').seed()


class _Proofs(Builder):
    def single(self, a): return self.op('{}', a)
    def unordered(self, a, b): return self.op('{,}', a, b)
    def ordered(self, a, b): return self.op('⟨,⟩', a, b)
    def definition(self, name, *terms):
        from dem.db.models import Definition
        service = DefinitionService(self.session)
        row = self.session.scalar(select(Definition).where(Definition.name == name))
        ax = service.get_axiom(row.id)
        return self.uis(self.line(AxiomStepInput(ax.id),
                                  self.ps._tokens_for_formula(ax.formula_id)), *terms)
    def set_single(self, a): return self.cite(THEOREM_NAMES[0], terms={'a': a})
    def set_pair(self, a, b): return self.cite(THEOREM_NAMES[1], terms={'a': a, 'b': b})
    def set_ordered(self, a, b): return self.cite(THEOREM_NAMES[2], terms={'a': a, 'b': b})
    def element(self, set_a):
        a = self.parts(self.tokens(set_a))[0]
        return self.mp(self.ui(self.ax('ZF集合元性公理'), a), set_a)
    def smem(self, set_a, x):
        a = self.parts(self.tokens(set_a))[0]
        return self.mp(self.cite(THEOREM_NAMES[3], terms={'a': a, 'x': x}), set_a)
    def pmem(self, set_a, set_b, x):
        a, b = self.parts(self.tokens(set_a))[0], self.parts(self.tokens(set_b))[0]
        return self.apply(self.cite(THEOREM_NAMES[4], terms={'a': a, 'b': b, 'x': x}), set_a, set_b)
    def inner_member(self, a, b, x, eq, sa, sb):
        # x=a or x=b supplies membership in {a,b}.
        disjunction = self.or_in(eq, self.eq(x, b))
        return self.iff_out(self.pmem(sa, sb, x), disjunction, True)
    def k_member(self, a, b, right=False):
        sa, sab = self.set_single(a), self.set_pair(a, b)
        one, two = self.single(a), self.unordered(a, b)
        chosen = two if right else one
        refl = self.refl(chosen)
        disjunction = self.or_in(refl, self.eq(chosen, one) if right else self.eq(chosen, two), right)
        mem = self.iff_out(self.pmem(sa, sab, chosen), disjunction, True)
        return self.transport(self.sym(self.definition('⟨,⟩', a, b)), mem, 'v', self.member(chosen, self.atom('v')))
    def k_choice(self, a, b, x, membership):
        mem = self.transport(self.definition('⟨,⟩', a, b), membership, 'v', self.member(x, self.atom('v')))
        return self.iff_out(self.pmem(self.set_single(a), self.set_pair(a, b), x), mem)
    def close_many(self, assumptions, result):
        for a in reversed(assumptions): result = self.close(a, result)
        return result

    def seed(self):
        a,b,c,d,x,v = [self.atom(n) for n in ('a','b','c','d','x','v')]
        # {x | x=a or x=a} = {x | x=a}, by pointwise equivalence.
        self.start()
        e = self.eq(x,a); union = self.disj(e,e)
        p = self.assume(union); l = self.assume(e); li = self.close(l,l)
        r = self.assume(e); ri = self.close(r,r)
        forward = self.close(p,self.cases(p,li,ri))
        p = self.assume(e); reverse = self.close(p,self.or_in(p,e))
        pointwise = self.gen(self.iff_in(forward,reverse),'x')
        comp_eq = self.mp(self.ax('ZF内包項外延性公理図式', {'φ¹': (union,('x',)), 'ψ¹':(e,('x',))}), pointwise)
        pair_set = self.uis(self.ax('ZF対公理'),a,a)
        singleton_comp_set = self.transport(comp_eq,pair_set,'v',self.isset(v))
        self.transport(self.sym(self.definition('{}',a)), singleton_comp_set,'v',self.isset(v))
        self.finish(THEOREM_NAMES[0],self.isset(self.single(a)), 'Singletons are sets without a guard on their argument.')

        self.start(); pair_set = self.uis(self.ax('ZF対公理'),a,b)
        self.transport(self.sym(self.definition('{,}',a,b)),pair_set,'v',self.isset(v))
        self.finish(THEOREM_NAMES[1],self.isset(self.unordered(a,b)), 'Unordered pairs are sets.')
        self.start(); s = self.set_pair(self.single(a),self.unordered(a,b))
        self.transport(self.sym(self.definition('⟨,⟩',a,b)),s,'v',self.isset(v))
        self.finish(THEOREM_NAMES[2],self.isset(self.ordered(a,b)), 'Kuratowski ordered pairs are sets.')

        for single in (True,False):
            self.start(); sa = self.assume(self.isset(a)); sb = None if single else self.assume(self.isset(b))
            body = self.eq(x,a) if single else self.disj(self.eq(x,a),self.eq(x,b))
            term = self.single(a) if single else self.unordered(a,b)
            name = '{}' if single else '{,}'; args = (a,) if single else (a,b)
            defined = self.definition(name,*args)
            st = self.transport(defined, self.set_single(a) if single else self.set_pair(a,b),'v',self.isset(v))
            raw = self.ui(self.mp(self.ax('ZF内包項所属公理図式',{'φ¹':(body,('x',))}),st),x)
            m = self.assume(self.member(x,term))
            opened = self.transport(defined,m,'v',self.member(x,v))
            fwd = self.close(m,self.right(self.iff_out(raw,opened)))
            p = self.assume(body)
            if single:
                ex = self.transport(self.sym(p),self.element(sa),'v',self.exists_member(v))
            else:
                ea = self.assume(self.eq(x,a)); xa = self.transport(self.sym(ea),self.element(sa),'v',self.exists_member(v)); la = self.close(ea,xa)
                eb = self.assume(self.eq(x,b)); xb = self.transport(self.sym(eb),self.element(sb),'v',self.exists_member(v)); lb = self.close(eb,xb)
                ex = self.cases(p,la,lb)
            mem = self.iff_out(raw,self.pair(ex,p),True)
            mem = self.transport(self.sym(defined),mem,'v',self.member(x,v))
            rev = self.close(p,mem)
            result = self.iff_in(fwd,rev)
            self.close_many([sa] if single else [sa,sb],result)
            self.finish(THEOREM_NAMES[3 if single else 4], description='Membership, guarded by sethood of the displayed elements.')

        self.start()
        russell = self.comp('x',self.neg(self.member(x,x)))
        s = self.assume(self.isset(russell))
        raw = self.ui(self.mp(self.ax('ZF内包項所属公理図式',{'φ¹':(self.neg(self.member(x,x)),('x',))}),s),russell)
        member = self.member(russell,russell)
        m = self.assume(member)
        no = self.right(self.iff_out(raw,m)); contradiction = self.not_out(no,m)
        no = self.not_in(self.close(m,contradiction))
        m = self.iff_out(raw,self.pair(self.element(s),no),True)
        self.not_in(self.close(s,self.not_out(no,m)))
        self.finish(THEOREM_NAMES[5],self.neg(self.isset(russell)), 'The Russell comprehension term is not a set.')
        self.injectivity()

    def injectivity(self):
        a,b,c,d,x,u,v = [self.atom(n) for n in ('a','b','c','d','x','u','v')]
        # Recover the first component from the singleton in the ordered pair.
        self.start(); guards = [self.assume(self.isset(t)) for t in (a,b,c,d)]; sa,sb,sc,sd = guards
        eq = self.assume(self.eq(self.ordered(a,b),self.ordered(c,d)))
        single_a = self.single(a)
        mem = self.transport(eq,self.k_member(a,b),'v',self.member(single_a,v))
        choice = self.k_choice(c,d,single_a,mem)
        branches=[]
        for right in (False,True):
            target = self.unordered(c,d) if right else self.single(c)
            e = self.assume(self.eq(single_a,target))
            cmem = self.iff_out(self.pmem(sc,sd,c),self.or_in(self.refl(c),self.eq(c,d)),True) if right else self.iff_out(self.smem(sc,c),self.refl(c),True)
            cmem = self.transport(self.sym(e),cmem,'v',self.member(c,v))
            ca = self.iff_out(self.smem(sa,c),cmem)
            branches.append(self.close(e,self.sym(ca)))
        result = self.cases(choice,*branches)
        self.close_many([*guards,eq],result); self.finish(THEOREM_NAMES[6])

        # Any member of a member of K(c,d) equals c or d.
        self.start(); sc,sd = [self.assume(self.isset(t)) for t in (c,d)]
        xu = self.assume(self.member(x,u)); uk = self.assume(self.member(u,self.ordered(c,d)))
        choice = self.k_choice(c,d,u,uk); branches=[]
        for right in (False,True):
            target = self.unordered(c,d) if right else self.single(c)
            e = self.assume(self.eq(u,target))
            m = self.transport(e,xu,'v',self.member(x,v))
            got = self.iff_out(self.pmem(sc,sd,x) if right else self.smem(sc,x),m)
            if not right: got = self.or_in(got,self.eq(x,d))
            branches.append(self.close(e,got))
        self.close_many([sc,sd,xu,uk],self.cases(choice,*branches)); self.finish(THEOREM_NAMES[7])

        # {a,b}={a,d} fixes the other component; stated using its two membership consequences.
        self.start(); p = self.assume(self.disj(self.eq(b,a),self.eq(b,d))); q = self.assume(self.disj(self.eq(d,a),self.eq(d,b)))
        ba = self.assume(self.eq(b,a)); da = self.assume(self.eq(d,a))
        branch1 = self.close(da,self.trans(ba,self.sym(da)))
        db = self.assume(self.eq(d,b)); branch2 = self.close(db,self.sym(db))
        left = self.close(ba,self.cases(q,branch1,branch2))
        bd = self.assume(self.eq(b,d)); right = self.close(bd,bd)
        self.close_many([p,q],self.cases(p,left,right)); self.finish(THEOREM_NAMES[8])

        self.start(); guards = [self.assume(self.isset(t)) for t in (a,b,c,d)]; sa,sb,sc,sd=guards
        eq = self.assume(self.eq(self.ordered(a,b),self.ordered(c,d)))
        ac = self.apply(self.cite(THEOREM_NAMES[6]),*guards,eq)
        def range_for(first,second,third,fourth,sfirst,ssecond,sthird,sfourth,equality):
            pair = self.unordered(first,second)
            member = self.iff_out(self.pmem(sfirst,ssecond,second),self.or_in(self.refl(second),self.eq(second,first),True),True)
            member_k = self.transport(equality,self.k_member(first,second,True),'v',self.member(pair,v))
            return self.apply(self.cite(THEOREM_NAMES[7],terms={'c':third,'d':fourth,'x':second,'u':pair}),sthird,sfourth,member,member_k)
        bd = range_for(a,b,c,d,sa,sb,sc,sd,eq)
        db = range_for(c,d,a,b,sc,sd,sa,sb,self.sym(eq))
        bd = self.transport(self.sym(ac),bd,'v',self.disj(self.eq(b,v),self.eq(b,d)))
        result = self.apply(self.cite(THEOREM_NAMES[8]),bd,db)
        self.close_many([*guards,eq],result); self.finish(THEOREM_NAMES[9])

        self.start(); guards = [self.assume(self.isset(t)) for t in (a,b,c,d)]
        eq = self.assume(self.eq(self.ordered(a,b),self.ordered(c,d)))
        first = self.apply(self.cite(THEOREM_NAMES[6]),*guards,eq)
        second = self.apply(self.cite(THEOREM_NAMES[9]),*guards,eq)
        self.close_many([*guards,eq],self.pair(first,second)); self.finish(THEOREM_NAMES[10])
