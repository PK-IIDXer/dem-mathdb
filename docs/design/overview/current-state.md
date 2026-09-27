# Public candidate current state

The public seed is the complete output of `dem.db.seeds.seed_all()`.

| Object | Count |
|---|---:|
| symbols | 17 |
| axioms | 8 |
| axiom systems | 2 |
| theorems | 0 |
| proofs | 0 |
| proof steps | 0 |

The 17 symbols are the nine public primitives plus the eight schema variables
owned by the Hilbert seed. No generated database snapshot is committed; tests
build an isolated A-only database from production code.
