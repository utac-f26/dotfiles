#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Mechanical "breadcrumb" digests of Claude Code session transcripts.

Modes:
  claude-breadcrumbs.py digest TRANSCRIPT.jsonl
      Print a markdown digest of one session transcript to stdout.
  claude-breadcrumbs.py sessionend
      SessionEnd hook entry point, wired for every end reason (/clear,
      quit, logout) in claude/settings.json. Reads the hook JSON on stdin,
      parses the completed session transcript, writes a digest under
      ~/dotfiles/claude/breadcrumbs/, and publishes a terminal-paired
      pending pointer for the next sessionstart.
  claude-breadcrumbs.py sessionstart
      SessionStart hook entry point (wired with matchers "clear" and
      "startup" in claude/settings.json). Reads the hook JSON on stdin,
      looks up the terminal-paired pending pointer written by sessionend,
      and prints a short pointer that Claude Code injects into the fresh
      session's context. After /clear it falls back to a short list of
      archived digests for the directory, then of recent transcripts. At
      startup (a new `claude` process) it is quieter: one pointer to the
      directory's newest digest when that digest is under 24 hours old,
      nothing otherwise, so a quit-and-restart resumes like a /clear while
      a cold start days later stays clean.

The user's convention: a message beginning "resume" (formerly
"breadcrumbs") asks the new session to continue the digested work. The
injected text states that convention so the model does not have to infer
it; the keyword itself is nothing the hook sees.

