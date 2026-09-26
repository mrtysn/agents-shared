#!/bin/bash
# Stop hook: reads the assistant's final message through the system-one
# decision model for padding and answer-shape, the check named 3.4 in the
# use-case survey and covered by answer-shape.md and communication-style.md.
#
# State: the last assistant text message from transcript_path's tail (tool
# calls stripped), first state.message_chars characters (default 1500;
# hooks/system-one-stop-questions.json), plus a line
# "length_chars: N  tables: N  headers: N  bullets: N" computed with awk/grep
# over the full message (not just the truncated excerpt, so the counts are
# honest even when the message is cut). Questions, pre-gate, gate thresholds
# and wording all come from that file, the single source shared with
# scripts/system-one-measure.py --hook stop.
#
# One call, two questions (needless_table + overlong), on
# SYSTEM_ONE_STOP_MODEL (default english; set to a fine-tuned checkpoint's
# friendly name to score it against this same pair). Gated by
# pregate.max_chars: a message under that length with no table is never
# padded by answer-shape.md's own definition, so the call is skipped entirely
# and nothing is logged for it.
#
# Modes (SYSTEM_ONE_STOP_MODE, falling back to SYSTEM_ONE_MODE, default shadow):
#   shadow / show   log the verdict to shadow/stop/<session_id>.jsonl, emit
#                   nothing, exit 0 (show is identical here; the distinct name
#                   is for status/statusline/app to say the user opted in)
#   act             when needless_table reaches gate.needless_table_min (or
#                   overlong reaches gate.overlong_min, when the file sets one),
#                   return decision: block with the file's wording -- but only
#                   when stop_hook_active is false, so a blocked turn's revision
#                   is never blocked again (an infinite loop the hooks docs warn
#                   against explicitly). Never fires when the pre-gate skipped
#                   the call.
# Fails open on everything: no config, no wrapper, no questions file, no
# transcript, server down, timeout, bad JSON. Must stay under ~500 ms; the
# transcript read is bounded (tail -c) and best-effort.
#
# Bash 3.2, like the hooks beside it.

set -u

INPUT=$(cat)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
STOP_ACTIVE=$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WRAPPER="$HERE/../scripts/system-one"
[ -x "$WRAPPER" ] || exit 0

QUESTIONS_FILE="$HERE/system-one-stop-questions.json"
QUESTIONS=$(jq -c '.questions // empty' "$QUESTIONS_FILE" 2>/dev/null)
[ -n "$QUESTIONS" ] || exit 0
[ "$QUESTIONS" != "{}" ] || exit 0
MSG_CHARS=$(jq -r '.state.message_chars // 1500' "$QUESTIONS_FILE" 2>/dev/null)
PREGATE_CHARS=$(jq -r '.pregate.max_chars // 0' "$QUESTIONS_FILE" 2>/dev/null)
GATE_OVERLONG=$(jq -r '.gate.overlong_min // 2' "$QUESTIONS_FILE" 2>/dev/null)
GATE_TABLE=$(jq -r '.gate.needless_table_min // 2' "$QUESTIONS_FILE" 2>/dev/null)
WORDING=$(jq -r '.wording // ""' "$QUESTIONS_FILE" 2>/dev/null)

# Config: sourced in a subshell, only the keys this hook reads come back, so
# an exported SYSTEM_ONE_* the caller set (STATE_DIR, PORT) is never
# re-assigned here and reaches the wrapper intact: environment wins over the
# file, per key (see hooks/system-one-bash.sh for the full reasoning).
CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-one.local.sh"
[ -r "$CONFIG" ] || exit 0
PRE_MODE="${SYSTEM_ONE_STOP_MODE:-${SYSTEM_ONE_MODE:-}}"
PRE_MODEL="${SYSTEM_ONE_STOP_MODEL:-}"
CFG=$( ( . "$CONFIG" 2>/dev/null || exit 1
    printf '%s\037%s\037%s' "${SYSTEM_ONE_STOP_MODE:-}" "${SYSTEM_ONE_MODE:-}" "${SYSTEM_ONE_STOP_MODEL:-}" ) ) || exit 0
IFS=$'\037' read -r CFG_STOP_MODE CFG_MODE CFG_MODEL <<<"$CFG"
MODE="${PRE_MODE:-${CFG_STOP_MODE:-${CFG_MODE:-shadow}}}"
MODEL="${PRE_MODEL:-${CFG_MODEL:-english}}"

