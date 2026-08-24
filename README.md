# UTAC dotfiles

This repository is your portable setup for Agentic Coding: command-line tools,
Claude/Codex config links, SOPS secrets hygiene, and local-to-department-host
workflows.

Clone your personal repo to exactly this path:

```bash
git clone https://github.com/utac-f26/dotfiles-<login>.git ~/dotfiles
cd ~/dotfiles
```

Before cloning with HTTPS, create a fine-grained GitHub Personal Access Token:

- Repository access: only `utac-f26/dotfiles-<login>`.
- Permission: **Contents: Read and write**.
- Do not paste the token into the clone URL.
- If GitHub asks for SSO authorization for the `utac-f26` org, approve it.

SSH is also fine if you already know how to create and register an SSH key.

## Setup

Run:

```bash
./setup
```

Then open a new terminal so the new PATH block is active. Authenticate GitHub
with `gh auth login` before running the completion check.

The installer is no-root by construction. It installs tools under `~/.local`,
adds `~/.local/bin` and `~/bin` to your shell PATH once, creates an age key if
one does not exist, writes `.sops.yaml` for your public age recipient, links the
owned Claude settings and shared agent guidance, and seeds Codex's live config
on a new machine. It also configures the course template as the source for
`git pull` while keeping your personal repository as the destination for
`git push`. Directly downloaded tools use explicit release versions and
repository-owned SHA-256 checksums; Claude Code and Codex are pinned as well.
`uv` provides Python 3.11 for the Python entry points. Existing compatible
tools are left alone unless you run `./setup --update`. The toolchain needs
roughly 1 GB free in your home directory; `setup` checks before downloading
anything.

It does not symlink the whole `~/.claude` or `~/.codex` directory. It also does
not symlink Codex's live `config.toml`, which Codex rewrites with machine and
project state. Those directories and files contain auth state, transcripts,
caches, trust grants, and runtime history that do not belong in git.

Run `./setup` in each independent home where you work. The department Linux
pool shares one home across its hosts, so one department-side setup covers that
pool; a laptop has a different home and needs its own setup and logins. You may
generate the homework receipt on either one. Department hosts are encouraged
for long or Linux-specific work, but they are not required for completion.

## Course updates

This repository is meant to improve during the semester. After the initial
setup, the normal update is deliberately ordinary:

```bash
git pull
```

That pulls the next published commit from `utac-f26/dotfiles` and merges it
with your work. Your normal `git push` still goes to
`dotfiles-<login>`. `KIT_REV` identifies the last course-verified cut; the Git
history identifies later living-repository commits, which are grading-neutral.
Release notes will say when an update also needs `./links` (new managed paths),
`./setup --update` (new tool versions), or a manual merge into Codex's app-owned
`~/.codex/config.toml`. Course updates never force-overwrite your commits;
resolve an ordinary Git conflict if you and the course edited the same line.

## Configuration ownership

The files have deliberately narrow roles:

- `AGENTS.md` is the shared, client-neutral guidance linked into both
  `~/.claude` and `~/.codex`.
- `claude/CLAUDE.md` imports that adjacent guidance and is the place for future
  Claude-only instructions. `claude/settings.json` is portable and linked.
- `codex/config.seed.toml` contains stable defaults. `./links` copies it only
  when `~/.codex/config.toml` is absent; after that, Codex owns the live file.
- `.tmux.conf` is the portable tmux policy linked as `~/.tmux.conf`.
- `required-tools.txt`, `asset-checksums.txt`, `KIT_REV`, and `upstream-url`
  are course-owned manifests used by setup and the completion check.
- `.editorconfig` gives editors one formatting policy for the mixed shell,
  Python, Markdown, and Makefile tree.

Edit each setting at its owner instead of repeating it in multiple client
files. Runtime auth, transcripts, caches, and one-machine overrides stay
outside this repository.

## Cheap `/clear` restarts in Claude Code

`claude/settings.json` wires `bin/claude-breadcrumbs.py` into Claude Code's
SessionEnd and SessionStart hooks. When you run `/clear`, the ending session's
transcript is digested mechanically — no model pass — into a markdown trail
under `claude/breadcrumbs/`, and the fresh session starts with a one-line
pointer to it. Continuing costs the model a single file read; a `/clear` meant
as a genuine fresh start just ignores the pointer. This makes `/clear` the
default way to reset context instead of waiting on compaction. The hook fails
open: if anything goes wrong it prints nothing and your session starts
normally. The hook wiring itself is one screen of `settings.json` — read it to
see what a hook is.

The digest keeps only each turn's closing message. A clear at a task boundary
therefore needs nothing more: the closing status report the model just printed
is already the restart summary, kept verbatim. The habit is for the other
endings — run `/handoff` before you clear mid-task or quit for the day. It
writes a standardized summary — goal, decisions, verification commands, next
action — and prints it, so the printout becomes the final closing message, the
digest keeps it verbatim, and a same-terminal `/clear` picks it up
automatically. The copy saved under `claude/handoffs/` covers what breadcrumbs
cannot: quitting instead of clearing, or resuming days later.

## Resetting context in the Codex app

Codex in the ChatGPT desktop app has no in-thread erase-context command. The
reset is a new task: press ⌘N or click New chat in the sidebar, which starts a
task without the current conversation's transcript. Where you start it chooses
the context — inside the same project keeps repository access and AGENTS.md;
from Home, outside the project, drops project-level context too. ⌘⌥N opens
Quick Chat, not a new Codex task. Because nothing else carries over, the same
handoff discipline applies: put status, next actions, and gotchas into the repo
before starting the new task.

