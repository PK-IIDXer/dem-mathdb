"""Regression tests pinning `inference_rule.kind` and `.tier` to the ledger
documented in docs/design/kernel/trust-boundary.md §2,
§5 (rule 1) and §9.5.

If either the seed data or the DB CHECK constraint gains a new kind without a
matching update here (and to the design doc's T-table), these tests fail --
that is the point: adding a non-core inference rule must be a deliberate,
visible change, not a side effect of some other patch.

The tier assertions pin the same thing one level deeper. A kind says what the
rule does; a tier says what justifies it, and therefore what removing it would
cost -- Tier 1 an inlining, Tier 2 a whole-proof transformation, Tier 3 nothing
that exists. Getting that wrong is how A5-A7 shipped three recognizers, one of
which proved a refutable statement.
"""

from __future__ import annotations

import re

from dem.db.models.inference import InferenceRule
from dem.db.seed import INFERENCE_RULE_SEEDS

# Tier 0 (primitive): the trusted computing base.
CORE_KINDS = frozenset({"modus_ponens", "generalization"})

# Tier 2 (admissible, §9.5): shrinks `premise_deps` or carries an eigenvariable
# condition, so it is justified by a *whole-proof transformation* rather than by
# a schematic derivation. Admitting one requires that procedure plus an
# invariant-(E)-shaped test (see tests/test_soundness_invariants.py); for
# `implication_intro` the procedure is
# `HilbertLemmaToolkit.expand_implication_intro()`.
ADMISSIBLE_KINDS = frozenset({"implication_intro"})

# Tier 3 (recognizer, §9.5): justified only by Python matching tokens, with no
# elimination procedure. Adding one is forbidden, and the public candidate has
# none. An empty set here is the design completion condition, so this
# constant staying empty is the thing worth watching.
DOCUMENTED_NON_CORE_KINDS: frozenset[str] = frozenset()

DOCUMENTED_KINDS = CORE_KINDS | ADMISSIBLE_KINDS | DOCUMENTED_NON_CORE_KINDS

# The tier each kind must be seeded at, and -- for admissible rules -- the
# elimination procedure it must name. This is the ledger the `tier` column
# exists for: a rule's tier is a claim about what it would cost to remove it,
# so it may not drift without the claim being restated here.
DOCUMENTED_TIERS: dict[str, tuple[str, str | None]] = {
    "modus_ponens": ("primitive", None),
    "generalization": ("primitive", None),
    "implication_intro": ("admissible", "expand_implication_intro"),
}


def _constraint(name: str) -> str:
    constraint = next(
        c
        for c in InferenceRule.__table__.constraints
        if getattr(c, "name", None) == name
    )
    return str(constraint.sqltext)


def test_inference_rule_seed_kinds_match_documented_ledger() -> None:
    seeded_kinds = frozenset(kind for _, kind, *_ in INFERENCE_RULE_SEEDS)
    assert seeded_kinds == DOCUMENTED_KINDS


def test_known_kind_check_constraint_matches_documented_ledger() -> None:
    constrained_kinds = frozenset(
        re.findall(r"'([a-z0-9_]+)'", _constraint("ck_inference_rule_known_kind"))
    )
    assert constrained_kinds == DOCUMENTED_KINDS


def test_known_tier_check_constraint_lists_exactly_the_four_tiers() -> None:
    """Including `recognizer`, the forbidden one, which no rule sits at any
    more. Naming the forbidden tier is still the point: a rule justified by
    nothing has to say so in the row, rather than passing as an ordinary
    `inference_rule` entry the way A5-A7 did."""
    tiers = frozenset(
        re.findall(r"'([a-z]+)'", _constraint("ck_inference_rule_known_tier"))
    )
    assert tiers == {"primitive", "derived", "admissible", "recognizer"}


def test_inference_rule_seed_tiers_match_documented_ledger() -> None:
    seeded = {
        kind: (tier, procedure)
        for _, kind, tier, procedure, *_ in INFERENCE_RULE_SEEDS
    }
    assert seeded == DOCUMENTED_TIERS


def test_no_rule_is_seeded_at_the_forbidden_tier_without_being_documented() -> None:
    """Tier 3 is forbidden (§9.5) and, since §6.2, unpopulated -- so this test
    now reads as "no recognizers exist", and it is what fails if someone adds
    one back."""
    recognizers = {
        kind for _, kind, tier, *_ in INFERENCE_RULE_SEEDS if tier == "recognizer"
    }
    assert recognizers == DOCUMENTED_NON_CORE_KINDS


def test_admissible_rules_must_name_an_elimination_procedure() -> None:
    """The CHECK is an equality, not an implication: an admissible rule must
    name its procedure, and no other tier may claim to have one."""
    assert (
        "(tier = 'admissible') = (elimination_procedure IS NOT NULL)"
        in _constraint("ck_inference_rule_admissible_requires_elimination_procedure")
    )
    for _, kind, tier, procedure, *_ in INFERENCE_RULE_SEEDS:
        assert (tier == "admissible") == (procedure is not None), kind
