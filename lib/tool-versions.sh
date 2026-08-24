#!/usr/bin/env bash

# Shared semantic-version checks for setup and self-check. The caller supplies
# the manifest path so this file remains usable before any tools are installed.

utac_pinned_version() {
    local manifest="$1"
    local tool="$2"
    local value
    value="$(awk -v tool="$tool" '$1 == tool {print $2}' "$manifest")"
    [[ "$value" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
    printf '%s\n' "$value"
}

utac_version_is_compatible() {
    local output="$1"
    local minimum="$2"
    local semver_re='([0-9]+)\.([0-9]+)(\.([0-9]+))?'
    local actual_major actual_minor actual_patch
    local minimum_major minimum_minor minimum_patch

    [[ "$output" =~ $semver_re ]] || return 1
    actual_major="${BASH_REMATCH[1]}"
    actual_minor="${BASH_REMATCH[2]}"
    actual_patch="${BASH_REMATCH[4]:-0}"
    IFS=. read -r minimum_major minimum_minor minimum_patch <<<"$minimum"

    ((actual_major == minimum_major)) || return 1
    ((actual_minor > minimum_minor)) && return 0
    ((actual_minor == minimum_minor && actual_patch >= minimum_patch))
}