## Agent sign-in

The course uses two coding agents, and both accounts are university-provided.
Codex's CLI command is `codex`; sign in with your UT ChatGPT account as
described in `guides/codex-login.md`. Claude Code's CLI command is `claude`;
sign in with your UT Claude account as described in
`guides/claude-login.md`. Then check both:

```bash
codex login status
claude auth status
```

Gemini is optional and uses `secrets/gemini.env` if you choose to set it up.

## Cross-model review

The repository installs symmetric review workflows. From Claude Code, ask for
a Codex review or run `codex-review`; from Codex, ask for a Claude review or
run `claude-review`. Both commands use the same bounded protocol:

```bash
codex-review start --phase code --artifact path/to/changed-file
claude-review start --phase code --artifact path/to/changed-file
```

Those forms infer the merge base on a feature branch and use `HEAD` for dirty,
uncommitted work on `main`. If the reviewed change is already committed on
`main`, name its parent explicitly, for example `claude-review start --phase
code --base HEAD~1 --artifact path/to/file`. You can also spell out `--base
HEAD` for uncommitted work. The generated snapshot records its branch, HEAD,
and base and fails closed if there are no changes to review.

The reviewer is read-only, findings use one checked format, and the originating
agent records each disposition before a second round. Named conversations and
review state survive context resets. Run `codex-review status` or
`claude-review status` to recover the active review. State is stored outside
the repository under `~/.local/state/utac-agent-review/` by default.
If a CLI, login, or network call fails mid-round, fix the reported cause and
run the matching `codex-review retry` or `claude-review retry` command.
Stale named-session entries are moved aside automatically so a retry can start
a fresh reviewer conversation without losing the disposition memo. If a CLI's
error wording evades automatic detection, move the session's JSON file aside
manually under `~/.claude/ask-sessions-by-name/` or
`~/.codex/sessions-by-name/`, then retry. Both bridges time out after 600
seconds by default; change that with `CLAUDE_ASK_TIMEOUT` or
`CODEX_ASK_TIMEOUT`.

Every round with findings needs a four-section disposition memo. Pass the
final memo to `finish --memo PATH` (or to `advance --memo PATH` when continuing
the lifecycle); a `No findings.` response needs none. A QUALITY BLOCKER must
be under Addressing. A human-overridden PREMISE BLOCKER belongs under Pushing
back, and the driver records the override reason beside the memo.

Codex review and Claude review both work with the required UT logins. If a
login or executable is missing, the command says which one instead of falling
back to a self-review.

## Department Linux hosts

The installed `remote-run` command sends a long job to one exact department
host, keeps it in tmux, and provides check, log, attach, list, kill, and cleanup
operations. It requires working SSH access, remote `bash` and `tmux`, and a
current project checkout; it is not a provisioning or file-transfer tool.

Follow [`guides/remote-hosts.md`](guides/remote-hosts.md) to configure SSH,
prepare the shared department home, choose a concrete host, synchronize through
GitHub, and exercise the full workflow if you want to use department compute.
This workflow is recommended, not part of the receipt gate. Do not use the
`linux.cs.utexas.edu` pool alias for a tmux job.

## Put the agent to work

The receipt proves the tools run; this step proves you can direct an agent and
judge its output. In this repository, run `codex` (Claude Code also works) and
ask it to add a "My preferences" section to `AGENTS.md` recording one real
preference and one gotcha you hit during setup. Review the diff line by line
and reject anything you would not defend, then commit and push it:

```bash
git diff
git add AGENTS.md
git commit -m 'record first preferences with the agent'
git push
```

Then answer the two agent-reflection questions in `SUBMISSION.md`: did the
agent come up with anything surprising, and where did you have to steer or
correct it?

Next, work through `guides/permissions.md` with the agent. Add a Claude
`permissions` block with at least one defensible `allow`, one `deny`, and an
explicit `defaultMode`; set the matching Codex policy in
`codex/config.seed.toml` and the app-owned `~/.codex/config.toml`; then perform
the documented denied-write probe. This is policy you must understand, not a
permission list for an agent to accept on your behalf. Record the debated rule
and probe result in `SUBMISSION.md`.

## Completion

Run:

```bash
./self-check
git add .setup-receipt.json .sops.yaml AGENTS.md SUBMISSION.md \
    claude/settings.json codex/config.seed.toml
git commit -m 'complete dotfiles setup'
git push
```

If `self-check` fails, read the failing check and fix that item. The receipt is
written only when the required checks pass. It records the normalized path and
non-empty version output for every required command, so `remote-run` and
`with-secrets` must be invokable by name rather than merely present in this
checkout. It also records successful GitHub and Codex authentication. Nothing
is uploaded on Canvas; your repository's `main` branch is the submission, and
it must also contain your reviewed agent commit to `AGENTS.md`. The receipt
also records the `KIT_REV`, the managed-link contract, and the pull/push
routing.

After the receipt, `self-check` also reports what is left of the homework
itself: a `TODO` line for each unfilled required identity/effort field, each
unanswered agent-reflection question, and a missing `AGENTS.md` "My
preferences" section.
It exits clean only when nothing remains — rerun it when you think you are
done.

## Windows

Use WSL first. It gives you a Linux environment close to the department hosts,
and the graded receipt comes from WSL or a department host. If you want a
native Windows shell for daily work, MSYS2 is bash + git + pacman on native
Windows — [`guides/windows.md`](guides/windows.md) has the five-step recipe.
`./setup` itself does not run under MSYS2 or Git Bash.
