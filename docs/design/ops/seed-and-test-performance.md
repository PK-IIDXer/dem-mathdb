# Public seed and test execution

The A-only seed is small enough to build in an isolated database for each test
scope. Public tests therefore do not reuse or distribute snapshots generated
from optional mathematical content.

Seed-related changes must run the focused seed and soundness tests twice, then
the complete suite. Correct accept/reject behavior and zero failures take
priority over elapsed time.
