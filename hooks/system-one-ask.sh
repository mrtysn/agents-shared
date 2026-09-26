#!/bin/bash
# PreToolUse hook (matcher AskUserQuestion): reads a question the agent is
# about to ask the user through the system-one decision model, the check
# named 3.2 in the use-case survey and covered by asking-for-decisions.md,
# working-style.md and stated-desires.md.
#
# One model call per question in tool_input.questions (measured better than
# one call over the whole ask, design doc section 11a), the calls run in
# parallel so a four-question ask costs about one call's wall time plus the
# model time. State per question: "question:" then its header and text, the
# multiSelect flag and the options (descriptions cut to
# state.description_chars), then a "recent:" block with the session's last
# state.recent_prompts typed user prompts and the last assistant text
# excerpt (state.recent_chars characters each), read from transcript_path's
# tail, bounded and best-effort. Questions, wording and thresholds all come
# from hooks/system-one-ask-questions.json, the single source shared with
# scripts/system-one-measure.py --hook ask. Each shadow-log line carries
# q_index and q_count so a multi-question call can be rebuilt from the log.
#
# Modes (SYSTEM_ONE_ASK_MODE, falling back to SYSTEM_ONE_MODE, default shadow):
#   shadow / show   log one verdict per question to shadow/ask/<session_id>.jsonl,
#                   emit nothing, exit 0 (show is identical here; the distinct
#                   name is for status/statusline/app to say the user opted in)
#   act             return permissionDecision: deny only when EVERY question in
#                   the call fires (answered_in_context or routine_default at
#                   or above the file's gate) and NONE of them reaches
#                   naming_or_irreversible_min: a naming or irreversible ask is
#                   always legitimate per asking-for-decisions.md and is never
#                   denied, and a batch with one legitimate question is not
#                   denied for its routine siblings (the rule says to batch)
# Fails open on everything: no config, no wrapper, no questions file, server
# down, timeout, bad JSON, a transcript that cannot be read, any question
# whose call returned nothing. Budget ~400 ms for a four-question call.
#
# Shadow log excerpt rule (system-one wrapper default, no --keep-state): a
# sha256 plus the first 80 characters of the state, never the full text.
#
# Bash 3.2, like the hooks beside it.

set -u

INPUT=$(cat)
QUESTIONS_INPUT=$(printf '%s' "$INPUT" | jq -c '.tool_input.questions // empty | select(type == "array")' 2>/dev/null)
[ -n "$QUESTIONS_INPUT" ] && [ "$QUESTIONS_INPUT" != "[]" ] || exit 0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WRAPPER="$HERE/../scripts/system-one"
[ -x "$WRAPPER" ] || exit 0

