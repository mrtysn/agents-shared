#!/bin/bash
# DESC: Run the show-rule-at-action PreToolUse hook against its case file

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../show-rule-at-action.sh"
CASES="$HERE/show-rule-at-action-cases.tsv"

VERBOSE=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) echo "usage: run-show-rule-at-action.sh [-v] [case-file]"; exit 0 ;;
        *) CASES=$1; shift ;;
    esac
done

# The hook keeps its once-per-session markers under $CLAUDE_CONFIG_DIR; give the run its own.
STATE_ROOT=$(mktemp -d)
export CLAUDE_CONFIG_DIR=$STATE_ROOT
trap '[ -n "${STATE_ROOT:-}" ] && rm -rf "$STATE_ROOT"' EXIT

total=0
failed=0

# run_hook <payload>: sets CODE and OUT
run_hook() {
    CODE=0
    OUT=$(printf '%s' "$1" | "$HOOK" 2>/dev/null) || CODE=$?
}

while IFS=$'\t' read -r verdict tool input agent; do
    case "${verdict-}" in
        ''|'#'*) continue ;;
    esac
    total=$((total + 1))
    payload=$(jq -cn --arg t "$tool" --arg s "case-$total" --arg a "${agent-}" --argjson i "$input" \
        '{tool_name: $t, session_id: $s, tool_input: $i} + (if $a == "" then {} else {agent_id: $a} end)')

    if [ "$verdict" = each-agent ]; then
        # A note-once row: the main conversation and a sub-agent of the same session each get
        # the text once, and a repeat from either is quiet.
        sub=$(printf '%s' "$payload" | jq -c '. + {agent_id: "sub-1"}')
        run_hook "$payload"; main_first=$OUT
        run_hook "$sub"; sub_first=$OUT
        run_hook "$sub"; sub_again=$OUT
        run_hook "$payload"; main_again=$OUT
        if [ -n "$main_first" ] && [ -n "$sub_first" ] && [ -z "$sub_again" ] && [ -z "$main_again" ]; then
            [ "$VERBOSE" = 1 ] && printf 'ok    %-6s %-16s %s\n' "$verdict" "$tool" "$input"
        else
            failed=$((failed + 1))
            printf 'FAIL  each-agent: main first=%s sub first=%s sub again=%s main again=%s: %s %s\n' \
                "${main_first:+text}" "${sub_first:+text}" "${sub_again:+text}" "${main_again:+text}" "$tool" "$input"
        fi
        continue
    fi

    if [ "$verdict" = each-message ]; then
        # A deny-each row: the full-text row spends itself on the first message, and every
        # new message in the same session is still refused once; a repeat of it passes.
        other=$(printf '%s' "$payload" | jq -c '.tool_input.message = "a different message"')
        run_hook "$payload"; c1=$CODE
        run_hook "$other"; c2=$CODE
        run_hook "$other"; c3=$CODE
        run_hook "$payload"; c4=$CODE
        if [ "$c1" = 2 ] && [ "$c2" = 2 ] && [ "$c3" = 0 ] && [ "$c4" = 0 ]; then
            [ "$VERBOSE" = 1 ] && printf 'ok    %-6s %-16s %s\n' "$verdict" "$tool" "$input"
        else
            failed=$((failed + 1))
            printf 'FAIL  each-message: codes %s %s %s %s: %s %s\n' "$c1" "$c2" "$c3" "$c4" "$tool" "$input"
        fi
        continue
    fi

    run_hook "$payload"
    first_code=$CODE
    first_out=$OUT
    run_hook "$payload"
    second_code=$CODE
    second_out=$OUT

    ok=0
    case "$verdict" in
        pass)  [ "$first_code" = 0 ] && [ -z "$first_out" ] && [ "$second_code" = 0 ] && [ -z "$second_out" ] && ok=1 ;;
        block) [ "$first_code" = 2 ] && [ "$second_code" = 0 ] && [ -z "$second_out" ] && ok=1 ;;
        note)  [ "$first_code" = 0 ] && printf '%s' "$first_out" | jq -e '.hookSpecificOutput.additionalContext | length > 0' >/dev/null 2>&1 \
                   && [ "$second_code" = 0 ] && [ -z "$second_out" ] && ok=1 ;;
        *) echo "unknown verdict '$verdict'" >&2; exit 1 ;;
    esac

    if [ "$ok" = 1 ]; then
        [ "$VERBOSE" = 1 ] && printf 'ok    %-6s %-16s %s\n' "$verdict" "$tool" "$input"
    else
        failed=$((failed + 1))
        printf 'FAIL  want %s, got first=%s second=%s: %s %s\n' "$verdict" "$first_code" "$second_code" "$tool" "$input"
    fi
done < "$CASES"

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = 0 ]
