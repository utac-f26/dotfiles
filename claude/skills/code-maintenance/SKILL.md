---
name: code-maintenance
description: |
  Use when asked for a maintenance pass, cleanup, or simplification of
  existing code, or for dead-code or redundancy removal, consolidation of
  duplicated mechanisms or API sprawl, stronger typing or clearer ownership,
  or a defect and logic-error hunt. Preserves behavior, compatibility,
  security, concurrency, durability, and trust boundaries. Not for
  feature-first work, formatting-only changes, or a review that forbids edits.
---

# Code Maintenance

Make the implementation smaller, clearer, better typed, and easier to reason
about. Implement the improvements unless the user requested a read-only audit.

Treat net-negative production code as the default direction, not a line-count
quota. Add code when it buys a necessary test, typed boundary, or real defect
repair. Do not trade clarity or a required guarantee for fewer lines.

## Establish The Contract

1. Read the applicable repository instructions and architecture documents.
2. Inspect repository status and preserve unrelated changes.
3. Identify public APIs, data formats, compatibility promises, trust boundaries,
   and concurrency or durability requirements.
4. Locate the focused and full validation commands.
5. Run a focused baseline when practical and distinguish pre-existing failures.

Do not infer that two paths are redundant merely because their code looks
similar. Establish whether they provide different security, lifecycle,
transactional, compatibility, or performance guarantees.

## Inventory Before Editing

Trace definitions through callers and tests. Look for:

- Duplicate or mostly duplicate functions, classes, handlers, endpoints,
  decoders, validators, factories, fixtures, and error paths.
- Separate serial, parallel, legacy, and production implementations of the same
  operation.
- Multiple cache, persistence, IPC, orchestration, or emission paths.
- Thin wrappers, aliases, compatibility entry points, and pass-through helpers.
- Repeated low-level sequences that represent one domain operation.
- Dead code, unused configuration, unreachable branches, stale terminology,
  and comments that no longer match behavior.
- APIs with excessive visibility, weak types, ambiguous ownership, hidden side
  effects, or unclear thread/process safety.
- Tests that repeat large internally constrained objects or assert incidental
  implementation details instead of portable contracts.

Choose the implementation with the strongest contract and clearest ownership
as the canonical mechanism. Migrate all in-scope callers and delete the old
mechanism in the same change. Do not leave forwarding wrappers or deprecated
aliases without evidence of an external consumer.

Prefer one configurable path over separate mechanisms when their semantics are
the same. Preserve separate paths when their guarantees materially differ.

## Improve Types And API Scope

- Use precise parameters, return types, immutable value objects, dataclasses,
  enums, literals, and protocols where they express real domain constraints.
- Make lifecycle and process ownership explicit. Use factories when instances
  must not be shared across workers or requests.
- Narrow interfaces and exports. Keep helpers private unless callers need a
  supported API.
- Make illegal and incomplete states difficult to represent.
- Replace ambiguous sentinels and optional values with explicit states when the
  distinction affects behavior.
- Reduce `Any`, broad dictionaries, unchecked casts, and type suppressions.
- Accept `object` at an untrusted serialization boundary, validate exact shapes
  and primitive types once, and return a typed domain object.
- Reject implicit coercions such as booleans accepted as integers unless the
  protocol explicitly permits them.

Do not invent an abstraction to remove a couple of similar lines. Introduce a
shared primitive when it names a domain operation, centralizes a contract, or
replaces meaningful repetition.

## Hunt For Defects

Inspect normal, empty, boundary, partial-failure, and cleanup paths. Check for:

- Off-by-one mistakes, invalid empty collections, and zero-sample states.
- Confusion between missing evidence and an observed zero or failure.
- Exceptions caught too broadly, too narrowly, or classified incorrectly.
- Partial writes, non-atomic replacement, stale cache reuse, and inconsistent
  provenance.
- Resource, process, thread, descriptor, socket, and temporary-file leaks.
- Cleanup and rollback that fail after partial initialization.
- Races, unsafe shared state, unstable ordering, and nondeterministic reduction.
- Timeout paths that fail to terminate descendants or bound diagnostics.
- Validation performed only after trusted state has changed.
- One-item failures that abort a batch, and infrastructure failures silently
  converted into ordinary user failures.
- Platform-specific return codes, timing assumptions, or filesystem behavior
  encoded as universal contracts.

Add the smallest regression test that states the intended contract for each
real defect. Do not weaken an assertion merely to make a test pass; decide
whether it describes a portable guarantee or an incidental implementation.

## Preserve Security And Trust

Keep authentication, authorization, validation, isolation, sandboxing,
resource limits, auditability, and fail-closed behavior at least as strong as
before. Do not remove apparently repeated checks until tracing which side of a
boundary each check protects.

For systems that run untrusted code, preserve these invariants when applicable:

- Untrusted and trusted code do not share an address space.
- Untrusted code cannot write trusted artifacts, caches, reports, provenance,
  or control state.
- Untrusted output is bounded data, never trusted control or direct emission.
- IPC is explicit, versioned, bounded, and strictly decoded.
- The trusted parent validates observations, constructs domain objects,
  persists, and emits results.
- Worker termination, descendant cleanup, and resource accounting are verified
  before accepting work.
- Infrastructure faults remain distinguishable from untrusted-code failures.

Preserve intentionally supported schema and protocol versions. Consolidate
their shared primitives without erasing version-specific validation.

## Keep The Change Disciplined

- Make cohesive changes; avoid unrelated renaming, formatting, or file moves.
- Reuse an existing structured primitive before adding another helper.
- Delete obsolete code instead of commenting it out.
- Update callers, tests, documentation, and type declarations atomically.
- Do not change thresholds, policy, protocol semantics, or compatibility
  promises under the label of maintenance.
- Ask for direction when proceeding requires a material contract or policy
  decision that cannot be discovered from the repository.

Use subagents only for independent inventories when the split pays. Review,
verification, and the combined diff stay in the main loop.

## Verify The Result

Run validation proportional to risk:

1. Focused regression tests after each cohesive change.
2. Formatter or lint checks and static type checking.
3. The complete relevant test suite.
4. Platform-specific tests for namespaces, cgroups, processes, signals,
   filesystems, sockets, concurrency, or other OS-dependent behavior.
5. Architecture, dependency-boundary, and compatibility tests when present.

Then run the repository's full verification gate (for example, a `check`
script) when one exists, and finish with one pass over the change itself:

- Search for removed API names, stale imports, duplicate endpoints, and
  superseded mechanisms; confirm one production entry point remains for each
  consolidated operation.
- Read the complete diff for weakened checks, accidental behavior changes, and
  unrelated modifications, and take the line counts the report needs.

That pass is the skill's verification step. Do not add further self-review
rounds on top of it.

## Report

Lead with the outcome. Include:

- The canonical mechanisms that remain and the alternatives removed.
- Typing and API-boundary improvements.
- Real bugs found and their regression tests.
- Security or compatibility distinctions deliberately preserved.
- Exact validation commands and results.
- Production and total additions, deletions, and net change.
- Unresolved risks or focused follow-up work.

Explain substantial net growth by major category. Continue simplifying when
growth has no concrete justification. Follow repository policy for committing
and pushing; do not broaden external side effects merely because maintenance
work is authorized.
