#!/bin/bash
# DESC: Run the require-subagent-sizing PreToolUse hook against its case file

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../require-subagent-sizing.sh"
CASES="$HERE/require-subagent-sizing-cases.tsv"

VERBOSE=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) echo "usage: run-require-subagent-sizing.sh [-v] [case-file]"; exit 0 ;;
        *) CASES=$1; shift ;;
    esac
done

total=0
failed=0

while IFS=$'\t' read -r verdict input; do
    case "${verdict-}" in
        ''|'#'*) continue ;;
    esac
    want_effort=
    case "$verdict" in
        pass) want=0 ;;
        block) want=2 ;;
        effort=*) want=0; want_effort=${verdict#effort=} ;;
        *) echo "unknown verdict '$verdict'" >&2; exit 1 ;;
    esac

    payload=$(jq -cn --argjson i "$input" '{tool_name: "Agent", tool_input: $i}')
    got=0
    out=$(printf '%s' "$payload" | "$HOOK" 2>/dev/null) || got=$?

    # What the call runs with: the hook's updatedInput if it rewrote, else nothing
    got_effort=
    [ -n "$out" ] && got_effort=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.updatedInput.effort // empty')
    [ "$verdict" = pass ] && [ -n "$out" ] && got=rewrote

    total=$((total + 1))
    if [ "$got" = "$want" ] && [ "$got_effort" = "$want_effort" ]; then
        [ "$VERBOSE" = "1" ] && printf 'ok    %-13s %s\n' "$verdict" "$input"
    else
        failed=$((failed + 1))
        printf 'FAIL  want %s effort=%s, got %s effort=%s: %s\n' "$want" "$want_effort" "$got" "$got_effort" "$input"
    fi
done < "$CASES"

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = "0" ]
