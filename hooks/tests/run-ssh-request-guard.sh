#!/bin/bash
# DESC: Run the ssh-request-guard PreToolUse hook against its case file
#
# Bash, not zsh, to match the hook under test and to keep working on Linux
# machines that sync agents-shared without /bin/zsh.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../ssh-request-guard.sh"
CASES="$HERE/ssh-request-guard-cases.tsv"

usage() {
    cat <<'USAGE'
usage: run-ssh-request-guard.sh [-v] [case-file]

Feeds each case to the hook as a PreToolUse payload and compares its verdict
(pass = no output, ask = permissionDecision "ask") with the expected one.

  -v   print every case, not just failures
USAGE
}

VERBOSE=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) CASES=$1; shift ;;
    esac
done

fail=0
total=0
while IFS=$'\t' read -r want cmd; do
    case "$want" in ''|\#*) continue ;; esac
    total=$((total + 1))
    decoded=$(printf '%b' "$cmd")
    out=$(jq -n --arg c "$decoded" '{tool_name: "Bash", tool_input: {command: $c}}' | "$HOOK")
    got=pass
    if [ -n "$out" ]; then
        got=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision')
    fi
    if [ "$got" != "$want" ]; then
        fail=$((fail + 1))
        printf 'FAIL  want %-4s got %-4s  %s\n' "$want" "$got" "$cmd"
    elif [ "$VERBOSE" = 1 ]; then
        printf 'ok    %-4s  %s\n' "$want" "$cmd"
    fi
done < "$CASES"

echo "$((total - fail))/$total passed"
[ "$fail" = 0 ]
