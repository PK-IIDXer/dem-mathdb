import userEvent from '@testing-library/user-event'

/** userEvent.setup() for interaction tests.
 *
 * The default `delay: 0` awaits a zero-length timer after every simulated key
 * and pointer action.  That pause asserts nothing: each event is already
 * dispatched inside act(), so React has rendered and run its effects before
 * the next one.  Under a saturated CPU, though, every timer wake-up waits for
 * the scheduler, and typing a 22-character formula added about 0.8 s.
 * `delay: null` dispatches the same events in the same order without those
 * pauses; timers the application itself sets (debounces, highlights) are
 * untouched and still run in real time.
 */
export function setupUser() {
  return userEvent.setup({ delay: null })
}