QUESTIONS_FILE="$HERE/system-one-ask-questions.json"
# One jq call for every scalar/object this hook needs from the questions
# file (unit-separated fields), instead of one read per field: each shell
# process spawned here is latency the budget cannot spare.
CFG=$(jq -j '
    (.questions // empty | tojson) + "\u001f" +
    ((.gate // {}) | tojson) + "\u001f" +
    ((.naming_or_irreversible_min // 0.50) | tostring) + "\u001f" +
    ((.state.recent_chars // 150) | tostring) + "\u001f" +
    ((.state.recent_prompts // 3) | tostring) + "\u001f" +
    ((.state.description_chars // 50) | tostring) + "\u001f" +
    ((.wording // {}) | tojson)
' "$QUESTIONS_FILE" 2>/dev/null)
[ -n "$CFG" ] || exit 0
IFS=$'\x1f' read -r QUESTIONS GATE NAMING_MIN RECENT_CHARS RECENT_PROMPTS DESC_CHARS WORDING <<<"$CFG"
[ -n "$QUESTIONS" ] || exit 0

# Config: sourced in a subshell, only the keys this hook reads come back, so
# an exported SYSTEM_ONE_* the caller set (STATE_DIR, PORT) is never
# re-assigned here and reaches the wrapper intact: environment wins over the
# file, per key (see hooks/system-one-bash.sh for the full reasoning).
CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-one.local.sh"
[ -r "$CONFIG" ] || exit 0
PRE_MODE="${SYSTEM_ONE_ASK_MODE:-${SYSTEM_ONE_MODE:-}}"
PRE_MODEL="${SYSTEM_ONE_ASK_MODEL:-}"
CFG=$( ( . "$CONFIG" 2>/dev/null || exit 1
    printf '%s\037%s\037%s' "${SYSTEM_ONE_ASK_MODE:-}" "${SYSTEM_ONE_MODE:-}" "${SYSTEM_ONE_ASK_MODEL:-}" ) ) || exit 0
IFS=$'\037' read -r CFG_ASK_MODE CFG_MODE CFG_MODEL <<<"$CFG"
MODE="${PRE_MODE:-${CFG_ASK_MODE:-${CFG_MODE:-shadow}}}"
MODEL="${PRE_MODEL:-${CFG_MODEL:-english}}"

# Best-effort "recent:" block: the transcript's last RECENT_PROMPTS typed user
# prompts (string content, or an all-text content array; a tool_result entry
# is neither and is skipped by construction; harness markers, skill
# expansions and interrupt notices are not typed prompts and are skipped
# too, the same rule scripts/usage-survey.py --dump-asks applies) and the
# last assistant text message, each cut to its last RECENT_CHARS characters.
# Bounded read (last 64 KiB), one line at a time (fromjson?) because the
# tail's first line is usually cut mid-JSON.
RECENT=""
if [ "$RECENT_CHARS" != 0 ] && [ "$RECENT_PROMPTS" != 0 ] && [ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ]; then
    RECENT=$(tail -c 65536 "$TRANSCRIPT" 2>/dev/null | jq -Rrn --argjson n "$RECENT_CHARS" --argjson p "$RECENT_PROMPTS" '
        def is_prompt: .type == "user" and
            ((.message.content | type) == "string" or
             ((.message.content | type) == "array" and (.message.content | length) > 0
              and (.message.content | all(.type == "text"))));
        def ptext: if (.message.content | type) == "string" then .message.content
                   else ([.message.content[] | select(.type == "text") | .text] | join(" ")) end;
        def typed: (. | ltrimstr(" ")) as $t
                   | ($t != "") and ($t | startswith("<") | not)
                     and ($t | test("^(\\[Request interrupted|Base directory for this skill:|This session is being continued)") | not);
        [inputs | fromjson?] as $es
        | ($es | map(select(is_prompt) | ptext) | map(select(typed)) | .[-$p:]) as $prompts
        | ($es | map(select(.type == "assistant"))
             | map(.message.content[]? | select(.type == "text") | .text) | last) as $lasta
        | ([$prompts[] | "user: " + .[-$n:]]
           + (if ($lasta // "") == "" then [] else ["assistant: " + ($lasta[-$n:])] end))
          | join("\n")' 2>/dev/null)
fi

# One state per question: "question:" then its header and text, the
# multiSelect flag and the options. Descriptions are cut to DESC_CHARS so a
# question with several verbose options still fits the encoder's state
# budget and the recent: block is not pushed out; the label alone (never
# cut) is what a routine or naming judgment actually turns on. One jq call
# builds all of them: the count, then the states, unit-separated.
STATES=$(printf '%s' "$QUESTIONS_INPUT" | jq -j --argjson d "$DESC_CHARS" '
    [.[] | select(type == "object") | (
        ["question:",
         (.header // "") + ": " + (.question // ""),
         "multiSelect: " + ((.multiSelect // false) | tostring),
         "options: " + ([.options[]? | (.label // "") + " (" + ((.description // "")[0:$d]) + ")"] | join("; "))]
        | join("\n"))]
    | (length | tostring) + "\u001f" + join("\u001f")' 2>/dev/null)
[ -n "$STATES" ] || exit 0
COUNT=${STATES%%$'\x1f'*}
STATES=${STATES#*$'\x1f'}
case "$COUNT" in ''|*[!0-9]*|0) exit 0 ;; esac

TMP=$(mktemp -d "${TMPDIR:-/tmp}/system-one-ask.XXXXXX" 2>/dev/null) || exit 0
trap 'rm -rf -- "$TMP"' EXIT

# Launch every question's call at once; the wrapper owns the request, the
# fail-open exit and the shadow-log line. Each response lands in its own
# file, empty when that call failed.
# Word-split on the unit separator only, with globbing off: a state is
# free text and may carry * or ?.
N=0
OLDIFS=$IFS
IFS=$'\x1f'
set -f
for STATE_Q in $STATES; do
    IFS=$OLDIFS
    set +f
    N=$((N + 1))
    STATE="$STATE_Q"
    if [ -n "$RECENT" ]; then
        STATE="$STATE
recent:
$RECENT"
    fi
    jq -cn --arg s "$STATE" --argjson q "$QUESTIONS" '{state: $s, questions: $q}' 2>/dev/null \
        | "$WRAPPER" ask --hook ask --session "$SESSION" --gate "$GATE" --model "$MODEL" --fail-open \
            --extra "{\"q_index\": $N, \"q_count\": $COUNT}" >"$TMP/$N.json" 2>/dev/null &
    IFS=$'\x1f'
    set -f
done
IFS=$OLDIFS
set +f
wait
[ "$MODE" = act ] || exit 0

# Act: deny only when every question fired and none is a naming or
# irreversible ask. A question whose call returned nothing cannot fire, so
# a partial failure fails open with the rest.
MIN_PROB=""
TOP_Q=""
i=1
while [ "$i" -le "$N" ]; do
    RESP=$(cat "$TMP/$i.json" 2>/dev/null)
    [ -n "$RESP" ] || exit 0
    NAMING=$(printf '%s' "$RESP" | jq -r '.answers.naming_or_irreversible.noul // 0' 2>/dev/null)
    awk -v v="${NAMING:-0}" -v t="$NAMING_MIN" 'BEGIN { exit !(v+0 >= t+0) }' && exit 0
    # The highest-probability fired question (answered_in_context or
    # routine_default only: the gate names no other question).
    TOP=$(printf '%s' "$RESP" | jq -r '(.fired // []) | max_by(.value) // empty | "\(.q) \(.value)"' 2>/dev/null)
    [ -n "$TOP" ] || exit 0
    Q=${TOP% *}
    PROB=${TOP#* }
    if [ -z "$MIN_PROB" ] || awk -v a="$PROB" -v b="$MIN_PROB" 'BEGIN { exit !(a+0 < b+0) }'; then
        MIN_PROB=$PROB
        TOP_Q=$Q
    fi
    i=$((i + 1))
done
[ -n "$TOP_Q" ] || exit 0

# Reason: the per-question wording for a single question; for a batch, the
# "all" template with the weakest question's probability.
KEY=$TOP_Q
[ "$N" -gt 1 ] && KEY=all
REASON=$(printf '%s' "$WORDING" | jq -r --arg k "$KEY" --argjson p "$MIN_PROB" --argjson n "$N" '
    (.[$k] // "") as $tmpl
    | if $tmpl == "" then "" else ($tmpl | sub("%\\.2f"; ($p * 100 | round / 100 | tostring)) | sub("%d"; ($n | tostring))) end' 2>/dev/null)
[ -n "$REASON" ] || exit 0
jq -cn --arg r "$REASON" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
exit 0
