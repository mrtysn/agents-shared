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
exit 0
