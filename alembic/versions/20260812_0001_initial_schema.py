"""initial schema

Initial public schema, collapsed from the private development migration chain.
The public migration contains only the generic storage and validation model.

Two differences from the collapsed chain, both consequences of that removal:

- `proof_macro` is not part of the public schema.
- `inference_rule.known_kind` admits only `modus_ponens`, `generalization` and
  `implication_intro`. The public completion condition (zero non-core kinds)
  holds. The `known_tier` CHECK
  still names `recognizer`, deliberately: the forbidden tier has to stay
  sayable so that adding one back is a visible act.

The SQLite path never runs migrations (`DemApi.create_schema()` builds the
schema directly), so the server defaults here are PostgreSQL-shaped, matching
the chain this replaces.

Revision ID: 20260812_0001
Revises:
Create Date: 2026-08-12 02:30:27.626308
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '20260812_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('axiom_system',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_axiom_system')),
    sa.UniqueConstraint('name', name=op.f('uq_axiom_system_name'))
    )
    op.create_table('formula_type',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_formula_type')),
    sa.UniqueConstraint('name', name=op.f('uq_formula_type_name'))
    )
    op.create_table('inference_rule',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('tier', sa.Text(), nullable=False),
    sa.Column('elimination_procedure', sa.Text(), nullable=True),
    sa.Column('premise_count', sa.Integer(), nullable=False),
    sa.Column('requires_variable_param', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("(tier = 'admissible') = (elimination_procedure IS NOT NULL)", name=op.f('ck_inference_rule_admissible_requires_elimination_procedure')),
    sa.CheckConstraint("kind IN ('modus_ponens', 'generalization', 'implication_intro')", name=op.f('ck_inference_rule_known_kind')),
    sa.CheckConstraint("tier IN ('primitive', 'derived', 'admissible', 'recognizer')", name=op.f('ck_inference_rule_known_tier')),
    sa.CheckConstraint('premise_count >= 0', name=op.f('ck_inference_rule_premise_count_nonnegative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_inference_rule')),
    sa.UniqueConstraint('name', name=op.f('uq_inference_rule_name'))
    )
    op.create_table('tag',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tag')),
    sa.UniqueConstraint('name', name=op.f('uq_tag_name'))
    )
    op.create_table('formula',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('formula_type_id', sa.Integer(), nullable=False),
    sa.Column('hash', sa.Text(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('token_count > 0', name=op.f('ck_formula_token_count_positive')),
    sa.ForeignKeyConstraint(['formula_type_id'], ['formula_type.id'], name=op.f('fk_formula_formula_type_id_formula_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_formula')),
    sa.UniqueConstraint('hash', name=op.f('uq_formula_hash'))
    )
    op.create_table('symbol_type',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('output_formula_type_id', sa.Integer(), nullable=False),
    sa.Column('input_formula_type_id', sa.Integer(), nullable=True),
    sa.Column('fixed_arity', sa.Integer(), nullable=True),
    sa.Column('is_quantifier', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('(input_formula_type_id IS NULL AND fixed_arity = 0) OR (input_formula_type_id IS NOT NULL)', name=op.f('ck_symbol_type_input_or_zero_arity')),
    sa.CheckConstraint('fixed_arity IS NULL OR fixed_arity >= 0', name=op.f('ck_symbol_type_fixed_arity_nonnegative')),
    sa.ForeignKeyConstraint(['input_formula_type_id'], ['formula_type.id'], name=op.f('fk_symbol_type_input_formula_type_id_formula_type')),
    sa.ForeignKeyConstraint(['output_formula_type_id'], ['formula_type.id'], name=op.f('fk_symbol_type_output_formula_type_id_formula_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_symbol_type')),
    sa.UniqueConstraint('name', name=op.f('uq_symbol_type_name'))
    )
    op.create_table('symbol',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('symbol_type_id', sa.Integer(), nullable=False),
    sa.Column('arity', sa.Integer(), nullable=False),
    sa.Column('is_primitive', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('namespace_id', sa.Integer(), nullable=True),
    sa.Column('notation_kind', sa.Text(), server_default='prefix', nullable=False),
    sa.Column('precedence', sa.Integer(), nullable=True),
    sa.Column('latex_template', sa.Text(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("(notation_kind = 'infix' AND precedence IS NOT NULL) OR (notation_kind = 'prefix' AND precedence IS NULL)", name=op.f('ck_symbol_precedence_matches_notation_kind')),
    sa.CheckConstraint("notation_kind = 'prefix' OR arity = 2", name=op.f('ck_symbol_infix_requires_arity_two')),
    sa.CheckConstraint("notation_kind IN ('prefix', 'infix')", name=op.f('ck_symbol_known_notation_kind')),
    sa.CheckConstraint('arity >= 0', name=op.f('ck_symbol_arity_nonnegative')),
    sa.ForeignKeyConstraint(['symbol_type_id'], ['symbol_type.id'], name=op.f('fk_symbol_symbol_type_id_symbol_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_symbol')),
    sa.UniqueConstraint('name', name=op.f('uq_symbol_name'))
    )
    op.create_table('theorem',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('conclusion_formula_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('conjecture', 'proven')", name=op.f('ck_theorem_known_status')),
    sa.ForeignKeyConstraint(['conclusion_formula_id'], ['formula.id'], name=op.f('fk_theorem_conclusion_formula_id_formula')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_theorem')),
    sa.UniqueConstraint('name', name=op.f('uq_theorem_name'))
    )
    op.create_table('formula_token',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('formula_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('symbol_id', sa.Integer(), nullable=True),
    sa.Column('de_bruijn_index', sa.Integer(), nullable=True),
    sa.CheckConstraint('(symbol_id IS NOT NULL AND de_bruijn_index IS NULL) OR (symbol_id IS NULL AND de_bruijn_index IS NOT NULL AND de_bruijn_index >= 0)', name=op.f('ck_formula_token_exactly_one_kind')),
    sa.CheckConstraint('position >= 0', name=op.f('ck_formula_token_position_nonnegative')),
    sa.ForeignKeyConstraint(['formula_id'], ['formula.id'], name=op.f('fk_formula_token_formula_id_formula'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['symbol_id'], ['symbol.id'], name=op.f('fk_formula_token_symbol_id_symbol')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_formula_token')),
    sa.UniqueConstraint('formula_id', 'position', name=op.f('uq_formula_token_formula_id'))
    )
    op.create_table('proof',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('theorem_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'verified', 'rejected')", name=op.f('ck_proof_known_status')),
    sa.ForeignKeyConstraint(['theorem_id'], ['theorem.id'], name=op.f('fk_proof_theorem_id_theorem')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_proof'))
    )
    op.create_table('symbol_role',
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('symbol_id', sa.Integer(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("role IN ('implication', 'universal_quantifier', 'biconditional', 'equality')", name=op.f('ck_symbol_role_known_role')),
    sa.ForeignKeyConstraint(['symbol_id'], ['symbol.id'], name=op.f('fk_symbol_role_symbol_id_symbol')),
    sa.PrimaryKeyConstraint('role', name=op.f('pk_symbol_role')),
    sa.UniqueConstraint('symbol_id', name=op.f('uq_symbol_role_symbol_id'))
    )
    op.create_table('theorem_premise',
    sa.Column('theorem_id', sa.Integer(), nullable=False),
    sa.Column('ord', sa.Integer(), nullable=False),
    sa.Column('formula_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('ord >= 0', name=op.f('ck_theorem_premise_ord_nonnegative')),
    sa.ForeignKeyConstraint(['formula_id'], ['formula.id'], name=op.f('fk_theorem_premise_formula_id_formula')),
    sa.ForeignKeyConstraint(['theorem_id'], ['theorem.id'], name=op.f('fk_theorem_premise_theorem_id_theorem'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('theorem_id', 'ord', name=op.f('pk_theorem_premise'))
    )
    op.create_table('theorem_tag',
    sa.Column('theorem_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], name=op.f('fk_theorem_tag_tag_id_tag'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['theorem_id'], ['theorem.id'], name=op.f('fk_theorem_tag_theorem_id_theorem'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('theorem_id', 'tag_id', name=op.f('pk_theorem_tag'))
    )
    op.create_table('definition',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('new_symbol_id', sa.Integer(), nullable=False),
    sa.Column('requires_existence_proof', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('requires_uniqueness_proof', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('existence_uniqueness_proof_id', sa.Integer(), nullable=True),
    sa.Column('display_formula_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("(kind = 'function_desc' AND existence_uniqueness_proof_id IS NOT NULL) OR (kind <> 'function_desc' AND existence_uniqueness_proof_id IS NULL)", name=op.f('ck_definition_function_desc_requires_proof')),
    sa.CheckConstraint("kind IN ('predicate', 'function', 'logical', 'quant_prop', 'function_desc')", name=op.f('ck_definition_known_kind')),
    sa.ForeignKeyConstraint(['display_formula_id'], ['formula.id'], name=op.f('fk_definition_display_formula_id_formula')),
    sa.ForeignKeyConstraint(['existence_uniqueness_proof_id'], ['proof.id'], name=op.f('fk_definition_existence_uniqueness_proof_id_proof')),
    sa.ForeignKeyConstraint(['new_symbol_id'], ['symbol.id'], name=op.f('fk_definition_new_symbol_id_symbol')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_definition')),
    sa.UniqueConstraint('name', name=op.f('uq_definition_name')),
    sa.UniqueConstraint('new_symbol_id', name=op.f('uq_definition_new_symbol_id'))
    )
    op.create_table('axiom',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('formula_id', sa.Integer(), nullable=False),
    sa.Column('origin_kind', sa.Text(), nullable=False),
    sa.Column('definition_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("(origin_kind = 'primitive' AND definition_id IS NULL) OR (origin_kind = 'definition_derived' AND definition_id IS NOT NULL)", name=op.f('ck_axiom_origin_definition_consistency')),
    sa.CheckConstraint("origin_kind IN ('primitive', 'definition_derived')", name=op.f('ck_axiom_known_origin_kind')),
    sa.ForeignKeyConstraint(['definition_id'], ['definition.id'], name=op.f('fk_axiom_definition_id_definition'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['formula_id'], ['formula.id'], name=op.f('fk_axiom_formula_id_formula')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_axiom')),
    sa.UniqueConstraint('definition_id', name=op.f('uq_axiom_definition_id')),
    sa.UniqueConstraint('name', name=op.f('uq_axiom_name'))
    )
    op.create_table('definition_formal_param',
    sa.Column('definition_id', sa.Integer(), nullable=False),
    sa.Column('ord', sa.Integer(), nullable=False),
    sa.Column('param_symbol_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('ord >= 0', name=op.f('ck_definition_formal_param_ord_nonnegative')),
    sa.ForeignKeyConstraint(['definition_id'], ['definition.id'], name=op.f('fk_definition_formal_param_definition_id_definition'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['param_symbol_id'], ['symbol.id'], name=op.f('fk_definition_formal_param_param_symbol_id_symbol')),
    sa.PrimaryKeyConstraint('definition_id', 'ord', name=op.f('pk_definition_formal_param'))
    )
    op.create_table('definition_tag',
    sa.Column('definition_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['definition_id'], ['definition.id'], name=op.f('fk_definition_tag_definition_id_definition'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], name=op.f('fk_definition_tag_tag_id_tag'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('definition_id', 'tag_id', name=op.f('pk_definition_tag'))
    )
    op.create_table('axiom_system_member',
    sa.Column('axiom_system_id', sa.Integer(), nullable=False),
    sa.Column('axiom_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['axiom_id'], ['axiom.id'], name=op.f('fk_axiom_system_member_axiom_id_axiom'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['axiom_system_id'], ['axiom_system.id'], name=op.f('fk_axiom_system_member_axiom_system_id_axiom_system'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('axiom_system_id', 'axiom_id', name=op.f('pk_axiom_system_member'))
    )
    op.create_table('axiom_tag',
    sa.Column('axiom_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['axiom_id'], ['axiom.id'], name=op.f('fk_axiom_tag_axiom_id_axiom'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], name=op.f('fk_axiom_tag_tag_id_tag'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('axiom_id', 'tag_id', name=op.f('pk_axiom_tag'))
    )
    op.create_table('proof_step',
    sa.Column('proof_id', sa.Integer(), nullable=False),
    sa.Column('ord', sa.Integer(), nullable=False),
    sa.Column('step_kind', sa.Text(), nullable=False),
    sa.Column('conclusion_formula_id', sa.Integer(), nullable=False),
    sa.Column('premise_ord', sa.Integer(), nullable=True),
    sa.Column('axiom_id', sa.Integer(), nullable=True),
    sa.Column('applied_proof_id', sa.Integer(), nullable=True),
    sa.Column('inference_rule_id', sa.Integer(), nullable=True),
    sa.Column('gen_variable_symbol_id', sa.Integer(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("(step_kind = 'premise' AND premise_ord IS NOT NULL AND axiom_id IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'assumption' AND premise_ord IS NULL AND axiom_id IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'axiom' AND axiom_id IS NOT NULL AND premise_ord IS NULL AND applied_proof_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'theorem' AND applied_proof_id IS NOT NULL AND premise_ord IS NULL AND axiom_id IS NULL AND inference_rule_id IS NULL) OR (step_kind = 'rule' AND inference_rule_id IS NOT NULL AND premise_ord IS NULL AND axiom_id IS NULL AND applied_proof_id IS NULL)", name=op.f('ck_proof_step_kind_column_consistency')),
    sa.CheckConstraint("step_kind = 'rule' OR gen_variable_symbol_id IS NULL", name=op.f('ck_proof_step_gen_variable_only_for_rule')),
    sa.CheckConstraint("step_kind IN ('premise', 'assumption', 'axiom', 'theorem', 'rule')", name=op.f('ck_proof_step_known_step_kind')),
    sa.CheckConstraint('ord >= 0', name=op.f('ck_proof_step_ord_nonnegative')),
    sa.ForeignKeyConstraint(['applied_proof_id'], ['proof.id'], name=op.f('fk_proof_step_applied_proof_id_proof')),
    sa.ForeignKeyConstraint(['axiom_id'], ['axiom.id'], name=op.f('fk_proof_step_axiom_id_axiom')),
    sa.ForeignKeyConstraint(['conclusion_formula_id'], ['formula.id'], name=op.f('fk_proof_step_conclusion_formula_id_formula')),
    sa.ForeignKeyConstraint(['gen_variable_symbol_id'], ['symbol.id'], name=op.f('fk_proof_step_gen_variable_symbol_id_symbol')),
    sa.ForeignKeyConstraint(['inference_rule_id'], ['inference_rule.id'], name=op.f('fk_proof_step_inference_rule_id_inference_rule')),
    sa.ForeignKeyConstraint(['proof_id'], ['proof.id'], name=op.f('fk_proof_step_proof_id_proof'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('proof_id', 'ord', name=op.f('pk_proof_step'))
    )
    op.create_table('proof_step_arg',
    sa.Column('proof_id', sa.Integer(), nullable=False),
    sa.Column('step_ord', sa.Integer(), nullable=False),
    sa.Column('arg_ord', sa.Integer(), nullable=False),
    sa.Column('referenced_step_ord', sa.Integer(), nullable=False),
    sa.CheckConstraint('arg_ord >= 0', name=op.f('ck_proof_step_arg_arg_ord_nonnegative')),
    sa.CheckConstraint('referenced_step_ord < step_ord', name=op.f('ck_proof_step_arg_references_prior_step')),
    sa.ForeignKeyConstraint(['proof_id', 'referenced_step_ord'], ['proof_step.proof_id', 'proof_step.ord'], name='fk_proof_step_arg_referenced_step'),
    sa.ForeignKeyConstraint(['proof_id', 'step_ord'], ['proof_step.proof_id', 'proof_step.ord'], name='fk_proof_step_arg_step', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('proof_id', 'step_ord', 'arg_ord', name=op.f('pk_proof_step_arg'))
    )
    op.create_table('proof_step_subst_prop',
    sa.Column('proof_id', sa.Integer(), nullable=False),
    sa.Column('step_ord', sa.Integer(), nullable=False),
    sa.Column('source_symbol_id', sa.Integer(), nullable=False),
    sa.Column('body_formula_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['body_formula_id'], ['formula.id'], name=op.f('fk_proof_step_subst_prop_body_formula_id_formula')),
    sa.ForeignKeyConstraint(['proof_id', 'step_ord'], ['proof_step.proof_id', 'proof_step.ord'], name=op.f('fk_proof_step_subst_prop_proof_id_proof_step'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_symbol_id'], ['symbol.id'], name=op.f('fk_proof_step_subst_prop_source_symbol_id_symbol')),
    sa.PrimaryKeyConstraint('proof_id', 'step_ord', 'source_symbol_id', name=op.f('pk_proof_step_subst_prop'))
    )
    op.create_table('proof_step_subst_term',
    sa.Column('proof_id', sa.Integer(), nullable=False),
    sa.Column('step_ord', sa.Integer(), nullable=False),
    sa.Column('source_symbol_id', sa.Integer(), nullable=False),
    sa.Column('target_formula_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['proof_id', 'step_ord'], ['proof_step.proof_id', 'proof_step.ord'], name=op.f('fk_proof_step_subst_term_proof_id_proof_step'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_symbol_id'], ['symbol.id'], name=op.f('fk_proof_step_subst_term_source_symbol_id_symbol')),
    sa.ForeignKeyConstraint(['target_formula_id'], ['formula.id'], name=op.f('fk_proof_step_subst_term_target_formula_id_formula')),
    sa.PrimaryKeyConstraint('proof_id', 'step_ord', 'source_symbol_id', name=op.f('pk_proof_step_subst_term'))
    )
    op.create_table('proof_step_subst_prop_param',
    sa.Column('proof_id', sa.Integer(), nullable=False),
    sa.Column('step_ord', sa.Integer(), nullable=False),
    sa.Column('source_symbol_id', sa.Integer(), nullable=False),
    sa.Column('ord', sa.Integer(), nullable=False),
    sa.Column('formal_param_symbol_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('ord >= 0', name=op.f('ck_proof_step_subst_prop_param_ord_nonnegative')),
    sa.ForeignKeyConstraint(['formal_param_symbol_id'], ['symbol.id'], name=op.f('fk_proof_step_subst_prop_param_formal_param_symbol_id_symbol')),
    sa.ForeignKeyConstraint(['proof_id', 'step_ord', 'source_symbol_id'], ['proof_step_subst_prop.proof_id', 'proof_step_subst_prop.step_ord', 'proof_step_subst_prop.source_symbol_id'], name=op.f('fk_proof_step_subst_prop_param_proof_id_proof_step_subst_prop'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('proof_id', 'step_ord', 'source_symbol_id', 'ord', name=op.f('pk_proof_step_subst_prop_param'))
    )


def downgrade() -> None:
    op.drop_table('proof_step_subst_prop_param')
    op.drop_table('proof_step_subst_term')
    op.drop_table('proof_step_subst_prop')
    op.drop_table('proof_step_arg')
    op.drop_table('proof_step')
    op.drop_table('axiom_tag')
    op.drop_table('axiom_system_member')
    op.drop_table('definition_tag')
    op.drop_table('definition_formal_param')
    op.drop_table('axiom')
    op.drop_table('definition')
    op.drop_table('theorem_tag')
    op.drop_table('theorem_premise')
    op.drop_table('symbol_role')
    op.drop_table('proof')
    op.drop_table('formula_token')
    op.drop_table('theorem')
    op.drop_table('symbol')
    op.drop_table('symbol_type')
    op.drop_table('formula')
    op.drop_table('tag')
    op.drop_table('inference_rule')
    op.drop_table('formula_type')
    op.drop_table('axiom_system')
