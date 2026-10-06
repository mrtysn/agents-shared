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

LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT
export SSH_REQUEST_GUARD_LOG=$LOG
asks=0
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
    [ "$got" = ask ] && asks=$((asks + 1))
    if [ "$got" != "$want" ]; then
        fail=$((fail + 1))
        printf 'FAIL  want %-4s got %-4s  %s\n' "$want" "$got" "$cmd"
    elif [ "$VERBOSE" = 1 ]; then
        printf 'ok    %-4s  %s\n' "$want" "$cmd"
    fi
done < "$CASES"

# every ask, and nothing else, is one JSON line in the log, carrying the command it stopped
logged=$(grep -c . "$LOG" || true)
if [ "$logged" != "$asks" ]; then
    fail=$((fail + 1))
    printf 'FAIL  log holds %s lines for %s asks\n' "$logged" "$asks"
fi
if [ "$asks" -gt 0 ] && ! jq -e 'select(.command != "" and .reason != "" and .at != "")' "$LOG" >/dev/null 2>&1; then
    fail=$((fail + 1))
    echo "FAIL  a log line lacks command, reason or time"
fi

echo "$((total - fail))/$total passed, $asks asks logged"
[ "$fail" = 0 ]