Why mechanical: the final assistant message of every turn is already a
summary (the harness asks the model to write it for "a teammate who
stepped away"), so a /clear restart prompt can be assembled from the
transcript with no model pass at all. The hook injects only a pointer,
not the full digest, so a /clear meant as a genuine fresh start is not
polluted by a stale trail; continuing costs the model one Read.

The hook must never break session start: sessionstart mode prints
nothing and exits 0 on any failure (diagnostics on stderr).

Scripted runs opt out: Claude Code fires both hooks for `claude -p` too, so
a scripted reviewer (`claude-ask`) would archive a one-turn digest as the
directory's newest and would itself be handed the pointer to the user's
last report. Both modes return at once when the environment holds
CLAUDE_BREADCRUMBS=off, which the hook inherits from the launching shell.
"""

# pyright: strict
from __future__ import annotations

import io
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import dotpaths

# Digests carry "→", "…", and whatever the user typed, but Windows Python
# < 3.15 encodes piped stdout as cp1252: `digest` crashed on its header and
# sessionstart printed nothing (or a bare 0x85 byte) to the hook.
for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8")

MAX_PROMPT_CHARS = 600
MAX_OUTCOME_CHARS = 1200  # last report exempt: its summary is the restart prompt
OUTCOME_TURNS = 10  # outcomes only for the most recent N turns
PRIOR_REPORT_CHARS = 3000  # the previous digest's last report, inlined
WORKER_LINES = 6  # worker-message summaries kept per turn
WORKER_LINE_CHARS = 120
TEAMMATE_PREFIX = "Another Claude session sent a message"
RESUME_KEYWORDS = '"resume" (or the older "breadcrumbs")'
MAX_AGE_DAYS = 7  # ignore prior transcripts older than this
STARTUP_AGE_HOURS = 24  # at startup, point only at a digest this fresh
REAP_AGE_DAYS = 7  # delete digest files older than this
PENDING_REAP_SECONDS = 300  # delete pending files older than this
FRESH_SECONDS = 30  # pending file freshness window
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
OFF_VARIABLE = "CLAUDE_BREADCRUMBS"  # =off: scripted run, neither read nor write
OFF_VALUE = "off"

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
    """SessionStart / SessionEnd hook JSON input (the fields read here)."""

    transcript_path: str
    session_id: str
    source: str  # SessionStart: "startup", "resume", "clear", "compact", "fork"
    reason: str  # SessionEnd: "clear", "logout", "prompt_input_exit", "other"


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
    last_prompt: str = ""  # the cleared session's last user prompt, clipped


@dataclass(frozen=True, slots=True)
class Candidate:
    """Recent session for short-list fallback."""

    session_id: str  # full session UUID
    short_id: str  # shortened unique prefix
    title: str  # custom-title or ""
    prompt: str  # first user prompt, truncated
    when: str  # HH:MM local time
    path: str  # absolute path to transcript


@dataclass(frozen=True, slots=True)
class DigestCandidate:
    """Archived digest for this directory, for the fallback list."""

    path: str  # absolute path to the digest
    when: str  # HH:MM local time it was written
    turns: str  # "N turns" from the digest header, or ""
    last_prompt: str  # last **User:** line, truncated


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
    commits: list[str] = field(default_factory=list[str])  # "sha subject"
    workers: list[str] = field(default_factory=list[str])  # 'id: "summary"'
    worker_count: int = 0  # every relayed teammate message, kept or not
    command: bool = False  # a slash-command invocation, "(ran /x)"


@dataclass(frozen=True, slots=True)
class Digest:
    cwd: str
    branch: str
    session_id: str
    started: str
    ended: str
    turns: list[Turn]  # one-line reason: mutated during assembly, then frozen here
    compact: str = ""  # the latest compaction summary, whole
    compact_before: int = 0  # turns[:compact_before] finished before it
    continues_from: str = ""  # prior digest this session Read at its start


def _local_hhmm(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M")
    except ValueError:
        return ""


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _truncate_middle(text: str, limit: int) -> str:
    """Keep the head and the tail: an end-of-turn report ends with its next
    steps, which a head-only cut would drop."""
    text = text.strip()
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return text[:head].rstrip() + "\n[…]\n" + text[-tail:].lstrip()


_TEAMMATE_ATTR = re.compile(r'(\w+)="([^"]*)"')
_COMMIT_LINE = re.compile(r"^\[[^\]]*?\b([0-9a-f]{7,40})\] (.+)$", re.MULTILINE)


def _worker_line(text: str) -> str:
    """'id: "summary"' for one relayed teammate message.

    The relay wraps the message in a <teammate-message> tag whose summary
    attribute, when present, is the sender's own one-liner; otherwise the body
    is often an idle-notification JSON whose result field is the report.
    """
    tag_start = text.find("<teammate-message")
    tag_end = text.find(">", tag_start) if tag_start >= 0 else -1
    attrs: dict[str, str] = {}
    if tag_end >= 0:
        attrs = dict(_TEAMMATE_ATTR.findall(text[tag_start:tag_end]))
    sender = attrs.get("teammate_id", "worker")
    summary = attrs.get("summary", "")
    if not summary and tag_end >= 0:
        body = text[tag_end + 1:].split("</teammate-message>", 1)[0].strip()
        try:
            parsed: Any = json.loads(body)  # Any: JSON boundary
            result = _as_entry(parsed)
            summary = str(result.get("result", "")) if result else body
        except json.JSONDecodeError:
            summary = body
    return f'{sender}: "{_truncate(summary, WORKER_LINE_CHARS)}"'


def _record_commits(entry: Entry, pending: dict[str, Turn]) -> None:
    """Attach `sha subject` lines from a git commit's output to its turn."""
    message = _as_entry(entry.get("message")) or {}
    blocks = _as_blocks(message.get("content"))
    if blocks is None:
        return
    for block_value in blocks:
        block = _as_entry(block_value)
        if block is None or block.get("type") != "tool_result":
            continue
        turn = pending.pop(str(block.get("tool_use_id", "")), None)
        if turn is None:
            continue
        content: Any = block.get("content")  # Any: JSON boundary
        if isinstance(content, str):
            text = content
        else:
            parts = _as_blocks(content) or []
            text = "\n".join(str((_as_entry(p) or {}).get("text", "")) for p in parts)
        for sha, subject in _COMMIT_LINE.findall(text):
            line = f"{sha} {subject.strip()}"
            if line not in turn.commits:
                turn.commits.append(line)


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
    compact = ""
    compact_before = 0
    continues_from = ""
    pending_commits: dict[str, Turn] = {}  # Bash tool_use id → its turn
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
            if pending_commits:
                _record_commits(entry, pending_commits)
            prompt = _user_prompt_text(entry)
            if prompt is None:
                continue
            if entry.get("isCompactSummary"):
                # The harness's own summary of everything before it: the
                # densest state in the transcript. Kept whole; the turns it
                # covers are rendered prompt-only. The in-flight turn
                # straddles the compaction and keeps its outcome.
                compact = prompt
                compact_before = len(turns)
                continue
            if prompt.startswith(TEAMMATE_PREFIX):
                # A relayed worker message is traffic within the user's turn,
                # not a turn of its own; as turns, bursts of them pushed the
                # user's prompts out of the outcome window.
                if current is None:
                    current = Turn(prompt="(worker messages)", when=_local_hhmm(ts))
                current.worker_count += 1
                if len(current.workers) < WORKER_LINES:
                    current.workers.append(_worker_line(prompt))
                continue
            if current is not None:
                turns.append(current)
            current = Turn(prompt=_truncate(prompt, MAX_PROMPT_CHARS),
                           when=_local_hhmm(ts), command=prompt.startswith("(ran /"))
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
                    # Stored untruncated; render() caps all but the last report.
                    current.outcome = str(block["text"]).strip()
                elif block.get("type") == "tool_use":
                    name = block.get("name")
                    tool_input = _as_entry(block.get("input")) or {}
                    if name in EDIT_TOOLS:
                        file_path = str(
                            tool_input.get("file_path")
                            or tool_input.get("notebook_path") or ""
                        )
                        if file_path and file_path not in current.files:
                            current.files.append(file_path)
                    elif name == "Bash":
                        command = str(tool_input.get("command", ""))
                        if re.search(r"\bgit\b.*\bcommit\b", command):
                            pending_commits[str(block.get("id", ""))] = current
                    elif name == "Read" and not continues_from:
                        read_path = Path(str(tool_input.get("file_path", "")))
                        if (read_path.parent.name == BREADCRUMB_DIR.name
                                and read_path.suffix == ".md"):
                            continues_from = str(read_path)
    if current is not None:
        turns.append(current)
    # A local slash command (/clear, /model, ...) that produced nothing is
    # harness plumbing, not a step of the work.
    kept = [t for t in turns
            if not (t.command and not t.outcome and not t.files and not t.workers)]
    compact_before -= sum(1 for t in turns[:compact_before] if t not in kept)
    if not kept:
        return None
    cwd = str(path.parent.name)
    return Digest(cwd=cwd, branch=branch, session_id=session_id,
                  started=first_ts, ended=last_ts, turns=kept,
                  compact=compact, compact_before=compact_before,
                  continues_from=continues_from)


def _last_report(markdown: str) -> str:
    """The last **Outcome:** block of a rendered digest."""
    marker = "**Outcome:** "
    start = markdown.rfind(marker)
    if start < 0:
        return ""
    body = markdown[start + len(marker):]
    end = body.find("\n## ")
    return (body if end < 0 else body[:end]).strip()


def _prior_report(path_text: str) -> str:
    try:
        return _last_report(Path(path_text).read_text(encoding="utf-8"))
    except OSError:
        return ""


def render(digest: Digest) -> str:
    """Markdown digest: every prompt, outcomes only for the newest turns.

    The last report (the final turn that has an outcome) is never truncated:
    it is the closest thing the trail has to a restart prompt. Other kept
    outcomes lose their middle, so their "next steps" tails survive.
    """
    short_id = digest.session_id[:8] or "unknown"
    header = [
        f"# Breadcrumbs — session {short_id} ({digest.cwd})",
        (f"Branch: {digest.branch or 'unknown'}; "
         f"{len(digest.turns)} turns, {digest.started} → {digest.ended}."),
    ]
    if digest.continues_from:
        header.append(f"Continues from: {digest.continues_from}")
    header += [
        "",
        "Per-turn trail harvested mechanically from the session transcript:",
        "each turn's prompt, the worker messages that arrived during it, the",
        "files it edited, the commits it made, and the model's own end-of-turn",
        "summary. Older turns keep only their prompts; the last report is kept",
        "in full. A context summary, when present, covers the turns before it.",
        "",
    ]
    body: list[str] = []
    if digest.continues_from:
        prior = _prior_report(digest.continues_from)
        body.append("## Previous session's last report")
        body.append(_truncate_middle(prior, PRIOR_REPORT_CHARS) if prior
                    else "(that digest is no longer on disk)")
        body.append("")
    outcome_cutoff = max(digest.compact_before, len(digest.turns) - OUTCOME_TURNS)
    report_index = max((i for i, t in enumerate(digest.turns, start=1) if t.outcome),
                       default=0)
    for index, turn in enumerate(digest.turns, start=1):
        if digest.compact and index == digest.compact_before + 1:
            body.append("## Context summary")
            body.append(digest.compact)
            body.append("")
        stamp = f" ({turn.when})" if turn.when else ""
        body.append(f"## Turn {index}{stamp}")
        body.append(f"**User:** {turn.prompt}")
        if turn.worker_count:
            noun = "message" if turn.worker_count == 1 else "messages"
            body.append(f"**Workers:** {turn.worker_count} {noun} — "
                        + "; ".join(turn.workers))
        if turn.files:
            body.append(f"**Files:** {', '.join(turn.files)}")
        if turn.commits:
            body.append(f"**Commits:** {'; '.join(turn.commits)}")
        if index > outcome_cutoff and turn.outcome:
            outcome = (turn.outcome if index == report_index
                       else _truncate_middle(turn.outcome, MAX_OUTCOME_CHARS))
            body.append(f"**Outcome:** {outcome}")
        if index == len(digest.turns) and not turn.outcome and not turn.command:
            body.append("**Unanswered:** the session was cleared before a reply; "
                        "this prompt is still to be acted on.")
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
            "token_kind": p.token_kind, "wall_ts": p.wall_ts,
            "last_prompt": p.last_prompt}


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
            last_prompt=str(raw.get("last_prompt", "")),  # type: ignore[union-attr]
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
    if dotpaths.fold(pending.project_dir) != dotpaths.fold(project_dir):
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
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ("", "")
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


