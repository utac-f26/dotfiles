---
name: codex-review
description: |
  Use when the user asks for a Codex review, independent second opinion, or
  multi-round critique of a specification, plan, code change, or measured
  results. Not for reviewing someone else's pull request or for routine tests.
---

# Codex Review

Use `codex-review` to drive one named, read-only Codex session. The command
owns session state, prompts, response validation, one format-repair attempt,
code diff snapshots, and the three-round cap. Do not reproduce that machinery
manually, and do not ask Claude to review its own work as a substitute.

## Start or resume

Infer the phase from the request. For an ambiguous request, use `code` when
`git status --short` is non-empty; otherwise ask which artifact to review.

```bash
codex-review start --phase PHASE --artifact PATH [--session NAME] [--base REF]
codex-review status
```

`start` immediately runs round one and prints the response path. Read that
file. Use `status` before starting another review if an active review may
already exist. If a transient CLI, login, or network failure leaves the current
round without a response, fix the reported cause and run `codex-review retry`.
If a saved Codex conversation no longer exists, the bridge quarantines its
stale registry entry; `retry` then starts a fresh conversation with the prior
disposition memo in its prompt. If changed CLI wording defeats detection, move
`~/.codex/sessions-by-name/NAME.json` aside manually and retry. Codex reviews
time out after 600 seconds by default; set `CODEX_ASK_TIMEOUT` higher before
retrying a legitimate long review.

For `code` on a feature branch, the driver finds and records the feature merge
base. On dirty `main` or `master`, it uses `HEAD` to review only uncommitted
work; `--base HEAD` is the explicit equivalent. For an already committed change
on a clean default branch, pass the commit immediately before the change. The
driver fails instead of sending an empty or unprovenanced snapshot.

## Respond to findings

Address sound findings in the work, investigate uncertain ones, and write a
disposition memo with every heading below. Reference every finding exactly
once and no unknown finding.

```markdown
## Addressing
- #1 -> what changed
## Pushing back
- #2 -> concrete technical reason
## Investigating
## Acknowledged
- #3
```

When another round is needed, run:

```bash
codex-review continue --memo PATH
```

Only NIT findings may be Acknowledged. A QUALITY BLOCKER cannot be Pushing
back. A `BLOCKER + PREMISE` requires the user's decision; if the user rejects
the premise, put it under Pushing back and record the decision explicitly:

```bash
codex-review continue --memo PATH --override-premise "USER REASON"
```

Never invent an override or edit reviewer response files. Each memo bullet
starts with its finding number; numbers later in explanatory text, such as
`PR #7`, are not dispositions.

## When to stop

BLOCKER means a concrete defect, missing requirement, or contradiction.
IMPROVE means a substantial improvement to address or push back on with a
reason. NIT means a small or stylistic finding to acknowledge.

Only BLOCKERs gate the loop. End it when a round raises no BLOCKER, after
disposing of every finding. Addressing IMPROVEs and NITs needs no further
round. After changing anything for a BLOCKER, run another round so Codex
verifies the fix. Three rounds is a cap, not a quota. At the cap, bring
unresolved BLOCKERs and fixes still awaiting reviewer verification to the
user; do not start a fourth round or silently finish or advance.

## Advance and finish

Continue the same session across lifecycle phases when the request covers
them:

```bash
codex-review advance --phase NEXT_PHASE --artifact PATH [--memo FINAL_MEMO]
codex-review finish [--memo FINAL_MEMO]
```

The phases are `spec -> plan -> code -> results`; advances must be adjacent.
If the last round reports findings, disposition them in `FINAL_MEMO` before
advancing or finishing. The driver requires every QUALITY BLOCKER to be
under Addressing. That disposition records what changed; it is not proof
the fix worked. Follow the verification and cap rules above before closing.
A human-overridden PREMISE BLOCKER belongs under Pushing back and also
requires `--override-premise "USER REASON"`. A final `No findings.` needs
no memo.

Code review records branch, HEAD, and base provenance and includes bounded
committed, staged, unstaged, and untracked work. Review state lives outside the
repository at
`$XDG_STATE_HOME/utac-agent-review/codex/` when that variable is set, otherwise
at `~/.local/state/utac-agent-review/codex/`.
