#!/usr/bin/env bash

# Shared semantic-version checks for setup and self-check. The caller supplies
# the manifest path so this file remains usable before any tools are installed.

# One dotted-version pattern for the whole file. Everything that needs a
# version number goes through utac_extract_version, so the line picker and the
# compatibility test cannot disagree about which number on a line is the
# version -- a disagreement would let setup and self-check reach opposite
# verdicts about the same installed tool.
UTAC_SEMVER_RE='(^|[^0-9])([0-9]+)\.([0-9]+)(\.([0-9]+))?([^0-9]|$)'

utac_pinned_version() {
    local manifest="$1"
    local tool="$2"
    local value
    value="$(awk -v tool="$tool" '$1 == tool {print $2}' "$manifest")"
    [[ "$value" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
    printf '%s\n' "$value"
}

# Prints the first dotted number in the text as major.minor.patch, defaulting a
# missing patch to 0. Fails when the text carries no version.
utac_extract_version() {
    [[ "$1" =~ $UTAC_SEMVER_RE ]] || return 1
    printf '%s.%s.%s\n' \
        "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[5]:-0}"
}

utac_version_is_compatible() {
    local output="$1"
    local minimum="$2"
    local actual
    local actual_major actual_minor actual_patch
    local minimum_major minimum_minor minimum_patch

    actual="$(utac_extract_version "$output")" || return 1
    IFS=. read -r actual_major actual_minor actual_patch <<<"$actual"
    IFS=. read -r minimum_major minimum_minor minimum_patch <<<"$minimum"
    [[ -n "$minimum_major" && -n "$minimum_minor" ]] || return 1
    minimum_patch="${minimum_patch:-0}"

    # 10# forces base 10. A component such as 08 is an ordinary version field
    # but an invalid octal literal, and a bare (( )) would print a raw bash
    # arithmetic error to the student's terminal before failing.
    ((10#$actual_major == 10#$minimum_major)) || return 1
    ((10#$actual_minor > 10#$minimum_minor)) && return 0
    ((10#$actual_minor == 10#$minimum_minor \
        && 10#$actual_patch >= 10#$minimum_patch))
}

# Picks the line of a tool's --version output that carries the version.
#
# Tools print diagnostics on stdout before their version -- codex warns about
# PATH aliases it could not create, and about stale temp dirs it could not
# remove on NFS -- so the first line is not reliably the version line.
#
# Two rules, in order. Lines opening with a diagnostic keyword are considered
# only if nothing else carries a version, so a warning that happens to quote a
# number cannot outrank the tool's own line. And a line is chosen by shape
# alone, never by whether its number satisfies a pin: filtering by the pin
# would let gh's "A new release of gh is available: 2.40.0 -> 2.97.0" outrank
# the stale "gh version 2.40.0" that printed it, reporting a stale tool as
# current and recording the banner as its version. Deciding compatibility is
# the caller's job, on the line this returns.
#
# Output with no dotted number at all still yields its first non-empty line,
# which is what the receipt recorded before this function existed; the caller's
# compatibility check is what rejects it.
utac_version_line() {
    # A subshell keeps nocasematch from leaking into the caller.
    (
        shopt -s nocasematch
        local diagnostic_re='^[[:space:]]*(warn|error|err|fatal|note|info|debug|hint|deprecat)'
        local line diagnostic="" fallback=""

        while IFS= read -r line; do
            [[ -n "${line//[[:space:]]/}" ]] || continue
            [[ -n "$fallback" ]] || fallback="$line"
            utac_extract_version "$line" >/dev/null || continue
            if [[ "$line" =~ $diagnostic_re ]]; then
                [[ -n "$diagnostic" ]] || diagnostic="$line"
                continue
            fi
            printf '%s\n' "$line"
            exit 0
        done <<<"$1"

        line="${diagnostic:-$fallback}"
        [[ -n "$line" ]] || exit 1
        printf '%s\n' "$line"
    )
}