_RESUME_RULE = (f"A message beginning {RESUME_KEYWORDS} asks to continue earlier "
                "work. ")


def render_short_list(candidates: list[Candidate]) -> str:
    head = ("Recent sessions in this directory (the cleared one could not be "
            "identified, and no digest of it is archived):")
    lines = [head]
    for c in candidates:
        tag = f"[{c.title}] " if c.title else ""
        lines.append(f'  {c.short_id}  {tag}"{c.prompt}"  ({c.when})')
        lines.append(f"      transcript: {c.path}")
    lines.append(_RESUME_RULE + "On such a request, show this list and run "
                 "`claude-breadcrumbs.py digest <transcript>` on the chosen one; "
                 "otherwise ignore it.")
    return "\n".join(lines)


_TURNS_RE = re.compile(r"; (\d+ turns?),")


def _peek_digest(path: Path) -> tuple[str, str]:
    """("N turns", last **User:** line) from an archived digest."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ("", "")
    match = _TURNS_RE.search(text.split("\n", 3)[1] if "\n" in text else text)
    turns = match.group(1) if match else ""
    last_prompt = ""
    for line in text.splitlines():
        if line.startswith("**User:** "):
            last_prompt = line[len("**User:** "):]
    return (turns, _truncate(last_prompt, 70))


def gather_recent_digests(root: Path, slug: str, exclude_id: str, now: float,
                          max_age_seconds: int, limit: int) -> list[DigestCandidate]:
    """Archived digests for this directory, newest first.

    sessionend archives a digest whether or not it could publish a pointer,
    so when the pointer is missing the digests are still the better list:
    already rendered, and they name the work by its last prompt.
    """
    cutoff = now - max_age_seconds
    suffix = f"-{slug}.md"
    paths = sorted(
        (p for p in root.glob(f"*{suffix}")
         if p.name.endswith(suffix)
         and not (exclude_id and exclude_id[:8] in p.name)
         and p.stat().st_mtime >= cutoff),
        key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out: list[DigestCandidate] = []
    for p in paths:
        turns, last_prompt = _peek_digest(p)
        out.append(DigestCandidate(
            path=str(p), when=_local(p.stat().st_mtime).strftime("%H:%M"),
            turns=turns, last_prompt=last_prompt))
    return out


def render_digest_list(candidates: list[DigestCandidate]) -> str:
    head = ("Recent breadcrumb digests for this directory (the cleared session "
            "could not be identified):")
    lines = [head]
    for c in candidates:
        turns = f"  ({c.turns})" if c.turns else ""
        lines.append(f'  {c.when}  last prompt: "{c.last_prompt}"{turns}')
        lines.append(f"      digest: {c.path}")
    lines.append(_RESUME_RULE + "On such a request, show this list, Read the "
                 "chosen digest, and go on from its last report; otherwise "
                 "ignore it.")
    return "\n".join(lines)



def _reap_old_digests(root: Path, now: float) -> None:
    cutoff = now - REAP_AGE_DAYS * 86400
    for old in root.glob("*.md"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


_POINTER_RULE = (f"{_RESUME_RULE}On such a request, Read that file first and go "
                 "on from its last report; otherwise ignore it.")


def _pointer_text(pending: Pending) -> str:
    # "just ended", not "just cleared": the same pointer pairs a quit with a
    # restart in the same terminal inside the freshness window.
    gist = (f'Its last prompt: "{pending.last_prompt}"\n'
            if pending.last_prompt else "")
    return (f"Breadcrumbs from the session that just ended in this terminal "
            f"(ended {pending.ended}) are saved at {pending.digest_path}.\n"
            f"{gist}{_POINTER_RULE}")


def render_startup_pointer(digests: list[DigestCandidate]) -> str:
    """One pointer for a new process: the directory's newest fresh digest.

    A cold start is not a /clear, so no list and no raw-transcript fallback:
    the terminal pairing is gone and the newest digest is the one guess worth
    one line. Others in the window are counted so the model knows to look.
    """
    newest, rest = digests[0], digests[1:]
    gist = (f'Its last prompt: "{newest.last_prompt}"\n'
            if newest.last_prompt else "")
    more = ""
    if rest:
        noun = "digest" if len(rest) == 1 else "digests"
        more = (f"{len(rest)} other {noun} for this directory from the last "
                f"{STARTUP_AGE_HOURS} hours sit beside it.\n")
    return (f"Breadcrumbs from the last session in this directory (written "
            f"{newest.when}) are saved at {newest.path}.\n"
            f"{gist}{more}{_POINTER_RULE}")


def breadcrumbs_off(env: Mapping[str, str]) -> bool:
    """True for a run that opted out (a scripted `claude -p`, say)."""
    return env.get(OFF_VARIABLE, "").strip().lower() == OFF_VALUE


def run_sessionstart(hook: HookInput, root: Path, env: Mapping[str, str],
                     tty_name: str | None, now: float) -> str | None:
    transcript = hook.get("transcript_path", "")
    if not transcript or breadcrumbs_off(env):
        return None
    project_dir = Path(transcript).parent
    token = compute_token(env, tty_name)
    if token.strong:
        try:
            key: str | None = dotpaths.path_key(project_dir)
        except dotpaths.UnmappablePathError:
            key = None  # cannot pair without a key; fall back to the short list
        pending = None if key is None else read_pending(root, token, now, key)
        if pending is not None:
            delete_pending(root, token)
            return _pointer_text(pending)
    session_id = hook.get("session_id", "")
    if hook.get("source") == "startup":
        fresh = gather_recent_digests(root, project_dir.name, session_id, now,
                                      STARTUP_AGE_HOURS * 3600, 4)
        return render_startup_pointer(fresh) if fresh else None
    digests = gather_recent_digests(root, project_dir.name, session_id, now,
                                    MAX_AGE_DAYS * 86400, 4)
    if digests:
        return render_digest_list(digests)
    candidates = gather_recent(project_dir, session_id, now, MAX_AGE_DAYS * 86400, 4)
    if not candidates:
        return None
    return render_short_list(candidates)


def run_sessionend(hook: HookInput, root: Path, env: Mapping[str, str],
                   tty_name: str | None, now: float) -> None:
    """Orchestrate sessionend: delete-first, parse, digest, publish (if strong)."""
    transcript = hook.get("transcript_path", "")
    if not transcript or breadcrumbs_off(env):
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
    try:
        key = dotpaths.path_key(Path(transcript).parent)
    except dotpaths.UnmappablePathError:
        return                           # no key to pair on; archive only
    publish_pending(root, token, Pending(
        session_id=digest.session_id,
        project_dir=key,
        ended=digest.ended, digest_path=str(dpath),
        token_kind=token.kind, wall_ts=now,
        last_prompt=_truncate(digest.turns[-1].prompt, 100)))


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
