"""Proof construction for the public set packages, without a theorem corpus.

Every convenience below emits axiom instances, MP, Gen or ImpIntro. Logical
axioms are selected by their formulas, never by a name or a premise order.
"""
from sqlalchemy import select
from dem.db.models import Axiom, Proof, Symbol, Theorem
from dem.errors import ValidationError
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService, abstract_and_quantify_pure
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import (Token, PropSubst, TermSubst, Substitution, AxiomStepInput,
                       TheoremStepInput, AssumptionStepInput, MPStepInput,
                       GenStepInput, ImplicationIntroStepInput)


LOGIC = {
    'false': '⊥ → φ', 'not_in': '(φ → ⊥) → ¬(φ)',
    'not_out': '¬(φ) → φ → ⊥', 'and_in': 'φ → ψ → (φ ∧ ψ)',
    'and_left': '(φ ∧ ψ) → φ', 'and_right': '(φ ∧ ψ) → ψ',
    'or_left': 'φ → (φ ∨ ψ)', 'or_right': 'ψ → (φ ∨ ψ)',
    'or_out': '(φ → χ) → (ψ → χ) → (φ ∨ ψ) → χ',
    'exists_in': 'φ¹(t) → (∃ x. φ¹(x))',
    'exists_out': '(∀ x. (φ¹(x) → ψ)) → (∃ x. φ¹(x)) → ψ',
    'forall_out': '(∀ x. φ¹(x)) → φ¹(t)',
    'refl': 'x = x', 'subst': 'x = y → φ¹(x) → φ¹(y)',
    'iff_in': '(φ → ψ) → (ψ → φ) → (φ ↔ ψ)',
    'iff_left': '(φ ↔ ψ) → φ → ψ',
    'iff_right': '(φ ↔ ψ) → ψ → φ',
}


def completed(session, theorem_names, axiom_names, system_names, definition_names=()):
    ts = list(session.scalars(select(Theorem).where(Theorem.name.in_(theorem_names))))
    ps = list(session.scalars(select(Proof).where(Proof.theorem_id.in_([t.id for t in ts]))))
    axs = list(session.scalars(select(Axiom).where(Axiom.name.in_(axiom_names))))
    from dem.db.models import AxiomSystem
    systems = list(session.scalars(select(AxiomSystem).where(AxiomSystem.name.in_(system_names))))
    from dem.db.models import Definition
    definitions = list(session.scalars(select(Definition).where(Definition.name.in_(definition_names))))
    if not ts and not axs and not systems:
        return False
    if (len(ts) == len(theorem_names) and all(t.status == 'proven' for t in ts)
            and len(ps) == len(ts) and all(p.status == 'verified' for p in ps)
            and len({p.theorem_id for p in ps}) == len(ts)
            and len(axs) == len(axiom_names) and len(systems) == len(system_names)
            and len(definitions) == len(definition_names)):
        return True
    raise ValidationError('Incomplete public set package')


