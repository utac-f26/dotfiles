#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
# Sourcing self-check creates and owns TMP_DIR, including its EXIT cleanup.
# shellcheck disable=SC1091
source "${REPO_ROOT}/self-check"

FAKE_BIN="${TMP_DIR}/bin"
mkdir -p "$FAKE_BIN"
PATH="${FAKE_BIN}:${PATH}"
export PATH
REQUIRED_TOOLS="${TMP_DIR}/required-tools.txt"
TOOL_VERSIONS="${TMP_DIR}/tool-versions.txt"
CHECKS_TSV="${TMP_DIR}/checks.tsv"
TOOLS_TSV="${TMP_DIR}/tools.tsv"
printf '4 codex\n' >"$REQUIRED_TOOLS"
printf 'codex 0.147.0\n' >"$TOOL_VERSIONS"

NFS_WARNING='WARNING: failed to clean up stale arg0 temp dirs: Directory not empty (os error 39)'
# Modelled on gh: the banner names both versions, and the release link that
# follows it carries the new one alone. A parser that picks the first line
# satisfying the pin picks that link.
UPGRADE_BANNER='A new release of codex is available: 0.140.0 -> 0.147.0'
RELEASE_LINK='https://github.com/openai/codex/releases/tag/v0.147.0'

CHECK_LOG="${TMP_DIR}/check.log"
: >"$CHECK_LOG"

fail() {
    printf 'FAIL %s\n' "$*" >&2
    printf 'last self-check output:\n' >&2
    cat "$CHECK_LOG" >&2
    exit 1
}

# Installs a fake codex that prints the given lines and exits with the given
# status. The lines live in a file so nothing has to be re-quoted into the
# generated script.
write_fake_codex() {
    local exit_status="$1"
    shift
    printf '%s\n' "$@" >"${TMP_DIR}/codex-output"
    {
        printf '%s\n' '#!/usr/bin/env bash'
        printf 'cat %q\n' "${TMP_DIR}/codex-output"
        printf 'exit %s\n' "$exit_status"
    } >"${FAKE_BIN}/codex"
    chmod +x "${FAKE_BIN}/codex"
}

# self-check reports each check on stdout. Capture it so a failing case here
# is not mistaken for one of those lines, and print it only when this file
# actually fails.
run_core_tools() {
    FAILURES=0
    : >"$CHECKS_TSV"
    : >"$TOOLS_TSV"
    check_core_tools >"$CHECK_LOG" 2>&1
}

recorded_version() {
    awk -F'\t' -v tool="$1" '$1 == tool {print $3}' "$TOOLS_TSV"
}

# A successful command may emit diagnostics before its compatible version.
write_fake_codex 0 "$NFS_WARNING" 'codex-cli 0.147.0'
run_core_tools
[[ "$FAILURES" == 0 ]] || fail 'noisy output rejected a compatible codex'
[[ "$(recorded_version codex)" == 'codex-cli 0.147.0' ]] \
    || fail "recorded <$(recorded_version codex)>, wanted <codex-cli 0.147.0>"
printf 'PASS noisy successful version output\n'

# Version-shaped output must not hide a genuine command failure.
write_fake_codex 1 "$NFS_WARNING" 'codex-cli 0.147.0'
run_core_tools
[[ "$FAILURES" == 1 ]] || fail 'nonzero version command accepted'
grep -Fq $'core_tools\tfalse\t' "$CHECKS_TSV" \
    || fail 'nonzero version command did not fail core_tools'
printf 'PASS nonzero version command\n'

# A stale tool whose upgrade banner names the pinned version must still be
# rejected, and must be recorded with the version it actually has rather than
# with whatever the banner said.
write_fake_codex 0 'codex-cli 0.140.0' "$UPGRADE_BANNER" "$RELEASE_LINK"
run_core_tools
[[ "$FAILURES" == 1 ]] || fail 'stale codex accepted because its banner named the pin'
[[ "$(recorded_version codex)" == 'codex-cli 0.140.0' ]] \
    || fail "recorded <$(recorded_version codex)>, wanted <codex-cli 0.140.0>"
printf 'PASS stale tool with upgrade banner\n'

# An incompatible tool records its version, so the student is told what they
# have. An empty field would mean "could not run" or "printed nothing".
write_fake_codex 0 'codex-cli 0.140.0'
run_core_tools
[[ "$FAILURES" == 1 ]] || fail 'incompatible codex accepted'
[[ "$(recorded_version codex)" == 'codex-cli 0.140.0' ]] \
    || fail "incompatible codex recorded <$(recorded_version codex)>"
printf 'PASS incompatible tool reports its version\n'

# The HW0 receipt path reads the version through the same parser. Handing
# hw0-check.py the first line instead would give it a diagnostic with no
# version in it, and the receipt would be withheld from a working install.
write_fake_codex 0 "$NFS_WARNING" 'codex-cli 0.147.0'
codex_version="$(version_for codex || true)"
[[ "$codex_version" == 'codex-cli 0.147.0' ]] \
    || fail "version_for codex gave <${codex_version}>"
# Mirrors hw0-check.py's re.search(r"(\d+)\.(\d+)\.(\d+)", active).
[[ "$codex_version" =~ [0-9]+\.[0-9]+\.[0-9]+ ]] \
    || fail 'hw0-check.py would not find a version in the string self-check sends'
if grep -nE -- '--version[^|]*\|[[:space:]]*head' \
    "${REPO_ROOT}/self-check" "${REPO_ROOT}/setup"; then
    fail 'a --version call is still truncated with head'
fi
printf 'PASS homework version path\n'

# setup decides whether to reinstall a tool and self-check decides whether to
# accept it; they must never reach opposite verdicts on the same output. setup
# is sourced in a subshell because it resets TOOL_VERSIONS and REPO_ROOT and
# redefines functions self-check also defines.
(
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/setup"

    write_fake_codex 0 'codex-cli 0.147.0'
    tool_is_compatible codex 0.147.0 || exit 1
    write_fake_codex 0 "$NFS_WARNING" 'codex-cli 0.147.0'
    tool_is_compatible codex 0.147.0 || exit 1
    write_fake_codex 1 "$NFS_WARNING" 'codex-cli 0.147.0'
    ! tool_is_compatible codex 0.147.0 || exit 1
    write_fake_codex 0 'codex-cli 0.140.0' "$UPGRADE_BANNER" "$RELEASE_LINK"
    ! tool_is_compatible codex 0.147.0 || exit 1
) || fail 'setup and self-check disagree about codex'
printf 'PASS setup version compatibility\n'

# Positive control for the subshell above: sourcing setup in this shell would
# reset TOOL_VERSIONS to the real manifest, and every assertion after it would
# silently stop testing the fixture.
# shellcheck disable=SC2031 # The change being lost is exactly the assertion.
[[ "$TOOL_VERSIONS" == "${TMP_DIR}/tool-versions.txt" ]] \
    || fail 'sourcing setup clobbered the test fixture'
write_fake_codex 0 "$NFS_WARNING" 'codex-cli 0.147.0'
run_core_tools
[[ "$FAILURES" == 0 ]] || fail 'harness stopped working after sourcing setup'
printf 'PASS fixtures survive sourcing setup\n'

printf 'test-core-tools: PASS\n'
