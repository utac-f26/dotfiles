# Permissions: make the agents tolerable, deliberately

This guide drives the permissions part of HW0. Your agent should read it;
you should understand every rule you commit. The standard for keeping a
rule: you can say out loud why skipping that approval is safe.

## What you are authoring

1. A `permissions` block in `claude/settings.json` (tracked, portable —
   you do not need Claude Code installed to author and commit it).
2. Your Codex policy in `codex/config.seed.toml` (tracked source of
   truth), mirrored into `~/.codex/config.toml` (app-owned, machine-local,
   never committed).
3. One probe run proving your Codex boundary actually fires, recorded in
   `SUBMISSION.md`.

`./self-check` prints a TODO line for anything missing or out of policy.

## Claude: the permissions block

Two layers, two jobs. Permission rules work at the tool layer: `allow`
and `ask` decide when Claude asks; `deny` and Read/Edit path rules block
tool calls outright. No rule constrains what a Bash subprocess does once
it is running — a denied `Bash(rm -rf*)` does not stop
`bash -c 'rm -rf …'`. Claude's separate sandbox feature (off by default)
is the OS-enforced boundary below the rules. Treat command-string deny
patterns as guardrails against accidents, not security.

Adapt — do not paste — this starting point:

```json
"permissions": {
  "allow": ["Read", "Glob", "Grep",
            "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)",
            "Bash(ls*)", "Bash(rg*)"],
  "deny":  ["Bash(sudo*)", "Bash(git push --force*)",
            "Read(~/.ssh/**)", "Read(**/secrets/**)"],
  "defaultMode": "acceptEdits"
}
```

HW0 accepts `defaultMode` of `default`, `acceptEdits`, or `plan`. Bare
`"Bash"` (or `"Bash(*)"`) in `allow` auto-approves every command and is
rejected: that is a decision to make later, with open eyes, not a default.

## Codex: two knobs and a tracked seed

`sandbox_mode` answers *what can it touch*; `approval_policy` answers
*when must it ask*. HW0 requires `sandbox_mode = "workspace-write"` and
`approval_policy` of `untrusted` or `on-request`. Widen the boundary
deliberately in `[sandbox_workspace_write]`:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
writable_roots = ["~/git"]   # one project root at a time — never your whole home
network_access = true        # default false; installs fail without it
```

Edit `codex/config.seed.toml` first, then copy the same values into
`~/.codex/config.toml` (Codex owns that file and adds its own state around
your keys — change only these keys). `self-check` compares the two and
reports drift. Keep the seed to exactly these keys for HW0.

Newer Codex builds have a beta "permission profiles" system that replaces
the sandbox keys. Do not mix the two: this course uses the sandbox keys,
and the pinned Codex version (`codex/pinned-version`) is what the
instructions are verified against.

## The probe

From `~/dotfiles`, ask Codex to create a file at a path outside every
writable root, for example:

    codex "create a file named codex-probe.txt in my home directory with
    the contents 'probe'"

Expected: the sandbox blocks the write or Codex asks for approval. **Deny
the request.** Then confirm nothing appeared:

    test ! -e ~/codex-probe.txt && echo "probe clean"

If you approved by mistake, delete the file and rerun. Record what
happened in the `SUBMISSION.md` permissions question.

## Platform notes

- macOS: enforcement is Seatbelt and invisible — the CLI, IDE extension,
  and desktop app all use it.
- Linux and WSL2: enforcement is bubblewrap; install it if the sandbox
  complains it is missing.
- Native Windows: the elevated sandbox creates dedicated low-privilege
  local users (this is expected, not malware); the unelevated fallback
  derives a restricted token from your account and is weaker. WSL2 is
  usually the calmer path.

## Review discipline

Review the agent's proposed rules line by line. Reject any rule you
cannot defend out loud. The disagreement you keep is the interesting
part — that is what the SUBMISSION question asks about.
