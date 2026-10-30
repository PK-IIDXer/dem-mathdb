# Public candidate current state

The public seed is the complete output of `dem.db.seeds.seed_all()`.

| Object | Count |
|---|---:|
| symbols | 18 |
| definitions | 1 |
| axioms | 20 |
| axiom systems | 4 |
| theorems | 27 |
| proofs | 28 |
| formulas | 85 |
| proof steps | 164 |

The core's seventeen symbols are the nine public primitives plus eight schema
variables. The independent demonstrations add one defined symbol. The natural
deduction package adds eleven schemas, two systems, twenty-two theorems and
twenty-two proofs (144 steps), using the existing language. Its intuitionistic
system omits Peirce; double-negation elimination and excluded middle require
the classical system. These statements concern each proof's actual used axioms.
The original core and demonstration package identities are preserved.
No generated database snapshot is committed; tests build isolated databases
with real proof validation and reuse verified snapshots.
