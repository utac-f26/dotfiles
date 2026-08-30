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

write_fake_codex() {
    local exit_status="$1"

    {
        printf '%s\n' '#!/usr/bin/env bash'
        printf '%s\n' \
            "printf '%s\\n' 'WARNING: failed to clean up stale arg0 temp dirs: Directory not empty (os error 39)'"
        printf '%s\n' "printf '%s\\n' 'codex-cli 0.147.0'"
        printf 'exit %s\n' "$exit_status"
    } >"${FAKE_BIN}/codex"
    chmod +x "${FAKE_BIN}/codex"
}

# A successful command may emit diagnostics before its compatible version.
write_fake_codex 0
FAILURES=0
: >"$CHECKS_TSV"
check_core_tools
[[ "$FAILURES" == 0 ]]
grep -Fq $'codex\t' "$TOOLS_TSV"
grep -Fq 'codex-cli 0.147.0' "$TOOLS_TSV"
printf 'PASS noisy successful version output\n'

# Version-shaped output must not hide a genuine command failure.
write_fake_codex 1
FAILURES=0
: >"$CHECKS_TSV"
check_core_tools
[[ "$FAILURES" == 1 ]]
grep -Fq $'core_tools\tfalse\t' "$CHECKS_TSV"
printf 'PASS nonzero version command\n'

# setup uses the same parser when deciding whether a managed tool is current.
# shellcheck disable=SC1091
source "${REPO_ROOT}/setup"
write_fake_codex 0
tool_is_compatible codex 0.147.0
write_fake_codex 1
if tool_is_compatible codex 0.147.0; then
    printf 'FAIL setup accepted a failed version command\n' >&2
    exit 1
fi
printf 'PASS setup version compatibility\n'

printf 'test-core-tools: PASS\n'
