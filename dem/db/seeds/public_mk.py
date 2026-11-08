"""Class existence from the requested MK schemas, with checked finite proofs."""
from sqlalchemy import select
from dem.db.models import AxiomSystemMember, Symbol
from dem.errors import ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.types import SymbolTypeName
from dem.db.seeds.public_mk_data import AXIOMS
from dem.db.seeds.public_set_tools import completed
from dem.db.seeds.public_zfc import _Proofs, THEOREM_NAMES as ZF_NAMES

HELPERS = ('MK:集合における類内包', 'MK:順序対内包の導入', 'MK:順序対内包の除去',
           'MK:三つ組内包の導入', 'MK:三つ組内包の除去')
STATEMENTS = (
    ('MK:B1 所属関係の類', '∃ Z. (∀ x. IsSet(x) → (∀ y. IsSet(y) → (⟨,⟩(x, y) ∈ Z ↔ (x ∈ y))))'),
    ('MK:B2 共通部分の類', '∀ a. (∀ b. (∃ Z. (∀ x. IsSet(x) → (x ∈ Z ↔ (x ∈ a ∧ x ∈ b)))))'),
    ('MK:B3 補類', '∀ a. (∃ Z. (∀ x. IsSet(x) → (x ∈ Z ↔ (¬(x ∈ a)))))'),
    ('MK:B4 定義域の類', '∀ a. (∃ Z. (∀ x. IsSet(x) → (x ∈ Z ↔ (∃ y. (IsSet(y) ∧ ⟨,⟩(x, y) ∈ a)))))'),
    ('MK:B5 全体類との直積', '∀ g. (∃ Z. (∀ x. IsSet(x) → (∀ y. IsSet(y) → (⟨,⟩(x, y) ∈ Z ↔ (x ∈ g)))))'),
    ('MK:B6 三つ組の巡回置換の類', '∀ g. (∃ Z. (∀ a. IsSet(a) → (∀ b. IsSet(b) → (∀ c. IsSet(c) → (⟨,⟩(⟨,⟩(a, b), c) ∈ Z ↔ ⟨,⟩(⟨,⟩(b, c), a) ∈ g)))))'),
    ('MK:B7 三つ組の後ろ二成分の転置の類', '∀ g. (∃ Z. (∀ a. IsSet(a) → (∀ b. IsSet(b) → (∀ c. IsSet(c) → (⟨,⟩(⟨,⟩(a, b), c) ∈ Z ↔ ⟨,⟩(⟨,⟩(a, c), b) ∈ g)))))'),
    ('MK:逆関係の類', '∀ g. (∃ Z. (∀ x. IsSet(x) → (∀ y. IsSet(y) → (⟨,⟩(x, y) ∈ Z ↔ (⟨,⟩(y, x) ∈ g)))))'),
)
THEOREM_NAMES = (*HELPERS, *(name for name, _ in STATEMENTS))


def seed_public_mk(session):
    if completed(session, THEOREM_NAMES, [a[0] for a in AXIOMS], ('MK',)): return
    ss, fs, axs = SymbolService(session), FormulaService(session), AxiomService(session)
    ss.register('φ³',ss.get_symbol_type_by_name(SymbolTypeName.FREE_PROP_VAR.value).id,3,
                public_id_key='dem.foundation.logic::φ³',latex_template=None)
    for name,text,pid,digest in AXIOMS:
        formula=fs.register(fs.parse_text(text)[0])
        axiom=axs.register(name,formula.id,public_id_key='dem.lean.mk::'+name,
                           description='Class-theory axiom schema supplied for the public foundation.')
        if axiom.public_id!=pid or formula.hash!=digest: raise ValidationError(f'Shared axiom identity mismatch: {name}')
    system=axs.register_system('MK',public_id_key='dem.public.mk::MK',remarks='ZFC with class comprehension and class extensionality.')
    zfc=axs.get_system_by_name('ZFC')
    ids=list(session.scalars(select(AxiomSystemMember.axiom_id).where(AxiomSystemMember.axiom_system_id==zfc.id)))
    for ax in [*ids,*(axs.get_by_name(a[0]).id for a in AXIOMS)]: axs.add_to_system(system.id,ax)
    _Classes(session,'mk').seed_classes()


