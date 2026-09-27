# DEM public-core note

This candidate demonstrates DEM's content-independent theorem database and
validation kernel with a deliberately small logical seed.

Formulas are stored as typed prefix token sequences. Symbol arity, formula
type, binder depth, substitution, and proof-step conclusions are validated at
service and database boundaries. A proof becomes verified only after the raw
kernel replays every step. A theorem becomes proven only through a verified
proof of that theorem.

The seed contains nine primitive symbols, three inference rules, eight
standard Hilbert schemas, and two axiom systems. It contains no derived
theorem or proof corpus. `ImpIntro` remains an admissible authoring rule: the
public Hilbert toolkit expands it to K/S, MP, and Gen steps, and the expanded
proof is validated by the same kernel.

Optional mathematical foundations and example corpora are intentionally
outside this first public candidate. They can be added later only after a
separate provenance and licensing review.
