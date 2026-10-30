# dem-mathdb

DEM stores formulas, axiom systems, theorems, and machine-checked proof steps.
This snapshot contains the reviewed A-only logical foundation and independent
logic demonstrations. It does not include optional mathematical corpora.

## Public data

The core supplies primitive symbols `⊥ ¬ ∨ ∧ → ↔ ∀ ∃ =`, the inference rules
`MP`, `Gen`, `ImpIntro`, and eight Hilbert schemas (K, S, universal elimination
and distribution, equality reflexivity and substitution, vacuous universal
introduction, and Peirce). Its axiom systems are `hilbert_core` and
`hilbert_classical`.

Independent demonstrations add a definition and derived theorems with validated
proofs, including self-implication, implication chaining, theorem citation and a
classical implication example. Their construction uses only the public core.
`dem.public.logic` and `dem.public.demos` provide package catalogs; the latter
depends on the former. `dem.public.natural_deduction` also depends on the core:
it adopts eleven connective and existential schemas and adds twenty-two verified
theorems, including double negation, contraposition and excluded middle. Its
intuitionistic and classical systems keep the original two systems unchanged.
Package building and publication are separate operations.
The seed entry point is `python -m dem.db.seeds`.

## Development

Requires Python 3.13 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,webapi]"
.\.venv\Scripts\python.exe -m pytest -q --basetemp=build/pytest
```

To build a local workspace template:

```powershell
.\.venv\Scripts\python.exe scripts\build_workspace_template.py build\template.db
```

## Deployment and authentication

The API has no authentication. Requests share a development account; there is
no per-user authorization. CORS does not restrict non-browser clients.

The generic `docker-compose.yml` and `.env.example` default to
`DEM_READ_ONLY=true` for browsing. Keep this setting when exposing that
configuration. Starting uvicorn directly defaults to writes for local development.

The anonymous beta configuration is separate: use `deploy/beta/compose.yml`
and follow [the operations guide](docs/design/ops/anonymous-beta-operations.md).
Open anonymous writes only with that configuration's request limits, resource
budgets, workspace reset and published-package freeze in place. Setting
`DEM_READ_ONLY=false` on the generic configuration alone does not establish
those beta protections. The beta limits do not provide authentication or
isolate individual users.

## Validation policy

Formula and proof validation is the trust boundary. The reduced public data
and independent demonstrations use the same formula well-formedness,
proof-step checking, database guards and verified-proof requirements.

## License status

No open-source permission is granted at this stage. See `LICENSE.md` and
`THIRD_PARTY_NOTICES.md` for separately licensed dependencies.
