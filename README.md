# dem-mathdb

DEM is a database-backed kernel for storing formulas, axiom systems,
theorems, and machine-checked proof steps. This release candidate contains
only the independently reviewed A-only public seed.

## Public seed

- primitive symbols: `⊥ ¬ ∨ ∧ → ↔ ∀ ∃ =`
- inference rules: `MP`, `Gen`, `ImpIntro`
- eight Hilbert schemas: K, S, universal elimination and distribution,
  equality reflexivity and substitution, vacuous universal introduction,
  and Peirce
- axiom systems: `hilbert_core`, `hilbert_classical`
- bundled derived theorems and proofs: none

The public seed entry point is `python -m dem.db.seeds`. It does not import
optional mathematical content packages or generated corpora.

## Development

Requires Python 3.13 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,webapi]"
.\.venv\Scripts\python.exe -m pytest -q
```

To build a local A-only workspace template:

```powershell
.\.venv\Scripts\python.exe scripts\build_workspace_template.py build\template.db
```

## Validation policy

Formula and proof validation is the trust boundary. Seed reduction changes
bundled mathematical data only; it does not weaken formula well-formedness,
proof-step checking, database guards, or verified-proof requirements.

## Security

The API does not provide authentication. `resolve_request_account()` in
`webapi/deps.py` treats every request as the same development account, so it
does not distinguish users or enforce per-user authorization.

`DEM_READ_ONLY` is the only switch that blocks writes. The bundled
`docker-compose.yml` and `.env.example` enable read-only mode by default;
setting it to `false` enables create, update, and delete operations. Because
`docker-compose.yml` publishes ports 80 and 443, do not expose a write-enabled
deployment to the Internet without an authentication layer in front of it.

The CORS allowlist in `webapi/main.py` is not an authorization mechanism;
non-browser clients are not constrained by CORS. When the API is started
directly with `uvicorn`, the application code defaults to write-enabled mode
for local development.

## License status

No open-source permission is granted at this stage. See `LICENSE.md`.
