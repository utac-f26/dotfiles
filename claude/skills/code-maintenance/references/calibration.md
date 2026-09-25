# Calibration: Real Fixes Versus Churn

Each rule below marks a change that looked like an improvement in an automated
cleanup pass over a real repository and was not. Most are phrased as a test to
apply to a candidate change; when the test fails, leave the code alone.

## Naming and extraction

- Rename only when a reader cannot tell what the variable holds without reading
  surrounding code. Short names (`p`, `i`, `n`, `t`) in loops, comprehensions,
  lambdas, and functions under about ten lines are idiomatic; renaming them is
  churn. The test is "would a reader be confused?", not "is the name short?"
- Extract a helper only when the *caller* becomes easier to read. A 40-line
  function with linear flow is fine. A block called from exactly one place with
  no independently meaningful name should stay inline; moving it adds a level
  of indirection and nothing else.
- Hoist a literal into a named constant when the value appears in more than one
  place, is configuration, or is cryptic at its usage site. `1440` in
  a function that already says "minutes" does not need `MINUTES_PER_DAY`.
- A commit that touches nine files to rename fifteen variables is busywork. One
  duplicate-removal or structural fix is worth more than a dozen renames.

## Types

- Never add `Any` as a placeholder. Untyped and `Any` are equally unchecked,
  but `Any` falsely records that typing was considered and silences warnings
  that would otherwise catch a real bug later. If the true type is a
  third-party class without stubs, import it (behind `TYPE_CHECKING` if
  needed) or leave the parameter bare.
- Never remove an existing `Any` without a real replacement. Bare is a
  downgrade: it loses the record that the author chose `Any` deliberately.
- `dict` to `dict[str, Any]` and `list` to `list[Any]` change nothing a checker
  catches. Spend annotations where a wrong type crosses a function boundary,
  where a missing `None` check hides, or where container contents are
  ambiguous.

## Exceptions and cleanup

- Decide whether a broad `except` is lazy or defensive before narrowing it. A
  broad catch around a third-party parser processing external input (`.bib`
  files, XML, uploads) is defensive: it skips one bad item instead of crashing
  the batch, and narrowing it means the next unexpected exception type aborts
  the run. A broad catch around your own typed code is lazy and hides bugs.
- Drop an exception type from a handler only after proving the path cannot
  raise it. `d.get(k)` cannot raise `KeyError`; `d[k]` can.
- Add explicit `close`/`finally` only for resources that leak in practice:
  browser processes, database connections and pools, subprocess handles,
  descriptors held across a loop. A `requests.Session` in a CLI that exits in
  seconds does not need `try/finally`. The test is "does this leak if an
  exception occurs and the program keeps running?"

## Durability

- Triage before adding atomic writes: "if a crash corrupts this file, how bad
  is it?" Progress metadata, generated results, and conversion state earn the
  full pattern. `.gitignore`, logs, caches, lock files, and anything
  regenerated on the next run get a plain write.
- The full pattern is: `mkstemp` in the *same directory* (rename across
  filesystems is not atomic), `fsync` the file, `os.replace`, `fsync` the
  parent directory, remove the temp file on the error path, and check the
  return values of `write` and `fsync`.
- A lock against lost updates spans the whole read-modify-write, not just the
  write. Use `flock`/`fcntl` across processes; a version counter that rejects
  stale writes is the compare-and-swap alternative.
- The idempotency test is run-twice-assert-once.

## Concurrency

- After turning a sequential loop into workers, trace the worker's return
  shape through to the caller's destructuring, and check any counter or
  progress report that assumed in-order completion. Inline loop variables
  become return values, and a 3-tuple destructured as 2 is a runtime crash the
  existing tests rarely reach.
- Do not parallelize a path whose tests exercise only the sequential case. Add
  a two- or three-item parallel test first.
- No "just in case" locks on single-threaded paths.

## Security

- Establish the threat model before adding a guard. CLI arguments, network
  data, and uploads are untrusted. A config file or manifest the user authored
  is trusted: whoever can edit it already has code execution, so a
  path-traversal check on it adds complexity and no security. Reflexive
  defense-in-depth is maintenance cost; ask what the realistic attack vector
  is.

## Tests

- Before writing a test, name the bug it would catch. No clear answer means
  the test is not worth writing.
- Weak-test signatures: it asserts that a mock returns what it was told; it
  would pass with the code under test broken; it depends on execution order or
  shared mutable state; it mocks away the logic it claims to exercise. Fix or
  replace these before adding coverage, because they are false confidence.
- Cover important behaviors and error paths, not line-coverage targets.

## Dependencies

- Grep for the import name, not the distribution name: `Pillow` imports as
  `PIL`, `python-dateutil` as `dateutil`, `beautifulsoup4` as `bs4`, `PyYAML`
  as `yaml`.
- Zero imports does not mean unused. pytest plugins, entry points, database
  drivers, and linters or formatters in a dev group load without an import.
- Remove; do not upgrade or downgrade in the same pass, and let the package
  manager regenerate lock files.

## Reading the final diff

Report only what warrants a code change or a follow-up. Skip harmless but
unnecessary defensive code, portability concerns in a single-platform project,
"could theoretically" issues, and notes that amount to "I verified this is
correct." A clean diff with nothing to report is the expected outcome; do not
manufacture findings to fill a list.