# Last assistant text message: the transcript's tail (bounded read), the last
# line whose type is "assistant" with a text content block. Tool calls (type
# tool_use / tool_result) are not text and are skipped by construction. The
# tail's first line is usually cut mid-JSON (a tool result can be hundreds of
# KB on its own), so lines are parsed one at a time with fromjson? and a
# broken one is dropped instead of failing the whole read, which is what a
# slurp (-s) did: any partial line and the hook saw no message at all.
FULL_MSG=$(tail -c 131072 "$TRANSCRIPT" 2>/dev/null | jq -Rrn '
    [inputs | fromjson? | select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text]
    | last // empty' 2>/dev/null)
[ -n "$FULL_MSG" ] || exit 0

LEN=${#FULL_MSG}
TABLES=$(printf '%s\n' "$FULL_MSG" | grep -cE '^\s*\|.*\|\s*$' 2>/dev/null); TABLES=${TABLES:-0}
HEADERS=$(printf '%s\n' "$FULL_MSG" | grep -cE '^#{1,6}[[:space:]]' 2>/dev/null); HEADERS=${HEADERS:-0}
BULLETS=$(printf '%s\n' "$FULL_MSG" | grep -cE '^\s*([-*]|[0-9]+\.)[[:space:]]' 2>/dev/null); BULLETS=${BULLETS:-0}

# Bash substring, not cut -c: cut works per line, so it would trim every line
# of a multi-line message to MSG_CHARS instead of taking the message's head.
EXCERPT=${FULL_MSG:0:$MSG_CHARS}
STATE="assistant message:
$EXCERPT
length_chars: $LEN  tables: $TABLES  headers: $HEADERS  bullets: $BULLETS"

# Deterministic pre-gate: a short message with no table is never padded by
# answer-shape.md's own definition, so the call is skipped entirely and logs
# nothing (pregate.max_chars; 0 disables it).
if [ "$PREGATE_CHARS" -gt 0 ] 2>/dev/null && [ "$LEN" -lt "$PREGATE_CHARS" ] && [ "$TABLES" -eq 0 ]; then
    exit 0
fi

RESP=$(jq -cn --arg s "$STATE" --argjson q "$QUESTIONS" '{state: $s, questions: $q}' 2>/dev/null \
    | "$WRAPPER" ask --hook stop --session "$SESSION" --model "$MODEL" \
        --gate "{\"needless_table\": $GATE_TABLE, \"overlong\": $GATE_OVERLONG}" \
        --keep-state --fail-open 2>/dev/null)

[ "$MODE" = act ] || exit 0
[ "$STOP_ACTIVE" = false ] || exit 0   # never re-block a turn already revising because of us
[ -n "$RESP" ] || exit 0

OVERLONG=$(printf '%s' "$RESP" | jq -r '.answers.overlong.noul // 0' 2>/dev/null)
TABLE=$(printf '%s' "$RESP" | jq -r '.answers.needless_table.noul // 0' 2>/dev/null)
[ -n "$OVERLONG" ] && [ -n "$TABLE" ] || exit 0

FIRE=0
awk -v v="$TABLE" -v t="$GATE_TABLE" 'BEGIN { exit !(v+0 >= t+0) }' && FIRE=1
awk -v v="$OVERLONG" -v t="$GATE_OVERLONG" 'BEGIN { exit !(v+0 >= t+0) }' && FIRE=1
[ "$FIRE" = 1 ] || exit 0

# Substitute the two %.2f placeholders in order (needless_table, then
# overlong): jq's sub() with the "g" flag would replace both with the same
# value, so this walks the template's %.2f-split pieces instead.
REASON=$(jq -cn --arg t "$WORDING" --argjson a "$TABLE" --argjson b "$OVERLONG" '
    ($t | split("%.2f")) as $parts
    | if ($parts | length) >= 3
      then $parts[0] + (($a * 100 | round) / 100 | tostring) + $parts[1] + (($b * 100 | round) / 100 | tostring) + ($parts[2:] | join("%.2f"))
      else $t end' 2>/dev/null | jq -r . 2>/dev/null)
[ -n "$REASON" ] || REASON="system-one: this answer reads as padded and does not lead with the answer. Rewrite: lead with the answer, plain sentences, no table unless comparing options."
jq -cn --arg r "$REASON" '{decision: "block", reason: $r}'
exit 0
