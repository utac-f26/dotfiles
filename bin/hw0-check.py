#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""HW0 completion checks. Prints 'TODO <item>' lines; exit 1 if any."""
# pyright: strict
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

try:
    import tomllib
except ImportError:  # Python < 3.11: tomllib is stdlib-only from 3.11 on.
    tomllib: ModuleType | None = None

COVER_FIELDS = ("name", "eid", "email", "hours spent on this assignment")
REFLECTIONS: tuple[tuple[str, str], ...] = (
    ("### did the agent come up with anything surprising", "surprising"),
    ("### where did you have to steer", "steering"),
    ("### permissions: which rule did you debate", "permissions"),
)
KNOWN_MODES = {"default", "acceptEdits", "plan"}
RULE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(\(.+\))?$")
BROAD_BASH = {"Bash", "Bash(*)"}
ALLOWED_TOP = {"approval_policy", "sandbox_mode", "sandbox_workspace_write"}
ALLOWED_SWW = {"writable_roots", "network_access"}
ALLOWED_APPROVAL = {"untrusted", "on-request"}


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast("list[object]", value)
    return [item for item in items if isinstance(item, str)]


def reflection_answer(text: str, heading: str) -> str:
    answer: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.lower().startswith(heading):
            in_section = True
            continue
        if in_section and line.startswith("#"):
            break
        if in_section:
            answer.append(line)
    return "\n".join(answer).strip()


def check_submission(root: Path) -> list[str]:
    todo: list[str] = []
    submission = root / "SUBMISSION.md"
    if not submission.is_file():
        return ["SUBMISSION.md is missing"]
    text = submission.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"^- ([^(:]+?)\s*(?:\([^)]*\))?\s*:\s*(.*)$", line)
        if match:
            fields[match.group(1).strip().lower()] = match.group(2).strip()
    for label in COVER_FIELDS:
        if not fields.get(label):
            todo.append(f"SUBMISSION.md: fill in '{label}'")
    for heading, short in REFLECTIONS:
        answer = reflection_answer(text, heading)
        if not answer or answer.lower() == "(your answer here)":
            todo.append(f"SUBMISSION.md: answer the {short} reflection question")
    return todo


def check_claude_permissions(root: Path) -> list[str]:
    path = root / "claude" / "settings.json"
    guide = "see guides/permissions.md"
    if not path.is_file():
        return [f"claude/settings.json is missing ({guide})"]
    try:
        # JSON boundary: json.loads is Any; narrow immediately to dict.
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"claude/settings.json is not valid JSON: {exc}"]
    if not isinstance(decoded, dict):
        return [f"claude/settings.json: author a permissions block ({guide})"]
    data = cast("dict[str, object]", decoded)
    perms_value = data.get("permissions")
    if not isinstance(perms_value, dict):
        return [f"claude/settings.json: author a permissions block ({guide})"]
    perms = cast("dict[str, object]", perms_value)
    todo: list[str] = []
    valid_rules = {
        key: [
            rule
            for rule in string_list(perms.get(key))
            if RULE_RE.match(rule)
        ]
        for key in ("allow", "ask", "deny")
    }
    if not valid_rules["allow"]:
        todo.append(
            "claude/settings.json: permissions needs at least one valid "
            f"allow rule ({guide})"
        )
    if not valid_rules["deny"]:
        todo.append(
            "claude/settings.json: permissions needs at least one valid "
            f"deny guardrail ({guide})"
        )
    mode = perms.get("defaultMode")
    if mode not in KNOWN_MODES:
        todo.append(
            f"claude/settings.json: defaultMode {mode!r} is not allowed for "
            "HW0 (use default, acceptEdits, or plan)"
        )
    broad = BROAD_BASH.intersection(string_list(perms.get("allow")))
    if broad:
        todo.append(
            "claude/settings.json: broad Bash auto-approval in allow "
            f"({', '.join(sorted(broad))}) is rejected for HW0"
        )
    return todo


def check_agents_md(root: Path) -> list[str]:
    agents_md = root / "AGENTS.md"
    if not agents_md.is_file() or "my preferences" not in agents_md.read_text(
        encoding="utf-8"
    ).lower():
        return ['AGENTS.md: agent-written "My preferences" section not found']
    return []


def _home() -> Path:
    return Path(os.path.realpath(os.environ.get("HOME", str(Path.home()))))


def _canon(path_str: str, home: Path) -> Path:
    expanded = os.path.expandvars(path_str)
    if expanded == "~" or expanded.startswith("~/"):
        expanded = str(home) + expanded[1:]
    path = Path(expanded)
    if not path.is_absolute():
        path = home / path
    return Path(os.path.realpath(path))


def _load_policy(path: Path, label: str) -> tuple[dict[str, object], list[str]]:
    if tomllib is None:  # pragma: no cover - check_codex_policy guards this
        return {}, []
    try:
        # TOML boundary: tomllib.loads is dict[str, Any]; narrow immediately.
        decoded: dict[str, object] = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, [f"{label}: unreadable TOML ({exc})"]
    return decoded, []


