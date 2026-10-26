"""Recover definition inputs from their checked defining axioms for transport."""
from sqlalchemy import select


def open_bound_body(tokens, params, symbol_record, symbol_types, require):
    """Undo outer parameter binders while preserving inner de Bruijn scopes."""
    def walk(pos, depth):
        require(pos < len(tokens), "truncated definition body")
        tok = tokens[pos]
        sid, index = tok["symbol_public_id"], tok["de_bruijn_index"]
        if sid is None:
            if index >= depth:
                outer = index - depth
                require(outer < len(params), "definition has an unbound variable")
                return [dict(symbol_public_id=params[-1-outer], de_bruijn_index=None)], pos + 1
            return [tok], pos + 1
        symbol = symbol_record(sid)
        st = next(r for r in symbol_types if r["name"] == symbol["symbol_type"])
        out, pos = [tok], pos + 1
        for _ in range(symbol["arity"]):
            part, pos = walk(pos, depth + int(st["is_quantifier"]))
            out.extend(part)
        return out, pos
    result, end = walk(0, 0)
    require(end == len(tokens), "trailing definition body tokens")
    return result


def definition_body_formula_ids(session, release_id):
    """Include existing body values needed by the ordinary DefinitionService.

    Bodies are not stored as a definition FK. Recover only formulas already in
    the source DB, never create formulas or bypass definition validation.
    """
    from dem.db.models import Axiom, Definition, DefinitionFormalParam, Formula, Symbol, SymbolType
    from dem.services.formula import FormulaService, compute_hash
    from dem.services.package import dependency_closure
    from dem.types import Token, SymbolTypeName
    definitions = list(session.scalars(select(Definition).where(Definition.release_id == release_id)))
    if not definitions:
        return set()
    symbols = {s.public_id: s for s in session.scalars(select(Symbol))}
    by_id = {s.id: s.public_id for s in symbols.values()}
    types = [dict(name=s.name, is_quantifier=s.is_quantifier) for s in session.scalars(select(SymbolType))]
    def record(pid):
        s = symbols[pid]
        return dict(symbol_type=s.symbol_type.name, arity=s.arity)
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    service = FormulaService(session)
    allowed = dependency_closure(session, release_id)
    found = set()
    for definition in definitions:
        params = [by_id[p] for p in session.scalars(select(DefinitionFormalParam.param_symbol_id).where(
            DefinitionFormalParam.definition_id == definition.id).order_by(DefinitionFormalParam.ord))]
        axiom = session.scalar(select(Axiom).where(Axiom.definition_id == definition.id))
        require(axiom is not None, "definition has no defining axiom")
        tokens = [dict(symbol_public_id=by_id[t.symbol_id] if t.symbol_id is not None else None,
                       de_bruijn_index=t.de_bruijn_index) for t in service.get_tokens(axiom.formula_id)]
        kind = definition.kind
        if kind in ("predicate", "function"):
            bodies = [open_bound_body(tokens[2*len(params)+2:], params, record, types, require)]
        elif kind == "logical":
            bodies = [tokens[2+len(params):]]
        elif kind in ("quant_prop", "quant_term"):
            bodies = [tokens[4:]]
        elif kind == "function_desc":
            free = {t["symbol_public_id"] for t in tokens[2*len(params)+5:]}
            bodies = [open_bound_body(tokens[2*len(params)+5:], params+[pid], record, types, require)
                      for pid, s in sorted(symbols.items()) if s.release_id in allowed
                      and s.symbol_type.name == SymbolTypeName.FREE_TERM_VAR.value
                      and pid not in params and pid not in free]
        else:
            raise ValueError("unknown definition kind: " + kind)
        matches = set()
        for body in bodies:
            converted = [Token(symbol_id=symbols[t["symbol_public_id"]].id if t["symbol_public_id"] else None,
                               de_bruijn_index=t["de_bruijn_index"]) for t in body]
            formula_id = session.scalar(select(Formula.id).where(Formula.hash == compute_hash(converted, by_id)))
            if formula_id is not None:
                matches.add(formula_id)
        require(bool(matches), "definition body missing from source DB")
        found.update(matches)
    return found