class Builder:
    def __init__(self, session, package):
        self.session, self.package = session, package
        self.ss, self.fs = SymbolService(session), FormulaService(session)
        self.axs, self.ps = AxiomService(session), ProofService(session, authoring_via='seed')
        self.ts = TheoremService(session)
        self.symbols = {s.name: s for s in session.scalars(select(Symbol))}
        self.meta = self.fs._load_symbol_meta([Token(s.id) for s in self.symbols.values()])
        self.logic = {}
        for key, text in LOGIC.items():
            tokens = self.parse(text)
            digest = self.fs.register(tokens).hash
            from dem.db.models import Formula
            matches = list(session.scalars(select(Axiom).join(Formula, Axiom.formula_id == Formula.id).where(Formula.hash == digest)))
            if len(matches) != 1:
                raise ValidationError(f'Expected exactly one logical axiom for {text}: {len(matches)}')
            self.logic[key] = matches[0]
        self.lines = []

    def parse(self, text): return self.fs.parse_text(text)[0]
    def atom(self, name): return [Token(self.symbols[name].id)]
    def op(self, name, *args): return [*self.atom(name), *(t for a in args for t in a)]
    def imp(self, a, b): return self.op('→', a, b)
    def eq(self, a, b): return self.op('=', a, b)
    def conj(self, a, b): return self.op('∧', a, b)
    def disj(self, a, b): return self.op('∨', a, b)
    def iff(self, a, b): return self.op('↔', a, b)
    def neg(self, a): return self.op('¬', a)
    def member(self, a, b): return self.op('∈', a, b)
    def isset(self, a): return self.op('IsSet', a)
    def quant(self, name, v, body):
        return abstract_and_quantify_pure(body, self.symbols[v].id, self.symbols[name].id, self.meta)
    def all(self, v, body): return self.quant('∀', v, body)
    def some(self, v, body): return self.quant('∃', v, body)
    def comp(self, v, body): return self.quant('{|}', v, body)
    def exists_member(self, a): return self.some('w', self.member(a, self.atom('w')))
    def fid(self, tokens): return self.fs.register(tokens).id

    def parts(self, tokens):
        def end(i):
            t = tokens[i]
            if t.symbol_id is None: return i + 1
            m = self.meta[t.symbol_id]
            j = i + 1
            for _ in range(1 if m.is_quantifier else m.arity): j = end(j)
            return j
        result, j = [], 1
        while j < len(tokens):
            k = end(j); result.append(tokens[j:k]); j = k
        return result

    def opened(self, quantified, variable):
        # Open the outer binder, preserving all nested de Bruijn indices.
        def visit(i, depth):
            t = quantified[i]
            if t.symbol_id is None:
                n = t.de_bruijn_index
                return (self.atom(variable) if n == depth else [Token(de_bruijn_index=n - (n > depth))]), i + 1
            m = self.meta[t.symbol_id]; out = [t]; j = i + 1
            for _ in range(1 if m.is_quantifier else m.arity):
                child, j = visit(j, depth + int(m.is_quantifier)); out.extend(child)
            return out, j
        return visit(1, 0)[0]

    def sigma(self, props=None, terms=None):
        props, terms = props or {}, terms or {}
        # The kernel applies proposition substitution before term substitution.
        # Protect external free variables in a lambda body from the latter;
        # lambda parameters continue to receive the intended term instances.
        from dem.services.proof import apply_substitution_pure
        protected, extra = {}, {}
        used = {t.symbol_id for body in props.values() for t in (body[0] if isinstance(body, tuple) else body)}
        used.update(t.symbol_id for body in terms.values() for t in body)
        fresh = [n for n in ('r','s','h','k') if self.symbols[n].id not in used and n not in terms]
        renames = {}
        for n in terms:
            if any(self.symbols[n].id in {t.symbol_id for t in (body[0] if isinstance(body,tuple) else body)}
                   and n not in (body[1] if isinstance(body,tuple) else ()) for body in props.values()):
                if not fresh: raise ValidationError('No capture-free substitution variable')
                temp = fresh.pop(0); renames[n] = temp; extra[temp] = self.atom(n)
        for n, body in props.items():
            tokens, params = body if isinstance(body,tuple) else (body, ())
            term_bindings = {self.symbols[src].id:self.atom(dst) for src,dst in renames.items() if src not in params}
            tokens = apply_substitution_pure(tokens, {}, term_bindings, self.meta)
            protected[n] = (tokens,params)
        props, terms = protected, {**terms, **extra}
        return Substitution(
            prop_substs=tuple(PropSubst(self.symbols[n].id, self.fid(b[0] if isinstance(b, tuple) else b),
                                      tuple(self.symbols[v].id for v in b[1]) if isinstance(b, tuple) else ()) for n, b in props.items()),
            term_substs=tuple(TermSubst(self.symbols[n].id, self.fid(b)) for n, b in terms.items()))
    def line(self, spec, tokens):
        i = len(self.lines); self.lines.append((spec, tokens)); return i
    def tokens(self, i): return self.lines[i][1]
    def ax(self, key, props=None, terms=None):
        row = self.logic[key] if key in self.logic else self.axs.get_by_name(key)
        sigma = self.sigma(props, terms)
        return self.line(AxiomStepInput(row.id, sigma), self.ps.compute_substituted_tokens(row.formula_id, sigma))
    def cite(self, name, props=None, terms=None):
        row = self.ts.get_by_name(name)
        proof = self.ps.list_for_theorem(row.id)
        if len(proof) != 1: raise ValidationError('Ambiguous public helper proof')
        sigma = self.sigma(props, terms)
        return self.line(TheoremStepInput(proof[0].id, sigma), self.ps.compute_substituted_tokens(row.conclusion_formula_id, sigma))
    def assume(self, tokens): return self.line(AssumptionStepInput(), tokens)
    def mp(self, implication, antecedent):
        p, q = self.parts(self.tokens(implication))
        if p != self.tokens(antecedent):
            raise ValidationError(f'Builder MP mismatch: {self.fs.print_text(p)} / {self.fs.print_text(self.tokens(antecedent))}')
        return self.line(MPStepInput(antecedent, implication), q)
    def apply(self, implication, *args):
        for a in args: implication = self.mp(implication, a)
        return implication
    def close(self, a, b): return self.line(ImplicationIntroStepInput(a, b), self.imp(self.tokens(a), self.tokens(b)))
    def gen(self, i, v): return self.line(GenStepInput(i, self.symbols[v].id), self.all(v, self.tokens(i)))
    def ui(self, i, term, v='v'):
        body = self.opened(self.tokens(i), v)
        return self.mp(self.ax('forall_out', {'φ¹': (body, (v,))}, {'t': term}), i)
    def uis(self, i, *terms):
        for t in terms: i = self.ui(i, t)
        return i
    def pair(self, i, j): return self.apply(self.ax('and_in', {'φ': self.tokens(i), 'ψ': self.tokens(j)}), i, j)
    def left(self, i):
        p, q = self.parts(self.tokens(i)); return self.mp(self.ax('and_left', {'φ': p, 'ψ': q}), i)
    def right(self, i):
        p, q = self.parts(self.tokens(i)); return self.mp(self.ax('and_right', {'φ': p, 'ψ': q}), i)
    def iff_out(self, i, j, reverse=False):
        p, q = self.parts(self.tokens(i))
        return self.apply(self.ax('iff_right' if reverse else 'iff_left', {'φ': p, 'ψ': q}), i, j)
    def iff_in(self, i, j):
        p, q = self.parts(self.tokens(i))
        return self.apply(self.ax('iff_in', {'φ': p, 'ψ': q}), i, j)
    def or_in(self, i, other, right=False):
        p, q = (other, self.tokens(i)) if right else (self.tokens(i), other)
        return self.mp(self.ax('or_right' if right else 'or_left', {'φ': p, 'ψ': q}), i)
    def cases(self, i, left, right):
        p, q = self.parts(self.tokens(i)); _, r = self.parts(self.tokens(left))
        return self.apply(self.ax('or_out', {'φ': p, 'ψ': q, 'χ': r}), left, right, i)
    def not_out(self, n, p): return self.apply(self.ax('not_out', {'φ': self.tokens(p)}), n, p)
    def not_in(self, implication):
        p, _ = self.parts(self.tokens(implication)); return self.mp(self.ax('not_in', {'φ': p}), implication)
    def refl(self, a): return self.ax('refl', terms={'x': a})
    def transport(self, equality, fact, v, predicate):
        a, b = self.parts(self.tokens(equality))
        return self.apply(self.ax('subst', {'φ¹': (predicate, (v,))}, {'x': a, 'y': b}), equality, fact)
    def sym(self, e):
        a, _ = self.parts(self.tokens(e)); return self.transport(e, self.refl(a), 'v', self.eq(self.atom('v'), a))
    def trans(self, e, f):
        a, _ = self.parts(self.tokens(e)); return self.transport(f, e, 'v', self.eq(a, self.atom('v')))
    def ei(self, fact, v, body, witness):
        return self.mp(self.ax('exists_in', {'φ¹': (body, (v,))}, {'t': witness}), fact)
    def ee(self, existential, v, assumption, conclusion):
        body = self.opened(self.tokens(existential), v)
        if self.tokens(assumption) != body: raise ValidationError('Existential witness mismatch')
        closed = self.gen(self.close(assumption, conclusion), v)
        return self.apply(self.ax('exists_out', {'φ¹': (body, (v,)), 'ψ': self.tokens(conclusion)}), closed, existential)
    def start(self): self.lines = []
    def finish(self, name, expected=None, description=''):
        if not self.lines or len(self.lines) > 200:
            raise ValidationError(f'Public proof step limit: {name}: {len(self.lines)}')
        target = self.tokens(len(self.lines)-1)
        if expected is not None and target != expected: raise ValidationError(f'Wrong public statement: {name}')
        theorem = self.ts.register(name, self.fid(target), [], description=description,
                                   public_id_key=f'dem.public.{self.package}::{name}')
        proof = self.ps.create_proof(theorem.id, name=name+'の証明')
        for spec, tokens in self.lines: self.ps.add_step(proof.id, spec, self.fid(tokens))
        self.ps.validate(proof.id)
        return proof
