#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# shellcheck disable=SC1091 # REPO_ROOT is resolved above.
source "${REPO_ROOT}/lib/tool-versions.sh"

assert_line() {
    local name="$1"
    local output="$2"
    local expected="$3"
    local actual

    if ! actual="$(utac_version_line "$output")"; then
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

assert_no_line() {
    local name="$1"
    local output="$2"

    if utac_version_line "$output" >/dev/null; then
        printf 'FAIL %s: empty output accepted\n' "$name" >&2
        return 1
    fi
    printf 'PASS %s\n' "$name"
}

assert_version() {
    local name="$1"
    local text="$2"
    local expected="$3"
    local actual

    if ! actual="$(utac_extract_version "$text")"; then
        printf 'FAIL %s: no version extracted\n' "$name" >&2
        return 1
    fi
    if [[ "$actual" != "$expected" ]]; then
        printf 'FAIL %s: expected <%s>, got <%s>\n' \
            "$name" "$expected" "$actual" >&2
        return 1
    fi
    printf 'PASS %s\n' "$name"
}

assert_no_version() {
    local name="$1"
    local text="$2"

    if utac_extract_version "$text" >/dev/null; then
        printf 'FAIL %s: found a version in <%s>\n' "$name" "$text" >&2
        return 1
    fi
    printf 'PASS %s\n' "$name"
}

assert_compatible() {
    local name="$1"

    if ! utac_version_is_compatible "$2" "$3"; then
        printf 'FAIL %s: <%s> rejected against %s\n' "$name" "$2" "$3" >&2
        return 1
    fi
    printf 'PASS %s\n' "$name"
}

assert_incompatible() {
    local name="$1"

    if utac_version_is_compatible "$2" "$3"; then
        printf 'FAIL %s: <%s> accepted against %s\n' "$name" "$2" "$3" >&2
        return 1
    fi
    printf 'PASS %s\n' "$name"
}

# --- version extraction -----------------------------------------------------

assert_version plain_semver 'codex-cli 0.147.0' 0.147.0
assert_version two_component 'remote-run 1.0' 1.0.0
assert_version parenthesised 'gh version 2.97.0 (2026-08-01)' 2.97.0
assert_version leading_v 'v22.17.1' 22.17.1
assert_version hyphenated 'jq-1.8.2' 1.8.2
assert_version four_component 'tool 1.2.3.4' 1.2.3
assert_no_version username_digits \
    'error: failed under /Users/sp4595/.cache/uv (os error 1)'
assert_no_version date_with_hyphens 'WARNING generated on 2026-08-30'
assert_no_version integer_only 'toolname 3'

# --- line selection ---------------------------------------------------------

assert_line nfs_warning \
    $'WARNING: failed to clean up stale arg0 temp dirs: Directory not empty (os error 39)\ncodex-cli 0.147.0' \
    'codex-cli 0.147.0'
assert_line sandbox_warning \
    $'WARNING: could not create PATH aliases: Operation not permitted (os error 1)\ncodex-cli 0.147.0' \
    'codex-cli 0.147.0'

# A diagnostic that quotes a number of its own must not outrank the tool's
# line, whichever side of the pin that number falls on.
assert_line diagnostic_quotes_low_version \
    $'WARNING: system library 2.17 needs attention\ncodex-cli 0.147.0' \
    'codex-cli 0.147.0'
assert_line diagnostic_quotes_high_version \
    $'WARNING: codex 0.148.0 is available\ncodex-cli 0.147.0' \
    'codex-cli 0.147.0'

# The regression this file exists for: gh prints its own version first and an
# upgrade banner after. Selecting the line that satisfies the pin would report
# a stale gh as current and record a release URL as its version.
GH_STALE=$'gh version 2.40.0 (2023-12-06)\nhttps://github.com/cli/cli/releases/tag/v2.40.0\n\nA new release of gh is available: 2.40.0 -> 2.97.0\nTo upgrade, run: gh extension upgrade gh\nhttps://github.com/cli/cli/releases/tag/v2.97.0'
assert_line upgrade_banner_loses "$GH_STALE" 'gh version 2.40.0 (2023-12-06)'
assert_incompatible stale_gh_rejected \
    "$(utac_version_line "$GH_STALE")" 2.97.0

# An incompatible tool still reports the version it has, so the failure can
# name it. Recording an empty version would collapse "too old" together with
# "could not run" and "printed nothing".
assert_line incompatible_still_reported 'codex-cli 0.140.0' 'codex-cli 0.140.0'
assert_incompatible incompatible_rejected 'codex-cli 0.140.0' 0.147.0

# Tools with no pin in tool-versions.txt still get a line recorded, including
# the ones whose --version carries no dotted number at all.
assert_line unpinned_tool 'remote-run 1.0' 'remote-run 1.0'
assert_line integer_version_falls_back 'toolname 3' 'toolname 3'
assert_line no_version_falls_back \
    'error: failed under /Users/sp4595/.cache/uv (os error 1)' \
    'error: failed under /Users/sp4595/.cache/uv (os error 1)'

# A diagnostic is the last resort, not a disqualification.
assert_line diagnostic_only 'WARNING: running 1.2.3 in degraded mode' \
    'WARNING: running 1.2.3 in degraded mode'
assert_line skips_blank_lines $'\n\ncodex-cli 0.147.0' 'codex-cli 0.147.0'
assert_no_line empty_output ''
assert_no_line blank_output $'\n   \n'

# --- compatibility ----------------------------------------------------------

assert_compatible exact_pin 'codex-cli 0.147.0' 0.147.0
assert_compatible newer_patch 'codex-cli 0.147.4' 0.147.0
assert_compatible newer_minor 'codex-cli 0.148.0' 0.147.0
assert_incompatible older_patch 'codex-cli 0.146.9' 0.147.0
assert_incompatible other_major 'codex-cli 1.147.0' 0.147.0
assert_incompatible no_version_at_all 'codex-cli unknown' 0.147.0

# A zero-padded component is a valid version field and an invalid octal
# literal. Before 10# forcing, bash printed "value too great for base" to the
# student's terminal on any output line shaped like this.
stderr_capture="$(utac_version_is_compatible 'tool 2.08.1' 2.7.0 2>&1 >/dev/null)"
if [[ -n "$stderr_capture" ]]; then
    printf 'FAIL leading_zero_is_quiet: stderr <%s>\n' "$stderr_capture" >&2
    exit 1
fi
printf 'PASS leading_zero_is_quiet\n'
assert_compatible leading_zero_minor 'tool 2.08.1' 2.7.0
assert_incompatible leading_zero_patch 'tool 2.7.08' 2.7.9

printf 'test-tool-versions: PASS\n'
