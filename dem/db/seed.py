from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dem.db.models.inference import InferenceRule
from dem.db.models.language import FormulaType, Symbol, SymbolRole, SymbolType
from dem.errors import ValidationError
from dem.services.symbol import SymbolService
from dem.types import FormulaTypeName, SymbolTypeName


FORMULA_TYPE_SEEDS = [
    (FormulaTypeName.TERM.value, "term", "term. 数学的な実体を表す論理式。"),
    (
        FormulaTypeName.PROPOSITION.value,
        "proposition",
        "proposition. 真偽を問える論理式。",
    ),
]

SYMBOL_TYPE_SEEDS = [
    (SymbolTypeName.FUNCTION.value, FormulaTypeName.TERM, FormulaTypeName.TERM, None, False, "項から項を作る記号"),
    (SymbolTypeName.PREDICATE.value, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, None, False, "項から命題を作る記号"),
    (SymbolTypeName.LOGICAL.value, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, None, False, "¬, ∨, ∧, →, ↔ など。"),
    (SymbolTypeName.QUANT_PROP.value, FormulaTypeName.PROPOSITION, FormulaTypeName.PROPOSITION, 1, True, "命題を束縛して命題を作る記号"),
    (SymbolTypeName.QUANT_TERM.value, FormulaTypeName.TERM, FormulaTypeName.PROPOSITION, 1, True, "項を作る束縛記法。現在インスタンスは無い。"),
    (SymbolTypeName.FREE_TERM_VAR.value, FormulaTypeName.TERM, None, 0, False, "自由な項変数"),
    (SymbolTypeName.FREE_PROP_VAR.value, FormulaTypeName.PROPOSITION, FormulaTypeName.TERM, None, False, "自由な命題変数"),
]

PRIMITIVE_SYMBOL_SEEDS = [
    # name, symbol_type, arity, notation_kind, precedence, latex_template, remarks
    # precedence order (higher binds tighter): ∧(40) > ∨(30) > →(20) > ↔(10)
    #
    # The public language keeps these connectives primitive. Their semantics
    # are supplied only by axioms explicitly selected for an axiom system.
    ("⊥", SymbolTypeName.LOGICAL, 0, "prefix", None, r"\bot", "矛盾"),
    ("¬", SymbolTypeName.LOGICAL, 1, "prefix", None, r"\neg", "否定"),
    ("∨", SymbolTypeName.LOGICAL, 2, "infix", 30, r"\vee", "選言"),
    ("∧", SymbolTypeName.LOGICAL, 2, "infix", 40, r"\wedge", "連言"),
    # `\implies` / `\iff`, not `\to` / `\leftrightarrow`. These are the object
    # language's connectives, and this project's own prose calls them that
    # ("⇒導入", architecture.md §2.1); the metalanguage side is `⊢`, so the
    # heavier arrows do not collide with anything. See conventions.md §4.
    ("→", SymbolTypeName.LOGICAL, 2, "infix", 20, r"\implies", "含意"),
    # ↔ is kept primitive because DefinitionService itself uses it to build
    # definition-derived axioms. Defining ↔ with that same mechanism would be
    # self-referential.
    ("↔", SymbolTypeName.LOGICAL, 2, "infix", 10, r"\iff", "同値"),
    # Quantifiers range over every well-formed term in the generic kernel.
    (
        "∀",
        SymbolTypeName.QUANT_PROP,
        1,
        "prefix",
        None,
        r"\forall",
        "整形式な項すべてを走る全称量化",
    ),
    ("∃", SymbolTypeName.QUANT_PROP, 1, "prefix", None, r"\exists", "整形式な項すべてを走る存在量化"),
    ("=", SymbolTypeName.PREDICATE, 2, "infix", 100, "=", "等号"),
]

ROLE_SEEDS = {
    "implication": "→",
    "universal_quantifier": "∀",
    "biconditional": "↔",
    "equality": "=",
}

# (name, kind, tier, elimination_procedure, premise_count,
#  requires_variable_param, remarks). See design doc §9.5 for the tiers: a rule
# may be added freely at `derived`, only with an elimination procedure and an
# invariant-(E)-shaped test at `admissible`, and not at all at `recognizer`.
INFERENCE_RULE_SEEDS = [
    ("MP", "modus_ponens", "primitive", None, 2, False, "φ と φ→ψ から ψ を導く"),
    ("Gen", "generalization", "primitive", None, 1, True, "φ から ∀°x.φ を導く"),
    (
        "ImpIntro",
        "implication_intro",
        "admissible",
        "expand_implication_intro",
        1,
        False,
        "仮定 φ の下での ψ から φ→ψ を導き、その仮定を落とす (Tier 2 許容規則。"
        "除去手続きは expand_implication_intro、設計書 §9.3)",
    ),
]


