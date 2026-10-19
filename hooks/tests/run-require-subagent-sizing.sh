#!/bin/bash
# DESC: Run the require-subagent-sizing PreToolUse hook against its case file

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../require-subagent-sizing.sh"
CASES="$HERE/require-subagent-sizing-cases.tsv"

# The hook keeps its once-per-session markers under $XDG_CACHE_HOME; give the run its own.
SEEN_ROOT=$(mktemp -d)
export XDG_CACHE_HOME=$SEEN_ROOT
trap '[ -n "${SEEN_ROOT:-}" ] && rm -rf "$SEEN_ROOT"' EXIT

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
    if [ "$verdict" = once ]; then
        # The call is refused once (a first call that is also a build-verb opus spawn), the same call a second time passes.
        total=$((total + 1))
        payload=$(jq -cn --argjson i "$input" --arg s "once-$total" '{tool_name: "Agent", session_id: $s, tool_input: $i}')
        first=0; printf '%s' "$payload" | "$HOOK" >/dev/null 2>&1 || first=$?
        second=0; printf '%s' "$payload" | "$HOOK" >/dev/null 2>&1 || second=$?
        # A sub-agent shares the session_id: its own first call is refused once too.
        sub_payload=$(printf '%s' "$payload" | jq -c '. + {agent_id: "sub-1"}')
        sub_first=0; printf '%s' "$sub_payload" | "$HOOK" >/dev/null 2>&1 || sub_first=$?
        sub_second=0; printf '%s' "$sub_payload" | "$HOOK" >/dev/null 2>&1 || sub_second=$?
        if [ "$first" = 2 ] && [ "$second" = 0 ] && [ "$sub_first" = 2 ] && [ "$sub_second" = 0 ]; then
            [ "$VERBOSE" = "1" ] && printf 'ok    %-13s %s\n' "$verdict" "$input"
        else
            failed=$((failed + 1))
            printf 'FAIL  once: want first 2 then 0, got %s then %s: %s\n' "$first" "$second" "$input"
        fi
        continue
    fi
    if [ "$verdict" = context-once ]; then
        # A session's first call passes carrying the sizing table as additionalContext; the repeat carries none.
        total=$((total + 1))
        payload=$(jq -cn --argjson i "$input" --arg s "context-$total" '{tool_name: "Agent", session_id: $s, tool_input: $i}')
        first=0; first_out=$(printf '%s' "$payload" | "$HOOK" 2>/dev/null) || first=$?
        second=0; second_out=$(printf '%s' "$payload" | "$HOOK" 2>/dev/null) || second=$?
        first_ctx=$(printf '%s' "$first_out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
        second_ctx=$(printf '%s' "$second_out" | jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null)
        if [ "$first" = 0 ] && [ "$second" = 0 ] && printf '%s' "$first_ctx" | grep -q 'Hand back past' && [ -z "$second_ctx" ]; then
            [ "$VERBOSE" = "1" ] && printf 'ok    %-13s %s\n' "$verdict" "$input"
        else
            failed=$((failed + 1))
            printf 'FAIL  context-once: want exit 0 with the table on the first call only, got %s then %s: %s\n' "$first" "$second" "$input"
        fi
        continue
    fi
    if [ "$verdict" = once-after-first ] || [ "$verdict" = pass-after-first ]; then
        # Use up the session's first-call refusal with a harmless call, then judge the call itself.
        total=$((total + 1))
        sid="after-first-$total"
        warm=$(jq -cn --arg s "$sid" '{tool_name: "Agent", session_id: $s, tool_input: {description: "x", prompt: "x", model: "haiku", effort: "low"}}')
        printf '%s' "$warm" | "$HOOK" >/dev/null 2>&1 || true
        payload=$(jq -cn --argjson i "$input" --arg s "$sid" '{tool_name: "Agent", session_id: $s, tool_input: $i}')
        first=0; printf '%s' "$payload" | "$HOOK" >/dev/null 2>&1 || first=$?
        second=0; printf '%s' "$payload" | "$HOOK" >/dev/null 2>&1 || second=$?
        want_first=2; [ "$verdict" = pass-after-first ] && want_first=0
        if [ "$first" = "$want_first" ] && [ "$second" = 0 ]; then
            [ "$VERBOSE" = "1" ] && printf 'ok    %-16s %s\n' "$verdict" "$input"
        else
            failed=$((failed + 1))
            printf 'FAIL  %s: want first %s then 0, got %s then %s: %s\n' "$verdict" "$want_first" "$first" "$second" "$input"
        fi
        continue
    fi
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

# The refusal text carries the guide's size limits; a renamed heading would drop them silently.
total=$((total + 1))
refusal=$(printf '%s' '{"tool_name":"Agent","tool_input":{"description":"x","prompt":"x"}}' | "$HOOK" 2>&1 >/dev/null || true)
if printf '%s' "$refusal" | grep -q 'Hand back past' && ! printf '%s' "$refusal" | grep -q 'size limits not found'; then
    [ "$VERBOSE" = "1" ] && echo "ok    refusal prints the size limits"
else
    failed=$((failed + 1))
    echo "FAIL  refusal does not print the size limits from the guide"
fi

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = "0" ]
