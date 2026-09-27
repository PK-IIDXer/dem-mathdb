# External verification backtest

The exporter under `scripts/backtest/` reads a freshly built A-only SQLite
database and emits the public vocabulary and eight axioms for independent type
checking. With no bundled theorem or proof corpus, theorem-closure and proof
mutation sets are empty by design.

Exporter tests verify that every public symbol and axiom is accounted for and
that malformed role metadata is rejected. A local Lean-backed run is optional
and requires a separately installed Lean toolchain.
