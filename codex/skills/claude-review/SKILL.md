---
name: claude-review
description: |
  Use when the user asks for a Claude review, independent second opinion, or
  multi-round critique of a specification, plan, code change, or measured
  results. Not for reviewing someone else's pull request or for routine tests.
---

# Claude Review

Use `claude-review` to drive one named, read-only Claude Code session. The
command owns session state, prompts, response validation, one format-repair
attempt, code diff snapshots, and the three-round cap. Do not reproduce that
machinery manually, and do not ask Codex to review its own work as a substitute.

## Start or resume

Infer the phase from the request. For an ambiguous request, use `code` when
`git status --short` is non-empty; otherwise ask which artifact to review.

```bash
claude-review start --phase PHASE --artifact PATH [--session NAME] [--base REF]
claude-review status
```

`start` immediately runs round one and prints the response path. Read that
file. If the command reports that Claude is unavailable, tell the user that
Claude Code needs its own account login; do not silently fall back to Codex.
After fixing a transient CLI, login, or network failure, run
`claude-review retry` to retry the same round.
If a saved Claude conversation no longer exists, the bridge quarantines its
stale registry entry; `retry` then starts a fresh conversation with the prior
disposition memo in its prompt. Claude reviews time out after 600 seconds by
default; set `CLAUDE_ASK_TIMEOUT` higher before retrying a legitimate long
review. If changed CLI wording defeats detection, move
`~/.claude/ask-sessions-by-name/NAME.json` aside manually and retry.

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

Then run:

```bash
claude-review continue --memo PATH
```

Only NIT findings may be Acknowledged. A QUALITY BLOCKER cannot be Pushing
back. A `BLOCKER + PREMISE` requires the user's decision; if the user rejects
the premise, put it under Pushing back and record the decision explicitly:

```bash
claude-review continue --memo PATH --override-premise "USER REASON"
```

Never invent an override or edit reviewer response files. Normally run two
rounds. Use the third only when round two reports a new or unresolved issue.
Each memo bullet starts with its finding number; numbers later in explanatory
text, such as `PR #7`, are not dispositions.

## Advance and finish

Continue the same session across lifecycle phases when the request covers
them:

```bash
claude-review advance --phase NEXT_PHASE --artifact PATH [--memo FINAL_MEMO]
claude-review finish [--memo FINAL_MEMO]
```

The phases are `spec -> plan -> code -> results`; advances must be adjacent.
If the last round reports findings, disposition them in `FINAL_MEMO` before
advancing or finishing. Every QUALITY BLOCKER must be under Addressing. A
human-overridden PREMISE BLOCKER belongs under Pushing back and also requires
`--override-premise "USER REASON"`; this is the audited exit at the three-round
cap. A final `No findings.` needs no memo.

Code review records branch, HEAD, and base provenance and includes bounded
committed, staged, unstaged, and untracked work. Claude receives only Read,
Grep, and Glob; the driver writes review state outside the repository at
`$XDG_STATE_HOME/utac-agent-review/claude/` when that variable is set,
otherwise at `~/.local/state/utac-agent-review/claude/`.