class _Classes(_Proofs):
    def replaced(self,body,bindings):
        from dem.services.proof import apply_substitution_pure
        return apply_substitution_pure(body,{}, {self.symbols[n].id:t for n,t in bindings.items()},self.meta)
    def tuple_term(self,values):
        if len(values)==2: return self.ordered(*values)
        return self.ordered(self.ordered(*values[:2]),values[2])
    def tuple_set(self,values):
        return self.set_ordered(*values) if len(values)==2 else self.set_ordered(self.ordered(*values[:2]),values[2])
    def tuple_body(self,n,predicate):
        names=('x','y','z')[:n]; values=[self.atom(v) for v in names]
        body=self.conj(self.eq(self.atom('q'),self.tuple_term(values)),predicate)
        for value in reversed(values): body=self.conj(self.isset(value),body)
        for v in reversed(names): body=self.some(v,body)
        return body
    def tuple_injection(self,targets,witnesses,target_sets,witness_sets,equality):
        if len(targets)==2:
            result=self.apply(self.cite(ZF_NAMES[10],terms=dict(zip(('a','b','c','d'),[*targets,*witnesses]))),
                              *target_sets,*witness_sets,equality)
            return [self.left(result),self.right(result)]
        result=self.apply(self.cite(ZF_NAMES[10],terms=dict(zip(('a','b','c','d'),
                              [self.ordered(*targets[:2]),targets[2],self.ordered(*witnesses[:2]),witnesses[2]]))),
                          self.set_ordered(*targets[:2]),target_sets[2],self.set_ordered(*witnesses[:2]),witness_sets[2],equality)
        inner=self.left(result); last=self.right(result)
        return [*self.tuple_injection(targets[:2],witnesses[:2],target_sets[:2],witness_sets[:2],inner),last]

    def tuple_helper(self,n,introduction):
        self.start(); names=('a','b','c')[:n]; ws=('x','y','z')[:n]
        targets=[self.atom(v) for v in names]; witnesses=[self.atom(v) for v in ws]
        prop='φ²' if n==2 else 'φ³'
        pred=self.op(prop,*witnesses); value=self.op(prop,*targets)
        body=self.tuple_body(n,pred); z=self.comp('q',body); term=self.tuple_term(targets)
        guards=[self.assume(self.isset(t)) for t in targets]
        raw=self.ui(self.ax('MK類内包公理図式',{'φ¹':(body,('q',))}),term)
        if introduction:
            p=self.assume(value)
            core=self.pair(self.refl(term),p)
            for s in reversed(guards): core=self.pair(s,core)
            # Introduce existential witnesses from the innermost binder out.
            for i in reversed(range(n)):
                tail=self.conj(self.eq(self.atom('q'),self.tuple_term(witnesses)),pred)
                for t in reversed(witnesses): tail=self.conj(self.isset(t),tail)
                for v in reversed(ws[i+1:]): tail=self.some(v,tail)
                tail=self.replaced(tail,{'q':term,**dict(zip(ws[:i],targets[:i]))})
                core=self.ei(core,ws[i],tail,targets[i])
            result=self.iff_out(raw,self.pair(self.element(self.tuple_set(targets)),core),True)
        else:
            p=self.assume(self.member(term,z)); ex=self.right(self.iff_out(raw,p))
            def unpack(existential,i):
                witness=self.assume(self.opened(self.tokens(existential),ws[i]))
                if i+1<n: result=unpack(witness,i+1)
                else:
                    core=witness; sets=[]
                    for _ in range(n): sets.append(self.left(core)); core=self.right(core)
                    equality=self.left(core); result=self.right(core)
                    equations=self.tuple_injection(targets,witnesses,guards,sets,equality)
                    current=list(witnesses)
                    for j,equation in enumerate(equations):
                        predicate_args=list(current); predicate_args[j]=self.atom('v')
                        result=self.transport(self.sym(equation),result,'v',self.op(prop,*predicate_args))
                        current[j]=targets[j]
                return self.ee(existential,ws[i],witness,result)
            result=unpack(ex,0)
        self.close_many([*guards,p],result)
        self.finish(HELPERS[(1 if n==2 else 3)+(not introduction)])

    def seed_classes(self):
        a,x=self.atom('a'),self.atom('x'); predicate=self.op('φ¹',x)
        self.start(); sa=self.assume(self.isset(a)); term=self.comp('x',predicate)
        raw=self.ui(self.ax('MK類内包公理図式'),a)
        member=self.assume(self.member(a,term)); fwd=self.close(member,self.right(self.iff_out(raw,member)))
        value=self.op('φ¹',a); p=self.assume(value)
        rev=self.close(p,self.iff_out(raw,self.pair(self.element(sa),p),True))
        self.close(sa,self.iff_in(fwd,rev)); self.finish(HELPERS[0])
        for n in (2,3):
            self.tuple_helper(n,True); self.tuple_helper(n,False)
        self.existence_theorems()

    def existence_theorems(self):
        a,b,c,x,y,g,Z=[self.atom(v) for v in ('a','b','c','x','y','g','Z')]
        for index,(name,text) in enumerate(STATEMENTS):
            self.start()
            if index in (1,2,3):
                predicate=(self.conj(self.member(x,a),self.member(x,b)) if index==1 else
                           self.neg(self.member(x,a)) if index==2 else
                           self.some('y',self.conj(self.isset(y),self.member(self.ordered(x,y),a))))
                z=self.comp('x',predicate); sx=self.assume(self.isset(x))
                fact=self.mp(self.cite(HELPERS[0],{'φ¹':(predicate,('x',))},{'a':x}),sx)
                result=self.gen(self.close(sx,fact),'x')
                body=self.all('x',self.imp(self.isset(x),self.iff(self.member(x,Z),predicate)))
                result=self.ei(result,'Z',body,z)
                for v in reversed(('a','b') if index==1 else ('a',)): result=self.gen(result,v)
            else:
                n=3 if index in (5,6) else 2
                names=('a','b','c') if n==3 else ('x','y')
                values=[self.atom(v) for v in names]
                predicate=(self.member(x,y) if index==0 else self.member(x,g) if index==4 else
                           self.member(self.ordered(self.ordered(b,c),a),g) if index==5 else
                           self.member(self.ordered(self.ordered(a,c),b),g) if index==6 else
                           self.member(self.ordered(y,x),g))
                ws=('x','y','z')[:n]
                renamed=self.replaced(predicate,dict(zip(names,[self.atom(v) for v in ws])))
                z=self.comp('q',self.tuple_body(n,renamed)); guards=[self.assume(self.isset(t)) for t in values]
                prop='φ²' if n==2 else 'φ³'; first=1 if n==2 else 3
                bindings=dict(zip(('a','b','c')[:n],values))
                fwd=self.apply(self.cite(HELPERS[first+1],{prop:(predicate,names)},bindings),*guards)
                rev=self.apply(self.cite(HELPERS[first],{prop:(predicate,names)},bindings),*guards)
                result=self.iff_in(fwd,rev)
                for v,guard in reversed(list(zip(names,guards))): result=self.gen(self.close(guard,result),v)
                body=self.iff(self.member(self.tuple_term(values),Z),predicate)
                for v,t in reversed(list(zip(names,values))): body=self.all(v,self.imp(self.isset(t),body))
                result=self.ei(result,'Z',body,z)
                if index: result=self.gen(result,'g')
            self.finish(name,self.parse(text),'Class existence from comprehension; B1–B7 numbering follows Mendelson, 4th ed., p.230.')
