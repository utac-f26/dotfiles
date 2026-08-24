# Dotfiles warmup

Project 0 is completion-only. Your job is to leave yourself with a working,
maintainable `~/dotfiles`: install the course toolchain, publish shared guidance
to Claude and Codex, seed their safely portable settings, push evidence that
the setup works, and put the agent to work once on your own configuration. The
point is using and judging the environment, not building a serious software
system.

The first class meeting walks through steps 1–7 as the in-class lab. Steps 8–10
are your work outside of class: a passing receipt alone does not complete the
assignment.

Generate the receipt on any supported machine where you work: a macOS, Linux,
or WSL laptop, or your CS department Linux home. Department hosts are an
encouraged second environment for long or Linux-specific work, not a completion
requirement.

## What to do

1. Clone your private `utac-f26/dotfiles-<login>` repository to `~/dotfiles`.
2. Run `./setup`. It configures plain `git pull` to receive published course
   improvements while plain `git push` continues to update your personal repo.
3. Run `gh auth status --hostname github.com`; use `gh auth login` if needed.
4. Follow `guides/codex-login.md` and make sure `codex login status` reports a
   logged-in UT Austin ChatGPT account.
5. Follow `guides/claude-login.md` and make sure `claude auth status` reports
   a signed-in UT Claude account.
6. Run `./self-check` on the laptop or department home you want to certify.
7. Commit and push `.setup-receipt.json`.
8. Put the agent to work: run `codex` in `~/dotfiles` and ask it to add a
   "My preferences" section to `AGENTS.md` recording one real preference and
   one gotcha you hit during setup. Review the diff line by line, reject
   anything you would not defend, then commit and push it.
9. Make the permissions situation tolerable. With your agent, author a
   `permissions` block in `claude/settings.json` — an allow list you can
   defend, deny guardrails, and a `defaultMode` of `default`,
   `acceptEdits`, or `plan`. Then set your Codex policy in
   `codex/config.seed.toml`, mirror the same keys into
   `~/.codex/config.toml`, and run the probe in `guides/permissions.md`:
   ask Codex to write one file outside your writable roots, deny the
   prompt, and confirm no file appeared. Review every rule line by line
   and reject anything you would not defend, then commit and push.
10. Complete `SUBMISSION.md` — including whether the agent came up with
    anything surprising, where you had to steer or correct it, and which
    permission rule you debated and what the probe showed — and commit
    and push it. Rerun `./self-check`: it prints a TODO line for anything
    still missing and exits clean only when HW0 is complete.
11. If you want department compute from a laptop, follow
    `guides/remote-hosts.md` and exercise `remote-run` against one exact host.

During the semester, run `git pull` when an update is announced. The
announcement will say whether you also need `./links`, `./setup --update`, or a
manual Codex seed merge. Your commits remain ordinary student history; course
updates do not overwrite them.

The self-check requires Codex and Claude Code because UT provides both —
ChatGPT Edu and university-managed Claude access — to every student. It does
not require Gemini.

## Grading

There is nothing to upload in Canvas. We grade `main` in your seeded repository.
It must contain your completed `SUBMISSION.md`, a current, valid
`.setup-receipt.json`, your reviewed agent-written addition to `AGENTS.md`,
your authored `permissions` block in `claude/settings.json`, and your Codex
policy in `codex/config.seed.toml`. The receipt records passing functional
checks plus the normalized path and compatible version output for every
required command, including `remote-run` and `with-secrets` as commands
available on `PATH`. It is written only after the full homework check passes and
binds SHA-256 digests of the four required committed artifacts, so later drift
is rejected by the offline grader.

Do not commit tokens, API keys, age private keys, plaintext `.env` files, or
Claude/Codex runtime state. The self-check rejects those leak shapes before it
writes a passing receipt.
