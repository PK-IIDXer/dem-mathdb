"""Public definitions shared by the three relations and maps packages."""

from sqlalchemy import select

from dem.db.models import Symbol
from dem.services.definition import DefinitionPublicIdKeys, DefinitionService
from dem.services.formula import FormulaService
from dem.services.symbol import SymbolService
from dem.types import FunctionDefinitionInput, PredicateDefinitionInput
from dem.types import QuantPropDefinitionInput, SymbolTypeName


DEFINITIONS = {
    "unique-existence": (
        ("∃!", QuantPropDefinitionInput, ("φ¹",),
         "∃ x. (φ¹(x) ∧ (∀ y. (φ¹(y) → y = x)))", r"\exists!", None),
    ),
    "relations": (
        ("⊂", PredicateDefinitionInput, ("a", "b"),
         "∀ x. (x ∈ a → x ∈ b)", r"#1 \subset #2", 50),
        ("×", FunctionDefinitionInput, ("a", "b"),
         "{|} q. (∃ x. ∃ y. (x ∈ a ∧ (y ∈ b ∧ q = ⟨,⟩(x, y))))", r"#1 \times #2", 70),
        ("IsRelation", PredicateDefinitionInput, ("R", "X", "Y"),
         "IsSet(R) ∧ R ⊂ X × Y", r"#1 \mathrel{\mathsf{IsRelationFrom}} #2 \mathrel{\mathsf{To}} #3", None),
        ("IsMap", PredicateDefinitionInput, ("f", "X", "Y"),
         "IsRelation(f, X, Y) ∧ (∀ x. (x ∈ X → (∃! y. (y ∈ Y ∧ ⟨,⟩(x, y) ∈ f))))",
         r"#1 \mathrel{\mathsf{IsMapFrom}} #2 \mathrel{\mathsf{To}} #3", None),
        ("ev", FunctionDefinitionInput, ("f", "x"),
         "{|} z. (IsSet(x) ∧ (∃ y. (IsSet(y) ∧ (⟨,⟩(x, y) ∈ f"
         " ∧ ((∀ w. ((IsSet(w) ∧ ⟨,⟩(x, w) ∈ f) → w = y)) ∧ z ∈ y)))))",
         r"#1\left(#2\right)", None),
        ("Preimage", FunctionDefinitionInput, ("f", "a"),
         "{|} x. (IsSet(x) ∧ (∃ y. (y ∈ a ∧ ⟨,⟩(x, y) ∈ f)))",
         r"\operatorname{Preimage}\left(#1, #2\right)", None),
        ("∘", FunctionDefinitionInput, ("g", "f"),
         "{|} q. (∃ x. ∃ y. ∃ z. (IsSet(x) ∧ (IsSet(y) ∧ (IsSet(z) ∧ (q = ⟨,⟩(x, z)"
         " ∧ (⟨,⟩(x, y) ∈ f ∧ ⟨,⟩(y, z) ∈ g))))))",
         r"#1 \circ #2", 70),
        ("id", FunctionDefinitionInput, ("X",),
         "{|} q. (∃ x. (x ∈ X ∧ q = ⟨,⟩(x, x)))",
         r"\operatorname{id}_{#1}", None),
    ),
    "class-relations": (
        ("IsClassRelation", PredicateDefinitionInput, ("R", "X", "Y"),
         "R ⊂ X × Y", r"#1 \mathrel{\mathsf{IsClassRelationFrom}} #2 \mathrel{\mathsf{To}} #3", None),
        ("IsClassMap", PredicateDefinitionInput, ("f", "X", "Y"),
         "IsClassRelation(f, X, Y) ∧ (∀ x. (x ∈ X → (∃! y. (y ∈ Y ∧ ⟨,⟩(x, y) ∈ f))))",
         r"#1 \mathrel{\mathsf{IsClassMapFrom}} #2 \mathrel{\mathsf{To}} #3", None),
    ),
}
VARIABLES = {"unique-existence": ("i", "j", "l"), "relations": ("f", "R", "S", "X", "Y", "W"), "class-relations": ()}


def register_definitions(session, package):
    symbols = SymbolService(session)
    formulas = FormulaService(session)
    definitions = DefinitionService(session, authoring_via="seed")
    variable_type = symbols.get_symbol_type_by_name(SymbolTypeName.FREE_TERM_VAR.value)
    for name in VARIABLES[package]:
        if session.scalar(select(Symbol.id).where(Symbol.name == name)) is None:
            symbols.register(name, variable_type.id, 0, public_id_key=f"dem.foundation.logic::{name}")
    for name, kind, params, body, latex, precedence in DEFINITIONS[package]:
        ids = tuple(symbols.get_by_name(param).id for param in params)
        formula_id = formulas.register(formulas.parse_text(body)[0]).id
        key = f"dem.public.{package}::{name}"
        definition = definitions.register(
            kind(name, ids[0] if kind is QuantPropDefinitionInput else ids, formula_id, latex_template=latex),
            public_id_keys=DefinitionPublicIdKeys(key, key, key),
        )
        if precedence is not None:
            symbols.set_notation(definition.new_symbol_id, "infix", precedence)
