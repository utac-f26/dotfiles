"""Path forms and comparison keys shared by the dotfiles Python scripts.

`os_path` turns a shell or Windows path into the form this interpreter's
`open()` accepts; `path_key` is for equality and containment only and is
never displayed or passed to a program. Entry points import this library from
their resolved sibling lib directory, so scripts linked under ~/bin find it.
"""

# pyright: strict
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

MSYS_DRIVE = re.compile(r"^/(?P<drive>[A-Za-z])/")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_DRIVE_ROOT = re.compile(r"^[A-Za-z]:$")
_UNC_ROOT = re.compile(r"^//[^/]+/[^/]+$")
_DEVICE_PREFIX = re.compile(r"^//[?.]/(?P<unc>unc/)?")
# Cygwin and MSYS2's msys Python see POSIX paths but run on Windows.
_POSIX_ON_WINDOWS = frozenset({"cygwin", "msys"})


class UnmappablePathError(ValueError):
    """A POSIX-rooted path whose native form needs cygpath, which is absent."""


def _cygpath(flag: str, word: str) -> str | None:
    # The cygpath on PATH belongs to the same runtime as the git and bash this
    # process inherited, so its mount table is the one the shell used.
    exe = shutil.which("cygpath")
    if exe is None:
        return None
    # The word goes on stdin, one per line, because the MSYS runtime re-parses
    # a native caller's command line (quotes, globs, braces). A line break
    # cannot ride that channel; cygpath also drops a trailing CR.
    if "\n" in word or "\r" in word:
        return None
    try:
        out = subprocess.run(
            [exe, flag, "-f", "-"], input=word + "\n",
            capture_output=True, encoding="utf-8", timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    value = out.stdout.strip()
    return value if out.returncode == 0 and value else None


def msys_drive_path(word: str) -> str:
    """Rewrite an MSYS drive path (`/c/Users/x`) as a native one (`C:/Users/x`)."""
    m = MSYS_DRIVE.match(word)
    return f"{m['drive'].upper()}:/{word[m.end():]}" if m else word


def os_path(word: str) -> str | None:
    """`word` in the form this interpreter can open; None if it cannot be mapped.

    Windows Python reads `/c/Users` as `C:\\c\\Users` and `/tmp` as `C:\\tmp`,
    but the shell maps `/tmp` through its mount table (`C:/msys64/tmp`).
    Without cygpath only a drive path (`/c/...`) is mappable.
    """
    if sys.platform == "win32":
        if not word.startswith("/") or word.startswith("//"):
            return word
        if "\n" in word or "\r" in word:
            return None  # cygpath cannot take it, so the fallback must not either
        mapped = _cygpath("-m", word)
        if mapped is not None:
            return mapped
        # cygpath takes ".." physically (a link's ".." is its target's parent)
        # and refuses ".." after a missing component; realpath would fold it
        # lexically and could name a different directory, so it is unmappable.
        if ".." in word.split("/"):
            return None
        native = msys_drive_path(word)
        return native if native != word else None
    if sys.platform in _POSIX_ON_WINDOWS and _WINDOWS_PATH.match(word):
        return _cygpath("-u", word)
    return word


def _strip(key: str) -> str:
    stripped = key.rstrip("/") or "/"
    if _DRIVE_ROOT.match(stripped) or _UNC_ROOT.match(stripped):
        return stripped + "/"
    return stripped


def fold(path: str) -> str:
    """Comparison form of a native path string, without touching the disk.

    Windows folds case and separators; POSIX keys keep case, and a backslash
    there is a filename character. Roots (`/`, `x:/`, `//server/share/`)
    keep their trailing slash.
    """
    if sys.platform == "win32":
        key = os.path.normcase(path).replace("\\", "/")
        # A device prefix names the same file as the plain path; realpath
        # strips it only when the plain path resolves.
        m = _DEVICE_PREFIX.match(key)
        if m:
            key = ("//" if m["unc"] else "") + key[m.end():]
    elif sys.platform in _POSIX_ON_WINDOWS:
        mixed = _cygpath("-m", path)
        key = (mixed if mixed is not None else path).lower()
    else:
        key = path
    return _strip(key)


def path_key(path: str | os.PathLike[str]) -> str:
    """Resolved, folded key for equality and containment tests."""
    word = os.fspath(path)
    native = os_path(word)
    if native is None:
        raise UnmappablePathError(word)
    return fold(os.path.realpath(native))


def key_within(child_key: str, parent_key: str) -> bool:
    if child_key == parent_key:
        return True
    prefix = parent_key if parent_key.endswith("/") else parent_key + "/"
    return child_key.startswith(prefix)


def is_within(child: str | os.PathLike[str], parent: str | os.PathLike[str]) -> bool:
    """Is `child` the same path as `parent`, or under it?

    Raises UnmappablePathError for a path that cannot be mapped.
    """
    return key_within(path_key(child), path_key(parent))
