/** Timeout for tests that mount a whole editor or proof page in jsdom and
 * drive it with user-event, instead of Vitest's 5 s unit-test default.
 *
 * Their cost is jsdom style resolution (user-event's pointer-events check and
 * role queries' visibility check), KaTeX markup parsing and React's
 * development build.  Measured on 2026-10-13: 0.8-1.4 s each with an idle
 * CPU, and 2.2-4.1 s in a full `vitest run` with eight busy-loop threads
 * saturating the eight-core machine, before the first test of a file even
 * counts its one-time JIT warm-up.  That is under 1.25x headroom at 5 s, and
 * one loaded run doubled every duration.  The limit only has to catch a hang.
 */
export const PAGE_INTERACTION_TIMEOUT = 15_000

/** Timeout for the onboarding flow, which drives three real screens through
 * nine operations: 2.4 s with an idle CPU and 11.2-11.5 s in the loaded full
 * run described above (13.6-15.2 s before the 2026-10-13 fixes, against the
 * previous 15 s limit).
 */
export const ONBOARDING_FLOW_TIMEOUT = 30_000
