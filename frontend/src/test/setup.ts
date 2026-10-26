// Vitest setup shared by every test file (see `test.setupFiles` in vite.config.ts).

if (typeof document !== 'undefined') {
  const { configure, getConfig } = await import('@testing-library/dom')
  const defaultGetElementError = getConfig().getElementError

  // waitFor and every findBy* query retry a failing getBy* query on each DOM
  // mutation and every 50 ms, and each failure builds an error whose message
  // pretty-prints the whole document.  That error is discarded on the next
  // retry, and on timeout waitFor passes the last message through
  // getElementError again outside the retry loop, so the reported failure
  // still carries the full DOM.  Skip only the pretty-printing of the
  // discarded intermediate errors: on large pages it cost more than half a
  // second per test.  Assertions are unchanged, and a timed-out findBy*
  // message now carries the DOM once instead of twice (setup.test.tsx pins
  // this); if the private flag ever disappears this falls back to the default.
  configure({
    getElementError(message, container) {
      const polling = (getConfig() as { _disableExpensiveErrorDiagnostics?: boolean })
        ._disableExpensiveErrorDiagnostics
      if (!polling) return defaultGetElementError(message, container)
      const error = new Error(message ?? '')
      error.name = 'TestingLibraryElementError'
      return error
    },
  })

  // jsdom initialises its style engine on the first getComputedStyle call,
  // which user-event (pointer-events check) and role queries (visibility)
  // make in nearly every interaction test.  Pay that one-time cost here,
  // once per test file, instead of inside whichever test happens to run
  // first: it was 0.35-0.4 s of that test's time budget.
  void getComputedStyle(document.body).pointerEvents
}

export {}