def _policy_fields(
    data: dict[str, object], home: Path
) -> tuple[object, object, frozenset[Path], object]:
    sww_value = data.get("sandbox_workspace_write")
    sww = cast("dict[str, object]", sww_value) if isinstance(sww_value, dict) else {}
    canon_roots = frozenset(
        _canon(entry, home) for entry in string_list(sww.get("writable_roots"))
    )
    return (
        data.get("approval_policy"),
        data.get("sandbox_mode"),
        canon_roots,
        sww.get("network_access", False),
    )


def check_codex_policy(root: Path) -> list[str]:
    if tomllib is None:
        return [
            "codex policy check needs python3 >= 3.11 (yours is "
            f"{sys.version_info.major}.{sys.version_info.minor}); install a "
            "newer python3"
        ]
    home = _home()
    guide = "see guides/permissions.md"
    seed_path = root / "codex" / "config.seed.toml"
    if not seed_path.is_file():
        return [f"codex/config.seed.toml is missing ({guide})"]
    seed, todo = _load_policy(seed_path, "codex/config.seed.toml")
    if todo:
        return todo
    for key in seed:
        if key not in ALLOWED_TOP:
            todo.append(
                f"codex/config.seed.toml: key {key!r} is not part of the "
                f"HW0 policy ({guide})"
            )
    sww_value = seed.get("sandbox_workspace_write")
    if isinstance(sww_value, dict):
        sww = cast("dict[str, object]", sww_value)
        for key in sww:
            if key not in ALLOWED_SWW:
                todo.append(
                    f"codex/config.seed.toml: [sandbox_workspace_write] key "
                    f"{key!r} is not part of the HW0 policy"
                )
        if "network_access" in sww and not isinstance(
            sww["network_access"], bool
        ):
            todo.append(
                "codex/config.seed.toml: [sandbox_workspace_write] "
                "network_access must be true or false"
            )
        if "writable_roots" in sww:
            roots_value = sww["writable_roots"]
            if isinstance(roots_value, list):
                entries = cast("list[object]", roots_value)
                all_strings = all(isinstance(entry, str) for entry in entries)
            else:
                all_strings = False
            if not all_strings:
                todo.append(
                    "codex/config.seed.toml: [sandbox_workspace_write] "
                    "writable_roots must be a list of strings"
                )
    if seed.get("approval_policy") not in ALLOWED_APPROVAL:
        todo.append(
            "codex/config.seed.toml: approval_policy must be 'untrusted' or "
            "'on-request' for HW0"
        )
    if seed.get("sandbox_mode") != "workspace-write":
        todo.append(
            "codex/config.seed.toml: sandbox_mode must be 'workspace-write' "
            "for HW0"
        )
    _, _, roots, _ = _policy_fields(seed, home)
    for canon_root in sorted(roots):
        if home == canon_root or home.is_relative_to(canon_root):
            todo.append(
                f"codex/config.seed.toml: writable_roots entry "
                f"{str(canon_root)!r} covers your whole home directory; "
                "widen one project root at a time instead"
            )
    if todo:
        return todo
    live_path = home / ".codex" / "config.toml"
    if not live_path.is_file():
        return [
            "~/.codex/config.toml is missing: copy the seed policy into the "
            f"live file ({guide})"
        ]
    live, live_todo = _load_policy(live_path, "~/.codex/config.toml")
    if live_todo:
        return live_todo
    labels = ("approval_policy", "sandbox_mode", "writable_roots", "network_access")
    for label, seed_val, live_val in zip(
        labels, _policy_fields(seed, home), _policy_fields(live, home), strict=True
    ):
        if seed_val != live_val:
            todo.append(
                f"codex policy drift: {label} differs between "
                "codex/config.seed.toml and ~/.codex/config.toml"
            )
    return todo


def check_codex_version(root: Path, active: str) -> list[str]:
    pin_path = root / "codex" / "pinned-version"
    if not pin_path.is_file():
        return ["codex/pinned-version is missing from the repo"]
    pinned = pin_path.read_text(encoding="utf-8").strip()
    pin_match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", pinned)
    if not pin_match:
        return [f"codex/pinned-version is malformed: {pinned!r}"]
    pin = tuple(int(part) for part in pin_match.groups())
    active_match = re.search(r"(\d+)\.(\d+)\.(\d+)", active)
    if not active_match:
        return [
            "codex version unknown: install the pinned Codex CLI "
            f"({pinned}) and rerun"
        ]
    version = tuple(int(part) for part in active_match.groups())
    if version[0] != pin[0] or version < pin:
        return [
            f"codex {'.'.join(map(str, version))} is outside the supported "
            f"range (same major as, and at least, {pinned}); run "
            "./setup --update"
        ]
    return []


def checks(root: Path, codex_version: str) -> list[str]:
    todo = check_submission(root)
    todo += check_agents_md(root)
    todo += check_claude_permissions(root)
    todo += check_codex_policy(root)
    todo += check_codex_version(root, codex_version)
    return todo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--codex-version", default="")
    args = parser.parse_args()
    todo = checks(args.repo, args.codex_version)
    for item in todo:
        print(f"TODO {item}", file=sys.stderr)
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main())
