# Department Linux hosts

`remote-run` keeps a command alive in tmux after your laptop disconnects. It is
the dispatcher, not the entire remote environment: SSH access, a concrete host,
tmux, and a current project checkout must already exist.

## 1. Establish SSH access

UTCS documents the public host pool and SSH-key setup here:

- [Public Linux hosts](https://www.cs.utexas.edu/facilities/public-labs)
- [Finding a public host](https://www.cs.utexas.edu/faq/751)
- [SSH keys from macOS or Linux](https://www.cs.utexas.edu/ssh-keys)

Use the pool name only to enter the department environment and choose a host:

```bash
ssh YOUR_CSID@linux.cs.utexas.edu
hostname -f
cshosts cmyk
```

From off campus, UTCS requires an SSH key unless you are connected through an
approved campus network or VPN path. Keep the private key on the laptop; never
put it in this repository.

For a long job, select and record one exact hostname, for example
`cyan.cs.utexas.edu`. Do not pass `linux.cs.utexas.edu` to `remote-run`: it is a
pool alias, while tmux sessions belong to one physical host and `remote-run`
makes several SSH connections while launching and inspecting a job.

## 2. Set up the department home

The public Linux hosts share your department home directory. Clone and set up
the dotfiles repository once from a department host, not once per host, if you
want department compute:

```bash
gh auth login
gh repo clone utac-f26/dotfiles-YOUR_GITHUB_LOGIN ~/dotfiles
cd ~/dotfiles
./setup
codex login
./self-check
```

Run `./setup` independently on a laptop with a separate home directory. GitHub
and Codex authentication are runtime state, so authenticate them in each home;
do not copy their state directories through this repository.

You may generate the homework receipt on the laptop or in the department home.
Department access and a successful remote dispatch are encouraged but are not
completion requirements.

The setup creates a separate SOPS age key in each independent home. If you later
need the same encrypted secret on both laptop and department machines, add both
*public* age recipients to `.sops.yaml` and run `sops updatekeys` on the encrypted
file from a machine that can already decrypt it. Never commit either private age
key.

## 3. Preflight an exact host

From the laptop, verify the concrete target and remote prerequisites:

```bash
HOST=YOUR_CSID@cyan.cs.utexas.edu
ssh "$HOST" 'hostname -f; command -v bash; command -v tmux; command -v git'
```

If any command path is missing, select another public host or contact UTCS
support. `remote-run` does not install or upload remote software.

## 4. Synchronize code, then dispatch

Treat GitHub as the boundary between the laptop checkout and department
checkout. Do not edit the same branch in both places at once.

```bash
# Laptop: commit and push the work the remote command needs.
git status --short
git push

# A short, bounded pull may use plain SSH.
ssh "$HOST" 'cd ~/project && git pull --rebase'

# A job that may outlive the connection goes through remote-run.
remote-run --cd '~/project' --name tests "$HOST" 'uv run pytest -x'
```

For a multiline job, write a local bash or sh file and pass its arguments after
the host. `remote-run` reads the file on the laptop and runs its contents in the
remote job; the file itself need not exist on the host.

```bash
cat > run-checks.sh <<'SH'
#!/usr/bin/env bash
set -e
printf 'Checking %s\n' "$1"
uv run pytest -x "$1"
SH
remote-run --cd '~/project' --name focused \
    --script run-checks.sh "$HOST" 'tests/test cli.py'
```

The first argument after `HOST` becomes `$1` in the script, the next becomes
`$2`, and so on. Quoted arguments keep their boundaries. With no arguments,
the script starts with zero positional parameters. Scripts without a shebang
also run under bash; a shebang naming an interpreter other than bash or sh is
rejected before dispatch.

The launch prints the exact follow-up commands. They remain usable after the
laptop sleeps or changes networks:

```bash
remote-run --check "$HOST" tests
remote-run --log "$HOST" tests
remote-run --attach "$HOST" tests
remote-run --list "$HOST"
remote-run --clean "$HOST"
```

A job's output is written to a log on the host as it runs, under
`~/.local/state/remote-run/`, ending with the exit status. Every launch and
`--clean` reap the finished windows, successful or failed, and compress their
logs; `--log` and `--check` keep reading the log after the window is gone, and
logs are deleted after 30 days. Because the department home is shared, the
same log directory is visible from every host; the log's first line names the
host the job ran on. Always record the exact host and window name in a
handoff.
