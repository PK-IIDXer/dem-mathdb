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
from dem.db.seeds.public_set_tools import Builder, PEIRCE, completed

SYSTEM_NAMES = ('ZF', 'ZFC')
EMPTY_SET_KEY = 'dem.lean.foundation::∅[zf]'
EMPTY_SET_IDENTITIES = (
    'c4ec1e44-7555-51f1-bfa8-2f757ad9368e',
    '0daf185d-cb58-57a3-8533-b9c3f7e46026',
    '9f77b3b7-3ffc-5dcd-b449-8fead94b5c75',
    '2b2a725cd37866d477ac02935ddf2b7e4077d54853f97a6ff23dc7841d84cd00',
)
THEOREM_NAMES = ('ZF:単集合の集合性', 'ZF:非順序対の集合性', 'ZF:順序対の集合性',
                 'ZF:単集合の所属', 'ZF:非順序対の所属', 'ZF:ラッセル',
                 'ZF:順序対の第一成分', 'ZF:順序対の成分範囲', 'ZF:対の共通成分消去',
                 'ZF:順序対の第二成分', 'ZF:順序対の成分一致',
                 'ZF:空集合の集合性', 'ZF:空集合は元を持たない',
                 'ZF:空集合の一意性', 'ZF:空でない集合は元を持つ',
                 'ZF:空集合は単集合でない')


def _register_empty_set(symbols, formulas, definitions):
    definition = definitions.register(
        FunctionDefinitionInput(
            '∅', (), formulas.register(formulas.parse_text('{|} x. ⊥')[0]).id,
            remarks='The comprehension term for the always-false predicate.',
            latex_template=r'\varnothing',
        ),
        public_id_keys=DefinitionPublicIdKeys(
            EMPTY_SET_KEY, EMPTY_SET_KEY, EMPTY_SET_KEY + ' 定義公理',
        ),
    )
    axiom = definitions.get_axiom(definition.id)
    actual = (
        symbols.get_by_name('∅').public_id, definition.public_id, axiom.public_id,
        formulas.get(axiom.formula_id).hash,
    )
    if actual != EMPTY_SET_IDENTITIES:
        raise ValidationError(f'Shared empty-set identity mismatch: {actual}')


def seed_public_zfc(session):
    if completed(session, THEOREM_NAMES, [a[0] for a in AXIOMS], SYSTEM_NAMES, ('∅','{}','{,}','⟨,⟩')): return
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
    defs = DefinitionService(session, authoring_via='seed')
    _register_empty_set(ss, fs, defs)
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
    proofs = _Proofs(session, 'zfc')
    proofs.seed()
    proofs.seed_empty_set()


class _Proofs(Builder):
    extra_logic = {'peirce': PEIRCE}

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

    def empty_membership_equivalence(self, a):
        x = self.atom('x')
        left, right = self.member(x, a), self.member(x, self.atom('∅'))
        no_left = self.assume(self.all('x', self.neg(left)))
        no_right = self.ui(self.cite('ZF:空集合は元を持たない'), x)
        forward = self.from_impossible_membership(left, self.ui(no_left, x), right)
        reverse = self.from_impossible_membership(right, no_right, left)
        return no_left, self.gen(self.iff_in(forward, reverse), 'x')

    def from_impossible_membership(self, membership, negation, target):
        assumption = self.assume(membership)
        contradiction = self.not_out(negation, assumption)
        result = self.mp(self.ax('false', {'φ': target}), contradiction)
        return self.close(assumption, result)

    def seed_empty_set(self):
        empty, a, x, u, v = (self.atom(n) for n in ('∅', 'a', 'x', 'u', 'v'))
        empty_set = 'ZF:空集合の集合性'
        no_elements = 'ZF:空集合は元を持たない'
        uniqueness = 'ZF:空集合の一意性'

        self.start()
        infinity = self.ax('ZF無限公理')
        witness = self.assume(self.opened(self.tokens(infinity), 'u'))
        membership = self.left(self.right(witness))
        purity = self.uis(self.ax('ZF純粋性公理'), empty, u)
        self.ee(infinity, 'u', witness, self.mp(purity, membership))
        self.finish(empty_set, self.parse('IsSet(∅)'), 'The empty set is a set.')

        self.start()
        definition = self.definition('∅')
        bottom = self.atom('⊥')
        comp_set = self.transport(definition, self.cite(empty_set), 'v', self.isset(v))
        schema = self.ax('ZF内包項所属公理図式', {'φ¹': (bottom, ('x',))})
        comp_membership = self.ui(self.mp(schema, comp_set), x)
        member = self.assume(self.member(x, empty))
        expanded = self.transport(definition, member, 'v', self.member(x, v))
        contradiction = self.right(self.iff_out(comp_membership, expanded))
        self.gen(self.not_in(self.close(member, contradiction)), 'x')
        self.finish(no_elements, self.parse('∀ x. ¬(x ∈ ∅)'),
                    'No object belongs to the empty set.')

        self.start()
        guard = self.assume(self.isset(a))
        no_left, pointwise = self.empty_membership_equivalence(a)
        extensionality = self.uis(self.ax('ZF外延性公理'), a, empty)
        equal = self.apply(extensionality, guard, self.cite(empty_set), pointwise)
        self.gen(self.close_many([guard, no_left], equal), 'a')
        self.finish(uniqueness, self.parse('∀ a. IsSet(a) → (∀ x. ¬(x ∈ a)) → a = ∅'),
                    'Every set with no elements equals the empty set.')

        self.start()
        guard = self.assume(self.isset(a))
        unequal = self.assume(self.neg(self.eq(a, empty)))
        membership = self.member(x, a)
        exists = self.some('x', membership)
        refute_existence = self.assume(self.imp(exists, bottom))
        member = self.assume(membership)
        contradiction = self.mp(refute_existence, self.ei(member, 'x', membership, x))
        no_members = self.gen(self.not_in(self.close(member, contradiction)), 'x')
        equal = self.apply(self.ui(self.cite(uniqueness), a), guard, no_members)
        contradiction = self.not_out(unequal, equal)
        result = self.mp(self.ax('false', {'φ': exists}), contradiction)
        classical = self.ax('peirce', {'φ': exists, 'ψ': bottom})
        exists_proof = self.mp(classical, self.close(refute_existence, result))
        self.gen(self.close_many([guard, unequal], exists_proof), 'a')
        self.finish('ZF:空でない集合は元を持つ',
                    self.parse('∀ a. IsSet(a) → ¬(a = ∅) → (∃ x. x ∈ a)'),
                    'A set distinct from the empty set has an element.')

        self.start()
        guard = self.assume(self.isset(a))
        equal = self.assume(self.eq(empty, self.single(a)))
        member = self.iff_out(self.smem(guard, a), self.refl(a), True)
        in_empty = self.transport(self.sym(equal), member, 'v', self.member(a, v))
        contradiction = self.not_out(self.ui(self.cite(no_elements), a), in_empty)
        self.gen(self.close(guard, self.not_in(self.close(equal, contradiction))), 'a')
        self.finish('ZF:空集合は単集合でない', self.parse('∀ a. IsSet(a) → ¬(∅ = {}(a))'),
                    'The singleton of a set is distinct from the empty set.')

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
