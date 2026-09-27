# Repository instructions for AI agents

## Validation comes before performance

DEM's mathematical validation is the highest-priority engineering constraint.

- A performance change must not accept any input that the current code rejects.
- Do not weaken, skip, or mock formula, proof, database, or API validation.
- A validation-path change requires adversarial accept/reject tests against the old and new behavior, plus a mutation check showing that tests detect a weakened guard.
- If equivalence or stricter behavior cannot be demonstrated, do not implement the optimization.

## Foundations are data

The bundled seed is one foundation, not DEM's foundation. Axioms, definitions, axiom systems, and foundation-specific symbols are data.

- Do not hard-code bundled-seed names, public IDs, axioms, or notation as behavior for every workspace.
- Only the logical core shared by every supported foundation may be built into the kernel.
- Judge changes by whether they preserve or strengthen formal validation, not by whether they fit the bundled seed.

## Seed and test discipline

- Every generated proof must be validated; never bypass validation to speed up tests.
- Use the narrowest seed phase that provides the data a test needs.
- Build the small A-only seed in an isolated database for each test scope.
- After changing seeds, proof services, or seed fixtures, run the affected test twice with durations and then run the full suite.

## Public-repository scope

- Keep this repository free of credentials, private deployment details, business plans, personal data, and material copied from private development history.
- Update `THIRD_PARTY_NOTICES.md` when adding third-party material.
- Do not publish bundled source-derived content until its redistribution status is documented.
