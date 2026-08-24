#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Mechanical "breadcrumb" digests of Claude Code session transcripts.

Modes:
  claude-breadcrumbs.py digest TRANSCRIPT.jsonl
      Print a markdown digest of one session transcript to stdout.
  claude-breadcrumbs.py sessionend
      SessionEnd hook entry point. Reads the hook JSON on stdin, parses
      the completed session transcript, writes a digest under
      ~/dotfiles/claude/breadcrumbs/, and publishes a terminal-paired
      pending pointer for the next sessionstart.
  claude-breadcrumbs.py sessionstart
      SessionStart hook entry point (wired with matcher "clear" in
      claude/settings.json). Reads the hook JSON on stdin, looks up the
      terminal-paired pending pointer written by sessionend, and prints a
      short pointer that Claude Code injects into the fresh session's
      context. Falls back to a short list of recent sessions.

Why mechanical: the final assistant message of every turn is already a
summary (the harness asks the model to write it for "a teammate who
stepped away"), so a /clear restart prompt can be assembled from the
transcript with no model pass at all. The hook injects only a pointer,
not the full digest, so a /clear meant as a genuine fresh start is not
polluted by a stale trail; continuing costs the model one Read.

The hook must never break session start: sessionstart mode prints
nothing and exits 0 on any failure (diagnostics on stderr).
"""

# pyright: strict
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

MAX_PROMPT_CHARS = 600
MAX_OUTCOME_CHARS = 1200  # final turn exempt: its summary is the restart prompt
OUTCOME_TURNS = 10  # outcomes only for the most recent N turns
MAX_AGE_DAYS = 7  # ignore prior transcripts older than this
REAP_AGE_DAYS = 7  # delete digest files older than this
PENDING_REAP_SECONDS = 300  # delete pending files older than this
FRESH_SECONDS = 30  # pending file freshness window
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})

# Mirrors the /handoff convention: output lives under ~/dotfiles/claude/
# (not ~/.claude/) so the permissions gate on ~/.claude/ never applies,
# and the directory is gitignored.
_DEFAULT_BREADCRUMB_DIR = Path.home() / "dotfiles" / "claude" / "breadcrumbs"
BREADCRUMB_DIR = Path(
    os.environ.get("CLAUDE_BREADCRUMBS_DIR", str(_DEFAULT_BREADCRUMB_DIR))
)

Entry = dict[str, Any]  # Any: JSON boundary — transcript lines are schemaless


def _local(ts: float) -> datetime:
    """Wall-clock local time for a POSIX timestamp, as an aware datetime.

    Digest stamps and the session picker are read by a human sitting at this
    machine, so they stay in local time; going through UTC only keeps the
    result tz-aware.
    """
    return datetime.fromtimestamp(ts, tz=UTC).astimezone()


class HookInput(TypedDict, total=False):
    """SessionStart hook JSON input."""

    transcript_path: str
    session_id: str


@dataclass(frozen=True, slots=True)
class Token:
    """Per-terminal token: kind, value, and strength."""

    kind: Literal["pane", "tty", "ppid"]  # "pane", "tty", or "ppid"
    value: str  # sanitized identifier
    strong: bool  # high-confidence unique identifier


@dataclass(frozen=True, slots=True)
class Pending:
    """Atomic pending file for terminal-paired breadcrumbs."""

    session_id: str  # session UUID
    project_dir: str  # project directory path
    ended: str  # ISO timestamp
    digest_path: str  # path to breadcrumb digest
    token_kind: str  # token kind: "pane", "tty", or "ppid"
    wall_ts: float  # wall time (seconds since epoch)


@dataclass(frozen=True, slots=True)
class Candidate:
    """Recent session for short-list fallback."""

    session_id: str  # full session UUID
    short_id: str  # shortened unique prefix
    title: str  # custom-title or ""
    prompt: str  # first user prompt, truncated
    when: str  # HH:MM local time
    path: str  # absolute path to transcript


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_token(value: str) -> str:
    cleaned = _SAFE.sub("-", value)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-._")


def _is_real_tty(name: str) -> bool:
    # macOS controlling ttys are /dev/ttys00N; Linux are /dev/pts/N. Reject
    # sentinels, non-terminal /dev nodes (e.g. /dev/null), and the bare
    # /dev/tty alias (which names the controlling terminal generically,
    # not a unique device — promoting it to a strong token would let two
    # different terminals share tty-tty and collide).
    if not name or name in {"?", "??"}:
        return False
    if not name.startswith("/dev/"):
        return False
    base = os.path.basename(name)
    if base == "tty":  # bare /dev/tty alias names the controlling terminal
        return False    # generically, not a unique device — can't disambiguate
    return base.startswith("tty") or name.startswith("/dev/pts/")


def resolve_tty() -> str | None:
    """Controlling terminal of this process, or None. Side-effecting."""
    ttyname = cast(
        Callable[[int], str] | None,
        getattr(os, "ttyname", None),  # Platform-specific stdlib attribute.
    )
    if ttyname is None:
        return None
    try:
        fd = os.open("/dev/tty", os.O_RDONLY)
    except OSError:
        return None
    try:
        return ttyname(fd)
    except OSError:
        return None
    finally:
        os.close(fd)


def compute_token(env: Mapping[str, str], tty_name: str | None) -> Token:
    pane = env.get("TMUX_PANE", "")
    if pane:
        return Token("pane", sanitize_token(pane), True)
    if tty_name is not None and _is_real_tty(tty_name):
        return Token("tty", sanitize_token(tty_name.removeprefix("/dev/")), True)
    ppid = env.get("PPID") or str(os.getppid())
    return Token("ppid", sanitize_token(ppid), False)


def _as_entry(value: object) -> Entry | None:
    """Narrow a JSON value to a dict via cast, keeping strict mode Unknown-free."""
    return cast(Entry, value) if isinstance(value, dict) else None


def _as_blocks(value: object) -> list[Any] | None:  # Any: JSON boundary
    return cast("list[Any]", value) if isinstance(value, list) else None


@dataclass(slots=True)
class Turn:
    """One user prompt and what came of it."""

    prompt: str
    when: str  # HH:MM local, or "" if the timestamp was unparseable
    outcome: str = ""
    files: list[str] = field(default_factory=list[str])


@dataclass(frozen=True, slots=True)
class Digest:
    cwd: str
    branch: str
    session_id: str
    started: str
    ended: str
    turns: list[Turn]  # one-line reason: mutated during assembly, then frozen here


def _local_hhmm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")
    except ValueError:
        return ""


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _user_prompt_text(entry: Entry) -> str | None:
    """Extract a real user prompt, or None for tool results / meta noise."""
    if entry.get("isMeta") or entry.get("isSidechain"):
        return None
    message = _as_entry(entry.get("message")) or {}
    content: Any = message.get("content")  # Any: JSON boundary
    blocks = _as_blocks(content)
    if isinstance(content, str):
        text = content
    elif blocks is not None:
        parts: list[str] = []
        for block_value in blocks:
            block = _as_entry(block_value)
            if block is None or block.get("type") == "tool_result":
                return None
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        text = "\n".join(parts)
    else:
        return None
    text = text.strip()
    if not text:
        return None
    # Slash-command invocations arrive tag-wrapped; keep the command name.
    if text.startswith("<command-name>"):
        name = text.split("<command-name>", 1)[1].split("</command-name>", 1)[0]
        return f"(ran {name.strip()})"
    # Everything else tag- or bracket-wrapped is harness plumbing, not the user:
    # <local-command-stdout>, <system-reminder>, [SYSTEM NOTIFICATION ...], etc.
    if text.startswith(("<", "[")):
        return None
    if text.startswith("Caveat:"):
        return None
    return text


def parse_transcript(path: Path) -> Digest | None:
    """Assemble per-turn breadcrumbs from one transcript. None if unreadable."""
    turns: list[Turn] = []
    current: Turn | None = None
    branch = ""
    session_id = ""
    first_ts = ""
    last_ts = ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"claude-breadcrumbs: cannot read {path}: {exc}", file=sys.stderr)
        return None
    for line in lines:
        try:
            raw: Any = json.loads(line)  # Any: JSON boundary
        except json.JSONDecodeError:
            continue
        entry = _as_entry(raw)
        if entry is None:
            continue
        ts = str(entry.get("timestamp", ""))
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        branch = str(entry.get("gitBranch", "")) or branch
        session_id = str(entry.get("sessionId", "")) or session_id
        kind = entry.get("type")
        if kind == "user":
            prompt = _user_prompt_text(entry)
            if prompt is not None:
                if current is not None:
                    turns.append(current)
                current = Turn(prompt=_truncate(prompt, MAX_PROMPT_CHARS),
                               when=_local_hhmm(ts))
        elif kind == "assistant" and current is not None:
            if entry.get("isSidechain"):
                continue
            message = _as_entry(entry.get("message")) or {}
            blocks = _as_blocks(message.get("content"))
            if blocks is None:
                continue
            for block_value in blocks:
                block = _as_entry(block_value)
                if block is None:
                    continue
                if block.get("type") == "text" and str(block.get("text", "")).strip():
                    # Keep overwriting: the turn's outcome is its LAST text.
                    # Stored untruncated; render() caps all but the final turn.
                    current.outcome = str(block["text"]).strip()
                elif (
                    block.get("type") == "tool_use"
                    and block.get("name") in EDIT_TOOLS
                ):
                    tool_input = _as_entry(block.get("input")) or {}
                    file_path = str(
                        tool_input.get("file_path")
                        or tool_input.get("notebook_path")
                        or ""
                    )
                    if file_path and file_path not in current.files:
                        current.files.append(file_path)
    if current is not None:
        turns.append(current)
    if not turns:
        return None
    cwd = str(path.parent.name)
    return Digest(cwd=cwd, branch=branch, session_id=session_id,
                  started=first_ts, ended=last_ts, turns=turns)


def render(digest: Digest) -> str:
    """Markdown digest: every prompt, outcomes only for the newest turns.

    The final turn's outcome is never truncated — it is the closest thing
    the trail has to a restart prompt, and its tail (usually "next steps")
    is exactly what a cap would cut.
    """
    short_id = digest.session_id[:8] or "unknown"
    header = [
        f"# Breadcrumbs — session {short_id} ({digest.cwd})",
        (f"Branch: {digest.branch or 'unknown'}; "
         f"{len(digest.turns)} turns, {digest.started} → {digest.ended}."),
        "",
        "Per-turn trail harvested mechanically from the session transcript:",
        "each turn's prompt, the files it edited, and the model's own",
        "end-of-turn summary. Older turns keep only their prompts; the",
        "final turn's summary is kept in full.",
        "",
    ]
    body: list[str] = []
    outcome_cutoff = max(0, len(digest.turns) - OUTCOME_TURNS)
    for index, turn in enumerate(digest.turns, start=1):
        stamp = f" ({turn.when})" if turn.when else ""
        body.append(f"## Turn {index}{stamp}")
        body.append(f"**User:** {turn.prompt}")
        if index > outcome_cutoff:
            if turn.files:
                body.append(f"**Files:** {', '.join(turn.files)}")
            if turn.outcome:
                outcome = (turn.outcome if index == len(digest.turns)
                           else _truncate(turn.outcome, MAX_OUTCOME_CHARS))
                body.append(f"**Outcome:** {outcome}")
        body.append("")
    return "\n".join(header + body)


def digest_path(root: Path, stamp: str, session_id: str, slug: str) -> Path:
    """Collision-safe digest filename: includes session ID to disambiguate."""
    short = session_id[:8] or "unknown"
    return root / f"{stamp}-{short}-{slug}.md"


def pending_path(root: Path, token: Token) -> Path:
    return root / "pending" / f"{token.kind}-{token.value}.json"


def delete_pending(root: Path, token: Token) -> None:
    try:
        pending_path(root, token).unlink()
    except OSError:
        pass


def _pending_to_dict(p: Pending) -> dict[str, Any]:  # Any: JSON boundary
    return {"session_id": p.session_id, "project_dir": p.project_dir,
            "ended": p.ended, "digest_path": p.digest_path,
            "token_kind": p.token_kind, "wall_ts": p.wall_ts}


def _pending_from_dict(raw: Any) -> Pending | None:  # Any: JSON boundary
    if not isinstance(raw, dict):
        return None
    try:
        # isinstance guard narrows to dict; explicit annotation avoids cast
        return Pending(
            session_id=str(raw["session_id"]),  # type: ignore[index]
            project_dir=str(raw["project_dir"]),  # type: ignore[index]
            ended=str(raw["ended"]),  # type: ignore[index]
            digest_path=str(raw["digest_path"]),  # type: ignore[index]
            token_kind=str(raw["token_kind"]),  # type: ignore[index]
            wall_ts=float(raw["wall_ts"]),  # type: ignore[index]
        )
    except (KeyError, TypeError, ValueError):
        return None


def publish_pending(root: Path, token: Token, pending: Pending) -> None:
    path = pending_path(root, token)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_pending_to_dict(pending)), encoding="utf-8")
    os.replace(tmp, path)  # atomic same-dir replace


def read_pending(root: Path, token: Token, now: float,
                 project_dir: str) -> Pending | None:
    try:
        raw_text = pending_path(root, token).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        raw: Any = json.loads(raw_text)  # Any: JSON boundary
    except json.JSONDecodeError:
        return None
    pending = _pending_from_dict(raw)
    if pending is None:
        return None
    if now - pending.wall_ts > FRESH_SECONDS:
        return None
    if pending.project_dir != project_dir:
        return None
    return pending


def reap_pending(root: Path, now: float) -> None:
    """Delete pending JSON files older than PENDING_REAP_SECONDS."""
    cutoff = now - PENDING_REAP_SECONDS
    pend = root / "pending"
    if not pend.is_dir():
        return
    for old in pend.glob("*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def _unique_prefixes(ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for full in ids:
        n = 8
        while any(full != other and other.startswith(full[:n])
                  for other in ids):
            n += 1
            if n >= len(full):
                break
        out[full] = full[:n]
    return out


def _peek_session(path: Path) -> tuple[str, str]:
    """(custom-title, first-user-prompt snippet). Cheap, stops at first prompt."""
    title = ""
    prompt = ""
    try:
        lines = path.open(encoding="utf-8")
    except OSError:
        return ("", "")
    with lines:
        for line in lines:
            try:
                raw: Any = json.loads(line)  # Any: JSON boundary
            except json.JSONDecodeError:
                continue
            entry = _as_entry(raw)
            if entry is None:
                continue
            if entry.get("type") == "custom-title" and not title:
                title = str(entry.get("title", ""))
            if entry.get("type") == "user":
                text = _user_prompt_text(entry)
                if text is not None:
                    prompt = _truncate(text, 70)
                    break
    return (title, prompt)


def gather_recent(project_dir: Path, exclude_id: str, now: float,
                  max_age_seconds: int, limit: int) -> list[Candidate]:
    cutoff = now - max_age_seconds
    paths = sorted(
        (p for p in project_dir.glob("*.jsonl")
         if not p.name.startswith("agent-")
         and p.stem != exclude_id
         and p.stat().st_mtime >= cutoff),
        key=lambda p: p.stat().st_mtime, reverse=True)
    kept: list[Path] = []
    metas: list[tuple[str, str]] = []
    for p in paths:
        title, prompt = _peek_session(p)
        if not prompt:  # skip turn-less/unreadable transcripts
            continue
        kept.append(p)
        metas.append((title, prompt))
        if len(kept) >= limit:
            break
    shorts = _unique_prefixes([p.stem for p in kept])
    out: list[Candidate] = []
    for p, (title, prompt) in zip(kept, metas, strict=True):
        when = _local(p.stat().st_mtime).strftime("%H:%M")
        out.append(Candidate(session_id=p.stem, short_id=shorts[p.stem],
                             title=title, prompt=prompt, when=when, path=str(p)))
    return out


def render_short_list(candidates: list[Candidate]) -> str:
    head = ("Recent sessions in this directory (couldn't auto-identify the one "
            "you cleared):")
    lines = [head]
    for c in candidates:
        tag = f"[{c.title}] " if c.title else ""
        lines.append(f'  {c.short_id}  {tag}"{c.prompt}"  ({c.when})')
        lines.append(f"      transcript: {c.path}")
    lines.append("Tell me which to continue and I'll Read its transcript, or "
                 "run `claude-breadcrumbs.py digest <path>`.")
    return "\n".join(lines)



def _reap_old_digests(root: Path, now: float) -> None:
    cutoff = now - REAP_AGE_DAYS * 86400
    for old in root.glob("*.md"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def _pointer_text(pending: Pending) -> str:
    return (f"Breadcrumbs from the session you just cleared "
            f"(ended {pending.ended}) are saved at {pending.digest_path}.\n"
            f"If you asked to continue/resume prior work, Read that file first. "
            f"Otherwise ignore it.")


def run_sessionstart(hook: HookInput, root: Path, env: Mapping[str, str],
                     tty_name: str | None, now: float) -> str | None:
    transcript = hook.get("transcript_path", "")
    if not transcript:
        return None
    project_dir = Path(transcript).parent
    token = compute_token(env, tty_name)
    if token.strong:
        pending = read_pending(root, token, now, str(project_dir.resolve()))
        if pending is not None:
            delete_pending(root, token)
            return _pointer_text(pending)
    candidates = gather_recent(project_dir, hook.get("session_id", ""),
                               now, MAX_AGE_DAYS * 86400, 4)
    if not candidates:
        return None
    return render_short_list(candidates)


def run_sessionend(hook: HookInput, root: Path, env: Mapping[str, str],
                   tty_name: str | None, now: float) -> None:
    """Orchestrate sessionend: delete-first, parse, digest, publish (if strong)."""
    transcript = hook.get("transcript_path", "")
    if not transcript:
        return
    token = compute_token(env, tty_name)
    delete_pending(root, token)          # delete-first (clears crashed predecessor)
    reap_pending(root, now)
    digest = parse_transcript(Path(transcript))
    if digest is None or not digest.turns:
        return                           # zero turns → nothing to continue
    root.mkdir(parents=True, exist_ok=True)
    _reap_old_digests(root, now)
    stamp = _local(now).strftime("%Y-%m-%dT%H-%M-%S")
    slug = Path(transcript).parent.name
    dpath = digest_path(root, stamp, digest.session_id, slug)
    dpath.write_text(render(digest), encoding="utf-8")
    if not token.strong:
        return                           # archive only; SessionStart will fall back
    publish_pending(root, token, Pending(
        session_id=digest.session_id,
        project_dir=str(Path(transcript).parent.resolve()),
        ended=digest.ended, digest_path=str(dpath),
        token_kind=token.kind, wall_ts=now))


def sessionend() -> None:
    """Hook entry: digest the session being cleared, stash a paired pointer."""
    hook = cast(HookInput, json.load(sys.stdin))  # Any: JSON boundary via cast
    run_sessionend(hook, BREADCRUMB_DIR, os.environ, resolve_tty(), time.time())


def sessionstart() -> None:
    """Hook entry: replay the paired pointer, or inject a short list."""
    hook = cast(HookInput, json.load(sys.stdin))  # Any: JSON boundary via cast
    text = run_sessionstart(hook, BREADCRUMB_DIR, os.environ, resolve_tty(),
                            time.time())
    if text:
        print(text)


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "digest":
        digest = parse_transcript(Path(sys.argv[2]))
        if digest is None:
            print("claude-breadcrumbs: no usable turns found", file=sys.stderr)
            return 1
        print(render(digest))
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "sessionend":
        try:
            sessionend()
        except Exception as exc:  # noqa: BLE001 — hook must never block clear
            print(f"claude-breadcrumbs: {exc}", file=sys.stderr)
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == "sessionstart":
        try:
            sessionstart()
        except Exception as exc:  # noqa: BLE001 — hook must never block session start
            print(f"claude-breadcrumbs: {exc}", file=sys.stderr)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
