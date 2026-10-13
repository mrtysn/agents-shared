#!/bin/bash
# Stop hook, log-only: when the agent's final reply ends by asking for a
# go-ahead in prose ("say the word and I'll build it", "want me to go ahead?")
# instead of using AskUserQuestion, append one JSON line to
# $LOG_DIR/<session_id>.jsonl. It never blocks and prints nothing.
#
# Covers asking-for-decisions.md ("never bury the ask in prose"). To judge it,
# join each logged row with the user's next typed message in the transcript:
# a bare "proceed" or "go" after it is a true match, anything else is a false
# one. LOG_DIR defaults to ${XDG_STATE_HOME:-~/.local/state}/log-buried-go-ahead.
set -u
INPUT=$(cat)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
[ -n "$SESSION" ] || exit 0

FULL_MSG=$(tail -c 131072 "$TRANSCRIPT" 2>/dev/null | jq -Rrn '
    [inputs | fromjson? | select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text]
    | last // empty' 2>/dev/null)
[ -n "$FULL_MSG" ] || exit 0

LEN=${#FULL_MSG}
START=$(( LEN > 400 ? LEN - 400 : 0 ))
TAIL=${FULL_MSG:$START}
PATTERN="say the word|want me to|do you want me to|would you like me to|shall i |should i (go|proceed|build|run|start|do)|let me know if you.?d like|tell me to (go|proceed|implement|build)|if you want,? i.?(ll|will)|ready to proceed when you"
PHRASE=$(printf '%s' "$TAIL" | grep -oiE "$PATTERN" | tail -1)
[ -n "$PHRASE" ] || exit 0

LOG_DIR="${LOG_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/log-buried-go-ahead}"
mkdir -p "$LOG_DIR" 2>/dev/null || exit 0
jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg s "$SESSION" --arg p "$PHRASE" --arg t "$TAIL" \
    '{ts: $ts, session_id: $s, phrase: $p, tail: $t}' >> "$LOG_DIR/$SESSION.jsonl" 2>/dev/null

# Once REVIEW_AT_ROWS rows are logged, run the review script in the background
# and post one notification with its verdict, then never again (.review-sent).
# A "not enough data" verdict leaves the marker unset, so a later row retries.
# REVIEW_SCRIPT and NOTIFY_CMD are test seams.
SENT="$LOG_DIR/.review-sent"
if [ ! -e "$SENT" ]; then
    ROWS=$(cat "$LOG_DIR"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')
    if [ "${ROWS:-0}" -ge "${REVIEW_AT_ROWS:-20}" ] && mkdir "$SENT.lock" 2>/dev/null; then
        HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
        (
            OUT=$("${REVIEW_SCRIPT:-$HERE/../scripts/review-buried-go-ahead-log.py}" --log-dir "$LOG_DIR" 2>&1)
            if ! printf '%s' "$OUT" | grep -q "not enough data"; then
                RATE=$(printf '%s' "$OUT" | grep -o 'true-match rate: [0-9.]*' | head -1)
                VERDICT=$(printf '%s' "$OUT" | grep -o 'verdict: .*' | head -1 | sed 's/ (.*//')
                ${NOTIFY_CMD:-"$HOME/bin/notify"} go-ahead-hook 0 "Go-ahead requests buried in prose: ${RATE:-no rate}; ${VERDICT:-no verdict}" >/dev/null 2>&1
                touch "$SENT"
            fi
            rmdir "$SENT.lock" 2>/dev/null
        ) >/dev/null 2>&1 &
    fi
fi
exit 0
