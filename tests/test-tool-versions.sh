#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck disable=SC1091 # REPO_ROOT is resolved above.
source "${REPO_ROOT}/lib/tool-versions.sh"

assert_line() {
    local name="$1"
    local output="$2"
    local minimum="$3"
    local expected="$4"
    local actual

    if ! actual="$(utac_version_line "$output" "$minimum")"; then
        printf 'FAIL %s: no version line\n' "$name" >&2
        return 1
    fi
    if [[ "$actual" != "$expected" ]]; then
        printf 'FAIL %s: expected <%s>, got <%s>\n' \
            "$name" "$expected" "$actual" >&2
        return 1
    fi
    printf 'PASS %s\n' "$name"
}

assert_rejected() {
    local name="$1"
    local output="$2"
    local minimum="$3"

    if utac_version_line "$output" "$minimum" >/dev/null; then
        printf 'FAIL %s: invalid output accepted\n' "$name" >&2
        return 1
    fi
    printf 'PASS %s\n' "$name"
}

assert_line nfs_warning \
    $'WARNING: failed to clean up stale arg0 temp dirs: Directory not empty (os error 39)\ncodex-cli 0.147.0' \
    0.147.0 'codex-cli 0.147.0'
assert_line sandbox_warning \
    $'WARNING: could not create PATH aliases: Operation not permitted (os error 1)\ncodex-cli 0.147.0' \
    0.147.0 'codex-cli 0.147.0'
assert_line unrelated_semver \
    $'WARNING: system library 2.17 needs attention\ncodex-cli 0.147.0' \
    0.147.0 'codex-cli 0.147.0'
assert_line unpinned_tool 'remote-run 1.0' '' 'remote-run 1.0'
assert_rejected username_digits \
    'error: failed under /Users/sp4595/.cache/uv (os error 1)' \
    0.147.0
assert_rejected date_with_hyphens 'WARNING generated on 2026-08-30' 0.147.0

printf 'test-tool-versions: PASS\n'
