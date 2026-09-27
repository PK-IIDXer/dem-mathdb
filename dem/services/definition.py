from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from dem.db.models.definition import Definition, DefinitionFormalParam
from dem.db.models.inference import Axiom
from dem.db.models.language import Formula, FormulaToken, Symbol
from dem.db.models.theorem import Proof, Theorem, TheoremPremise
from dem.db.seed_labels import (
    axiom_lookup_names,
    definition_axiom_formula_remark,
    definition_axiom_name,
)
from dem.db.models.tag import DefinitionTag
from dem.errors import ConflictError, NotFoundError, ValidationError
from dem.services.authoring_provenance import AuthoringVia, record_authoring_provenance
from dem.identity import DEFAULT_NAMESPACE_NAME, new_entity_public_id
from dem.services.axiom import AxiomService
from dem.services.formula import FormulaService
from dem.services.proof import ProofService, abstract_and_quantify_pure, apply_substitution_pure
from dem.services.symbol import SymbolService
from dem.services.theorem import TheoremService
from dem.types import (
    DefinitionInput,
    DescriptiveFunctionDefinitionInput,
    FormulaTypeName,
    FunctionDefinitionInput,
    LogicalDefinitionInput,
    PredicateDefinitionInput,
    QuantPropDefinitionInput,
    QuantTermDefinitionInput,
    SymbolTypeName,
    Token,
)


@dataclass(frozen=True)
class _DefinitionSpec:
    name: str
    kind: str
    symbol_type_name: SymbolTypeName
    arity: int
    param_symbol_ids: tuple[int, ...]
    body_formula_id: int
    body_formula_type: FormulaTypeName
    connective_role: str
    quantifies_params: bool
    requires_existence_proof: bool
    requires_uniqueness_proof: bool
    remarks: str | None
    latex_template: str | None
    value_symbol_id: int | None = None
    uniqueness_witness_symbol_id: int | None = None
    existence_uniqueness_proof_id: int | None = None


@dataclass(frozen=True)
class DefinitionPublicIdKeys:
    """Birth keys (``<namespace>::<name>``) of the three rows a definition
    creates: its symbol, the definition and the defining axiom.

    Seed data and package import pass them to keep public IDs when a
    definition lives in a namespace other than the one it was born in; the
    REST API never does (``dem.identity.public_id_from_key``)."""

    symbol: str
    definition: str
    axiom: str


