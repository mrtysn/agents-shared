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
    case "$verdict" in
        pass) want=0 ;;
        block) want=2 ;;
        *) echo "unknown verdict '$verdict'" >&2; exit 1 ;;
    esac

    payload=$(jq -cn --argjson i "$input" '{tool_name: "Agent", tool_input: $i}')
    got=0
    reason=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?

    total=$((total + 1))
    if [ "$got" = "$want" ]; then
        [ "$VERBOSE" = "1" ] && printf 'ok    %-6s %s\n' "$verdict" "$input"
    else
        failed=$((failed + 1))
        printf 'FAIL  want %s, got %s: %s\n' "$want" "$got" "$input"
        printf '      %s\n' "$(printf '%s' "$reason" | head -1)"
    fi
done < "$CASES"

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = "0" ]