def seed_language(session: Session) -> None:
    """Insert Phase 1 enum rows, primitive symbols, and roles."""

    for name, code, remarks in FORMULA_TYPE_SEEDS:
        existing = session.scalar(select(FormulaType).where(FormulaType.name == name))
        if existing is None:
            session.add(FormulaType(name=name, code=code, remarks=remarks))
        elif existing.code != code:
            raise ValidationError(
                f"existing formula type {name!r} does not match seed code"
            )
    session.flush()

    formula_types = {
        FormulaTypeName(row.name): row
        for row in session.scalars(select(FormulaType)).all()
        if row.name in {item[0] for item in FORMULA_TYPE_SEEDS}
    }

    for name, output_name, input_name, fixed_arity, is_quantifier, remarks in SYMBOL_TYPE_SEEDS:
        existing = session.scalar(select(SymbolType).where(SymbolType.name == name))
        if existing is not None:
            continue
        session.add(
            SymbolType(
                name=name,
                output_formula_type_id=formula_types[output_name].id,
                input_formula_type_id=(
                    formula_types[input_name].id if input_name is not None else None
                ),
                fixed_arity=fixed_arity,
                is_quantifier=is_quantifier,
                remarks=remarks,
            )
        )
    session.flush()

    symbol_types = {
        SymbolTypeName(row.name): row
        for row in session.scalars(select(SymbolType)).all()
        if row.name in {item[0] for item in SYMBOL_TYPE_SEEDS}
    }

    from dem.db.seeds._notation import symbol_latex

    symbols = SymbolService(session)
    for (
        name,
        symbol_type_name,
        arity,
        notation_kind,
        precedence,
        latex_template,
        remarks,
    ) in PRIMITIVE_SYMBOL_SEEDS:
        latex_template = symbol_latex(name, latex_template)
        existing = session.scalar(select(Symbol).where(Symbol.name == name))
        if existing is None:
            symbol = symbols.register(
                name=name,
                symbol_type_id=symbol_types[symbol_type_name].id,
                arity=arity,
                is_primitive=True,
                notation_kind=notation_kind,
                precedence=precedence,
                latex_template=latex_template,
                remarks=remarks,
            )
            session.add(symbol)
            session.flush()
        else:
            if existing.symbol_type.name != symbol_type_name.value or existing.arity != arity:
                raise ValidationError(f"existing symbol {name!r} does not match seed shape")
            symbol = existing

        symbol.is_primitive = True
        symbol.remarks = remarks
        symbols.set_latex_template(symbol.id, latex_template)
        symbols.set_notation(symbol.id, notation_kind, precedence)
    session.flush()

    _seed_symbol_roles(session, ROLE_SEEDS)
    from dem.db.seeds._aliases import apply_builtin_aliases
    apply_builtin_aliases(session)


def _seed_symbol_roles(session: Session, role_seeds: dict[str, str]) -> None:
    symbols = {
        row.name: row
        for row in session.scalars(select(Symbol).where(Symbol.name.in_(role_seeds.values()))).all()
    }
    for role, symbol_name in role_seeds.items():
        existing = session.scalar(select(SymbolRole).where(SymbolRole.role == role))
        if existing is None:
            session.add(SymbolRole(role=role, symbol_id=symbols[symbol_name].id))
    session.flush()


def seed_inference_rules(session: Session) -> None:
    """Insert Phase 3 inference-rule seed rows."""

    for (
        name,
        kind,
        tier,
        elimination_procedure,
        premise_count,
        requires_variable_param,
        remarks,
    ) in INFERENCE_RULE_SEEDS:
        existing = session.scalar(select(InferenceRule).where(InferenceRule.name == name))
        if existing is not None:
            if (
                existing.kind != kind
                or existing.tier != tier
                or existing.elimination_procedure != elimination_procedure
                or existing.premise_count != premise_count
                or existing.requires_variable_param != requires_variable_param
            ):
                raise ValidationError(f"existing inference rule {name!r} does not match seed shape")
            existing.remarks = remarks
            continue
        session.add(
            InferenceRule(
                name=name,
                kind=kind,
                tier=tier,
                elimination_procedure=elimination_procedure,
                premise_count=premise_count,
                requires_variable_param=requires_variable_param,
                remarks=remarks,
            )
        )
    session.flush()