class DefinitionService:
    def __init__(
        self,
        session: Session,
        *,
        authoring_via: AuthoringVia | None = None,
    ) -> None:
        self._session = session
        self._symbol_svc = SymbolService(session)
        self._formula_svc = FormulaService(session, authoring_via=authoring_via)
        self._axiom_svc = AxiomService(session)
        self._proof_svc = ProofService(session, authoring_via=authoring_via)
        self._theorem_svc = TheoremService(session, authoring_via=authoring_via)
        self._authoring_via = authoring_via

    def register(
        self,
        definition_input: DefinitionInput,
        *,
        namespace: str = DEFAULT_NAMESPACE_NAME,
        public_id_keys: DefinitionPublicIdKeys | None = None,
    ) -> Definition:
        spec = self._spec_for(definition_input)
        self._ensure_name_available(spec.name)
        self._validate_body_and_params(spec)

        symbol_type = self._symbol_svc.get_symbol_type_by_name(spec.symbol_type_name.value)
        new_symbol = self._symbol_svc.register(
            name=spec.name,
            symbol_type_id=symbol_type.id,
            arity=spec.arity,
            is_primitive=False,
            latex_template=spec.latex_template,
            remarks=spec.remarks,
            namespace=namespace,
            public_id_key=public_id_keys.symbol if public_id_keys else None,
        )
        public_id = new_entity_public_id(
            "definition",
            new_symbol.namespace.name,
            spec.name,
            public_id_keys.definition if public_id_keys else None,
        )
        if public_id_keys is not None and self._session.scalar(
            select(Definition.id).where(Definition.public_id == public_id)
        ) is not None:
            raise ConflictError("Definition", "public_id", public_id)

        defining_tokens = self.compute_defining_formula_tokens(definition_input, new_symbol.id)
        defining_formula = self._formula_svc.register(
            defining_tokens,
            remarks=definition_axiom_formula_remark(spec.name),
        )

        definition = Definition(
            public_id=public_id,
            name=spec.name,
            kind=spec.kind,
            new_symbol_id=new_symbol.id,
            requires_existence_proof=spec.requires_existence_proof,
            requires_uniqueness_proof=spec.requires_uniqueness_proof,
            existence_uniqueness_proof_id=spec.existence_uniqueness_proof_id,
            display_formula_id=defining_formula.id if spec.kind == "function" else None,
            remarks=spec.remarks,
        )
        self._session.add(definition)
        self._session.flush()
        record_authoring_provenance(
            self._session,
            entity_kind="definition",
            entity_id=definition.id,
            via=self._authoring_via,
        )

        self._axiom_svc._register_definition_derived(
            name=definition_axiom_name(spec.name),
            formula_id=defining_formula.id,
            definition_id=definition.id,
            remarks=spec.remarks,
            namespace=new_symbol.namespace.name,
            public_id_key=public_id_keys.axiom if public_id_keys else None,
        )

        self._session.add_all(
            DefinitionFormalParam(
                definition_id=definition.id,
                ord=ord_,
                param_symbol_id=param_symbol_id,
            )
            for ord_, param_symbol_id in enumerate(spec.param_symbol_ids)
        )
        self._session.flush()
        return definition

    def get(self, id: int) -> Definition:
        row = self._session.get(Definition, id)
        if row is None:
            raise NotFoundError("Definition", id)
        return row

    def get_by_public_id(self, public_id: str) -> Definition:
        row = self._session.scalar(
            select(Definition).where(Definition.public_id == public_id)
        )
        if row is None:
            raise NotFoundError("Definition", public_id)
        return row

    def get_by_name(self, name: str) -> Definition:
        row = self._session.scalar(select(Definition).where(Definition.name == name))
        if row is None:
            raise NotFoundError("Definition", name)
        return row

    def list_all(
        self, search: str | None = None, tag_ids: list[int] | None = None
    ) -> list[Definition]:
        stmt = select(Definition).order_by(Definition.id)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Definition.name.ilike(like), Definition.description.ilike(like)))
        if tag_ids:
            stmt = (
                stmt.join(DefinitionTag, DefinitionTag.definition_id == Definition.id)
                .where(DefinitionTag.tag_id.in_(tag_ids))
                .distinct()
            )
        return list(self._session.scalars(stmt))

    def set_description(self, id: int, description: str | None) -> Definition:
        definition = self.get(id)
        definition.description = description.strip() if description and description.strip() else None
        self._session.flush()
        return definition

    def set_display_formula(self, id: int, formula_id: int | None) -> Definition:
        definition = self.get(id)
        if formula_id is None:
            definition.display_formula_id = None
            definition.display_formula = None
        else:
            display_formula = self._get_formula_of_type(
                formula_id,
                FormulaTypeName.PROPOSITION,
                "definition display formula must be a proposition",
            )
            definition.display_formula_id = formula_id
            definition.display_formula = display_formula
        self._session.flush()
        return definition

    def get_symbol(self, definition_id: int) -> Symbol:
        definition = self.get(definition_id)
        return definition.new_symbol

    def get_axiom(self, definition_id: int) -> Axiom:
        self.get(definition_id)
        axiom = self._session.scalar(
            select(Axiom).where(Axiom.definition_id == definition_id)
        )
        if axiom is None:
            raise NotFoundError("Axiom", definition_id)
        return axiom

    def list_formal_params(self, definition_id: int) -> list[Symbol]:
        self.get(definition_id)
        return list(
            self._session.scalars(
                select(Symbol)
                .join(DefinitionFormalParam, Symbol.id == DefinitionFormalParam.param_symbol_id)
                .where(DefinitionFormalParam.definition_id == definition_id)
                .order_by(DefinitionFormalParam.ord)
            )
        )

    def compute_defining_formula_tokens(
        self,
        definition_input: DefinitionInput,
        new_symbol_id: int,
    ) -> list[Token]:
        spec = self._spec_for(definition_input)
        self._validate_body_and_params(spec)
        body_tokens = self._tokens_for_formula(spec.body_formula_id)

        if spec.kind == "function_desc":
            assert spec.value_symbol_id is not None
            eq = self._symbol_svc.get_by_role("equality")
            iff = self._symbol_svc.get_by_role("biconditional")
            forall = self._symbol_svc.get_by_role("universal_quantifier")

            core_tokens = [
                Token(symbol_id=iff.id),
                Token(symbol_id=eq.id),
                Token(symbol_id=new_symbol_id),
                *(Token(symbol_id=pid) for pid in spec.param_symbol_ids),
                Token(symbol_id=spec.value_symbol_id),
                *body_tokens,
            ]
            symbol_meta = self._formula_svc._load_symbol_meta(
                [*core_tokens, Token(symbol_id=forall.id)]
            )
            tokens = core_tokens
            # value variable is innermost (nearest the body), params wrap around it
            for variable_id in reversed((*spec.param_symbol_ids, spec.value_symbol_id)):
                tokens = abstract_and_quantify_pure(
                    tokens,
                    variable_symbol_id=variable_id,
                    forall_symbol_id=forall.id,
                    symbol_meta=symbol_meta,
                )
            return tokens

        connective = self._symbol_svc.get_by_role(spec.connective_role)

        if spec.quantifies_params:
            forall = self._symbol_svc.get_by_role("universal_quantifier")
            tokens = [
                Token(symbol_id=connective.id),
                Token(symbol_id=new_symbol_id),
                *(Token(symbol_id=param_id) for param_id in spec.param_symbol_ids),
                *body_tokens,
            ]
            symbol_meta = self._formula_svc._load_symbol_meta(
                [*tokens, Token(symbol_id=forall.id)]
            )
            for param_id in reversed(spec.param_symbol_ids):
                tokens = abstract_and_quantify_pure(
                    tokens,
                    variable_symbol_id=param_id,
                    forall_symbol_id=forall.id,
                    symbol_meta=symbol_meta,
                )
            return tokens

        if spec.kind == "logical":
            return [
                Token(symbol_id=connective.id),
                Token(symbol_id=new_symbol_id),
                *(Token(symbol_id=param_id) for param_id in spec.param_symbol_ids),
                *body_tokens,
            ]

        return [
            Token(symbol_id=connective.id),
            Token(symbol_id=new_symbol_id),
            Token(symbol_id=spec.param_symbol_ids[0]),
            Token(de_bruijn_index=0),
            *body_tokens,
        ]

    def compute_existence_uniqueness_statement_tokens(
        self,
        param_symbol_ids: Sequence[int],
        value_symbol_id: int,
        uniqueness_witness_symbol_id: int,
        body_formula_id: int,
    ) -> list[Token]:
        """forall params. exists y. (phi(params,y) and forall z. (phi(params,z) -> z=y))"""
        body_tokens = self._tokens_for_formula(body_formula_id)
        imp = self._symbol_svc.get_by_role("implication")
        eq = self._symbol_svc.get_by_role("equality")
        and_ = self._symbol_svc.get_by_name("∧")
        forall = self._symbol_svc.get_by_role("universal_quantifier")
        exists = self._symbol_svc.get_by_name("∃")

        symbol_meta = self._formula_svc._load_symbol_meta(
            [
                *body_tokens,
                Token(symbol_id=imp.id),
                Token(symbol_id=eq.id),
                Token(symbol_id=and_.id),
                Token(symbol_id=forall.id),
                Token(symbol_id=exists.id),
                Token(symbol_id=uniqueness_witness_symbol_id),
                Token(symbol_id=value_symbol_id),
                *(Token(symbol_id=pid) for pid in param_symbol_ids),
            ]
        )

        # phi(params, z) := phi with the value variable replaced by the witness
        # variable -- a plain free-symbol-for-free-symbol substitution, no
        # shifting concerns (both are unbound at this point).
        phi_z = apply_substitution_pure(
            body_tokens,
            prop_subst={},
            term_subst={value_symbol_id: [Token(symbol_id=uniqueness_witness_symbol_id)]},
            symbol_meta=symbol_meta,
        )
        uniqueness_imp = [
            Token(symbol_id=imp.id),
            *phi_z,
            Token(symbol_id=eq.id),
            Token(symbol_id=uniqueness_witness_symbol_id),
            Token(symbol_id=value_symbol_id),
        ]
        forall_z = abstract_and_quantify_pure(
            uniqueness_imp, uniqueness_witness_symbol_id, forall.id, symbol_meta
        )
        conj = [Token(symbol_id=and_.id), *body_tokens, *forall_z]
        exists_y = abstract_and_quantify_pure(conj, value_symbol_id, exists.id, symbol_meta)

        tokens = exists_y
        for param_id in reversed(param_symbol_ids):
            tokens = abstract_and_quantify_pure(tokens, param_id, forall.id, symbol_meta)
        return tokens

    def register_explicit_function(
        self,
        name: str,
        param_symbol_ids: Sequence[int],
        body_term_formula_id: int,
        remarks: str | None = None,
    ) -> Definition:
        """Register the direct defining axiom ``forall params. f(params)=B``.

        Since ``B`` is already a well-formed term, no existence/uniqueness
        proof is required.  Predicate-characterized functions remain the
        separate, proof-obligated ``function_desc`` kind.
        """
        return self.register(
            FunctionDefinitionInput(
                name=name,
                param_symbol_ids=tuple(param_symbol_ids),
                body_formula_id=body_term_formula_id,
                remarks=remarks,
            )
        )

    # `_prove_explicit_existence_uniqueness()` used to live here: an authoring
    # helper that built the ∃! proof for the descriptive predicate `y = body`
    # so that `function_desc` validation could be exercised. It was only ever
    # called from tests, and it cited the natural-deduction layer
    # (`nd_and_intro`, `nd_ax_exists_intro`), which no longer exists -- the ∃!
    # statement itself needs ∧ and ∃, and `hilbert_core` axiomatises only
    # →/∀/=. Recover it from git history together with a logical layer that
    # gives ∧ and ∃ axioms.

    def _verified_proof_id(self, theorem_id: int) -> int:
        proof = self._session.scalar(
            select(Proof).where(Proof.theorem_id == theorem_id, Proof.status == "verified")
        )
        if proof is None:
            raise ValidationError(f"no verified proof for theorem id {theorem_id}")
        return proof.id

    def _spec_for(self, definition_input: DefinitionInput) -> _DefinitionSpec:
        if isinstance(definition_input, PredicateDefinitionInput):
            return _DefinitionSpec(
                name=definition_input.name,
                kind="predicate",
                symbol_type_name=SymbolTypeName.PREDICATE,
                arity=len(definition_input.param_symbol_ids),
                param_symbol_ids=definition_input.param_symbol_ids,
                body_formula_id=definition_input.body_formula_id,
                body_formula_type=FormulaTypeName.PROPOSITION,
                connective_role="biconditional",
                quantifies_params=True,
                requires_existence_proof=definition_input.requires_existence_proof,
                requires_uniqueness_proof=definition_input.requires_uniqueness_proof,
                remarks=definition_input.remarks,
                latex_template=definition_input.latex_template,
            )
        if isinstance(definition_input, FunctionDefinitionInput):
            return _DefinitionSpec(
                name=definition_input.name,
                kind="function",
                symbol_type_name=SymbolTypeName.FUNCTION,
                arity=len(definition_input.param_symbol_ids),
                param_symbol_ids=definition_input.param_symbol_ids,
                body_formula_id=definition_input.body_formula_id,
                body_formula_type=FormulaTypeName.TERM,
                connective_role="equality",
                quantifies_params=True,
                requires_existence_proof=False,
                requires_uniqueness_proof=False,
                remarks=definition_input.remarks,
                latex_template=definition_input.latex_template,
            )
        if isinstance(definition_input, DescriptiveFunctionDefinitionInput):
            return _DefinitionSpec(
                name=definition_input.name,
                kind="function_desc",
                symbol_type_name=SymbolTypeName.FUNCTION,
                arity=len(definition_input.param_symbol_ids),
                param_symbol_ids=definition_input.param_symbol_ids,
                body_formula_id=definition_input.body_formula_id,
                body_formula_type=FormulaTypeName.PROPOSITION,
                connective_role="equality",
                quantifies_params=False,
                requires_existence_proof=True,
                requires_uniqueness_proof=True,
                remarks=definition_input.remarks,
                latex_template=definition_input.latex_template,
                value_symbol_id=definition_input.value_symbol_id,
                uniqueness_witness_symbol_id=definition_input.uniqueness_witness_symbol_id,
                existence_uniqueness_proof_id=definition_input.existence_uniqueness_proof_id,
            )
        if isinstance(definition_input, LogicalDefinitionInput):
            return _DefinitionSpec(
                name=definition_input.name,
                kind="logical",
                symbol_type_name=SymbolTypeName.LOGICAL,
                arity=len(definition_input.param_symbol_ids),
                param_symbol_ids=definition_input.param_symbol_ids,
                body_formula_id=definition_input.body_formula_id,
                body_formula_type=FormulaTypeName.PROPOSITION,
                connective_role="biconditional",
                quantifies_params=False,
                requires_existence_proof=False,
                requires_uniqueness_proof=False,
                remarks=definition_input.remarks,
                latex_template=definition_input.latex_template,
            )
        if isinstance(definition_input, QuantPropDefinitionInput):
            return _DefinitionSpec(
                name=definition_input.name,
                kind="quant_prop",
                symbol_type_name=SymbolTypeName.QUANT_PROP,
                arity=1,
                param_symbol_ids=(definition_input.param_symbol_id,),
                body_formula_id=definition_input.body_formula_id,
                body_formula_type=FormulaTypeName.PROPOSITION,
                connective_role="biconditional",
                quantifies_params=False,
                requires_existence_proof=False,
                requires_uniqueness_proof=False,
                remarks=definition_input.remarks,
                latex_template=definition_input.latex_template,
            )
        if isinstance(definition_input, QuantTermDefinitionInput):
            # Same shape as quant_prop, two columns apart: the body is a term and
            # the defining axiom is an equation. compute_defining_formula_tokens()
            # needs no branch of its own -- its final `return` builds
            # `<connective> N phi #0 <body>` for both.
            return _DefinitionSpec(
                name=definition_input.name,
                kind="quant_term",
                symbol_type_name=SymbolTypeName.QUANT_TERM,
                arity=1,
                param_symbol_ids=(definition_input.param_symbol_id,),
                body_formula_id=definition_input.body_formula_id,
                body_formula_type=FormulaTypeName.TERM,
                connective_role="equality",
                quantifies_params=False,
                requires_existence_proof=False,
                requires_uniqueness_proof=False,
                remarks=definition_input.remarks,
                latex_template=definition_input.latex_template,
            )
        raise TypeError(f"unsupported definition input: {type(definition_input)!r}")

    def _ensure_name_available(self, name: str) -> None:
        existing_symbol = self._session.scalar(select(Symbol).where(Symbol.name == name))
        if existing_symbol is not None:
            raise ConflictError("Symbol", "name", name)

        existing_definition = self._session.scalar(
            select(Definition).where(Definition.name == name)
        )
        if existing_definition is not None:
            raise ConflictError("Definition", "name", name)

        axiom_name = definition_axiom_name(name)
        existing_axiom = self._session.scalar(
            select(Axiom).where(Axiom.name.in_(axiom_lookup_names(axiom_name)))
        )
        if existing_axiom is not None:
            raise ConflictError("Axiom", "name", axiom_name)

    def _validate_body_and_params(self, spec: _DefinitionSpec) -> None:
        self._get_formula_of_type(
            spec.body_formula_id,
            spec.body_formula_type,
            f"{spec.kind} definition body must be a {spec.body_formula_type.value}",
        )
        param_symbols = self._get_param_symbols(spec.param_symbol_ids)

        if len(set(spec.param_symbol_ids)) != len(spec.param_symbol_ids):
            raise ValidationError("definition formal parameters must be distinct")

        for symbol in param_symbols:
            if spec.kind in {"predicate", "function", "function_desc"}:
                self._validate_term_free_param(symbol)
            elif spec.kind == "logical":
                self._validate_logical_param(symbol)
            else:
                self._validate_quant_param(symbol)

        if spec.kind == "function_desc":
            self._validate_function_desc(spec)

    def _validate_function_desc(self, spec: _DefinitionSpec) -> None:
        assert spec.value_symbol_id is not None
        assert spec.uniqueness_witness_symbol_id is not None
        assert spec.existence_uniqueness_proof_id is not None

        scratch_ids = (spec.value_symbol_id, spec.uniqueness_witness_symbol_id)
        if len(set(scratch_ids)) != len(scratch_ids) or any(
            sid in spec.param_symbol_ids for sid in scratch_ids
        ):
            raise ValidationError(
                "value_symbol_id/uniqueness_witness_symbol_id must be distinct "
                "from each other and from param_symbol_ids"
            )
        for symbol in self._get_param_symbols(scratch_ids):
            self._validate_term_free_param(symbol)

        proof = self._session.get(Proof, spec.existence_uniqueness_proof_id)
        if proof is None:
            raise NotFoundError("Proof", spec.existence_uniqueness_proof_id)
        if proof.status != "verified":
            raise ValidationError("existence_uniqueness_proof must be verified")

        theorem = self._session.get(Theorem, proof.theorem_id)
        if theorem is None:
            raise NotFoundError("Theorem", proof.theorem_id)
        has_premise = self._session.scalar(
            select(TheoremPremise.formula_id).where(TheoremPremise.theorem_id == theorem.id)
        )
        if has_premise is not None:
            raise ValidationError(
                "existence_uniqueness_proof's theorem must have no premises"
            )

        expected_tokens = self.compute_existence_uniqueness_statement_tokens(
            spec.param_symbol_ids,
            spec.value_symbol_id,
            spec.uniqueness_witness_symbol_id,
            spec.body_formula_id,
        )
        expected_formula = self._formula_svc.register(expected_tokens)
        if theorem.conclusion_formula_id != expected_formula.id:
            raise ValidationError(
                "existence_uniqueness_proof does not prove the required "
                "exists-unique statement for this definition"
            )

    def _get_param_symbols(self, param_symbol_ids: Sequence[int]) -> list[Symbol]:
        if not param_symbol_ids:
            return []

        symbols = list(
            self._session.scalars(
                select(Symbol)
                .options(joinedload(Symbol.symbol_type))
                .where(Symbol.id.in_(set(param_symbol_ids)))
            )
        )
        by_id = {symbol.id: symbol for symbol in symbols}
        for param_symbol_id in param_symbol_ids:
            if param_symbol_id not in by_id:
                raise NotFoundError("Symbol", param_symbol_id)
        return [by_id[param_symbol_id] for param_symbol_id in param_symbol_ids]

    def _validate_term_free_param(self, symbol: Symbol) -> None:
        if symbol.symbol_type.name != SymbolTypeName.FREE_TERM_VAR.value:
            raise ValidationError(
                "predicate/function definition parameters must be term-free-variable symbols"
            )

    def _validate_logical_param(self, symbol: Symbol) -> None:
        if (
            symbol.symbol_type.name != SymbolTypeName.FREE_PROP_VAR.value
            or symbol.arity != 0
        ):
            raise ValidationError(
                "logical definition parameters must be arity-0 proposition-free-variable symbols"
            )

    def _validate_quant_param(self, symbol: Symbol) -> None:
        if (
            symbol.symbol_type.name != SymbolTypeName.FREE_PROP_VAR.value
            or symbol.arity != 1
        ):
            raise ValidationError(
                "quantifier definition parameter must be a proposition-free-variable symbol with arity == 1"
            )

    def _get_formula_of_type(
        self,
        formula_id: int,
        formula_type: FormulaTypeName,
        message: str,
    ) -> Formula:
        formula = self._session.get(Formula, formula_id)
        if formula is None:
            raise NotFoundError("Formula", formula_id)
        if formula.formula_type.name != formula_type.value:
            raise ValidationError(message)
        return formula

    def _tokens_for_formula(self, formula_id: int) -> list[Token]:
        self._session.get(Formula, formula_id)
        rows = self._session.scalars(
            select(FormulaToken)
            .where(FormulaToken.formula_id == formula_id)
            .order_by(FormulaToken.position)
        ).all()
        return [
            Token(symbol_id=row.symbol_id)
            if row.symbol_id is not None
            else Token(de_bruijn_index=row.de_bruijn_index)
            for row in rows
        ]
