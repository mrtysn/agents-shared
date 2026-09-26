#!/bin/bash
# PreToolUse (Bash) hook: semantic destructiveness check through the system-one decision model.
#
# The deterministic guards beside this (block-tree-discard, require-absolute-rm,
# ssh-request-guard) catch known shapes exactly. This one scores the shapes they
# do not enumerate: kill by pattern, docker prune, launchctl of something not
# ours, dd, truncate, force-push, obfuscated rm. Design and measurements:
# notebook/2026-09-24-system-one-decision-model-integration.md, section 3.1.
#
# State: "cwd: <cwd>\ncommand:\n<command>", with each heredoc body cut to its
# first N lines plus a "<heredoc: K more lines>" marker by
# system-one-bash-state.awk (N = state.heredoc_keep in the questions file; the
# body text drove false asks on ordinary file edits). Questions, gate
# thresholds and N all come from system-one-bash-questions.json beside this
# file, the single source shared with scripts/system-one-measure.py, so the
# hook and the harness build an identical request. would_act = any gate
# question at or above its threshold (SYSTEM_ONE_BASH_ASK_<QUESTION> in the
# config or environment overrides a threshold; SYSTEM_ONE_BASH_ASK is the
# fallback for a gate question with no threshold in the file).
#
# Modes (SYSTEM_ONE_BASH_MODE, falling back to SYSTEM_ONE_MODE, in
# system-one.local.sh, default shadow):
#   shadow  log the verdict to shadow/bash/<session_id>.jsonl, emit nothing, exit 0
#   show    identical to shadow here (no permission output ever); the distinct
#           name is for status and the statusline/app to say the user opted
#           in to seeing verdicts, not for this hook to branch on
#   act     permissionDecision "ask" naming the question that fired; never deny
# Fails open on everything: no config, no wrapper, no questions file, server
# down, timeout, bad JSON. `system-one ask --fail-open` owns the curl and its
# 1.5 s cap, so the happy path is one model call plus jq and a dead server
# costs one refused connection.
#
# Bash 3.2, like the hooks beside it.

set -u

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$COMMAND" ] && exit 0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
# Logged on the verdict row so hooks/system-one-bash-post.sh (PostToolUse /
# PostToolUseFailure, same tool_use_id in its input) joins its outcome row to
# exactly this call, not to another row with the same command text.
TOOL_USE_ID=$(printf '%s' "$INPUT" | jq -r '.tool_use_id // ""' 2>/dev/null)
EXTRA=$(jq -cn --arg t "$TOOL_USE_ID" 'if $t == "" then {} else {tool_use_id: $t} end' 2>/dev/null)
[ -n "$EXTRA" ] || EXTRA='{}'

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WRAPPER="$HERE/../scripts/system-one"
[ -x "$WRAPPER" ] || exit 0

QUESTIONS_FILE="$HERE/system-one-bash-questions.json"
STATE_AWK="$HERE/system-one-bash-state.awk"
QUESTIONS=$(jq -c '.questions // empty' "$QUESTIONS_FILE" 2>/dev/null)
[ -n "$QUESTIONS" ] || exit 0
GATE=$(jq -c '.gate // {}' "$QUESTIONS_FILE" 2>/dev/null)
[ -n "$GATE" ] || exit 0
KEEP=$(jq -r '.state.heredoc_keep // 0' "$QUESTIONS_FILE" 2>/dev/null)

# Config: file, then environment wins (the test runner forces shadow mode this
# way). The file is sourced in a subshell and only the keys this hook reads
# come back: sourcing it here would re-assign any SYSTEM_ONE_* variable that
# arrived exported (SYSTEM_ONE_STATE_DIR, SYSTEM_ONE_PORT from a runner or a
# caller), and bash keeps a re-assigned import exported, so the wrapper would
# then see the file's value instead of the caller's -- the opposite of the
# documented precedence. A key the file leaves unset comes back as the
# environment's value (the subshell inherits it), so env-or-file per key.
CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-one.local.sh"
[ -r "$CONFIG" ] || exit 0
PRE_MODE="${SYSTEM_ONE_BASH_MODE:-${SYSTEM_ONE_MODE:-}}"
PRE_ASK="${SYSTEM_ONE_BASH_ASK:-}"
PRE_ASK_FP="${SYSTEM_ONE_BASH_ASK_FOREIGN_PROCESS:-}"
PRE_ASK_IRR="${SYSTEM_ONE_BASH_ASK_IRREVERSIBLE:-}"
PRE_ASK_LM="${SYSTEM_ONE_BASH_ASK_LEAVES_MACHINE:-}"
PRE_ASK_NI="${SYSTEM_ONE_BASH_ASK_NETWORK_INSTALL:-}"
PRE_MODEL="${SYSTEM_ONE_BASH_MODEL:-}"
CFG=$( ( . "$CONFIG" 2>/dev/null || exit 1
    printf '%s\037%s\037%s\037%s\037%s\037%s\037%s\037%s' \
        "${SYSTEM_ONE_BASH_MODE:-}" "${SYSTEM_ONE_MODE:-}" "${SYSTEM_ONE_BASH_ASK:-}" \
        "${SYSTEM_ONE_BASH_ASK_FOREIGN_PROCESS:-}" "${SYSTEM_ONE_BASH_ASK_IRREVERSIBLE:-}" \
        "${SYSTEM_ONE_BASH_ASK_LEAVES_MACHINE:-}" "${SYSTEM_ONE_BASH_ASK_NETWORK_INSTALL:-}" \
        "${SYSTEM_ONE_BASH_MODEL:-}" ) ) || exit 0
IFS=$'\037' read -r CFG_BASH_MODE CFG_MODE CFG_ASK CFG_ASK_FP CFG_ASK_IRR CFG_ASK_LM CFG_ASK_NI CFG_MODEL <<<"$CFG"
SYSTEM_ONE_BASH_ASK="${PRE_ASK:-$CFG_ASK}"
SYSTEM_ONE_BASH_ASK_FOREIGN_PROCESS="${PRE_ASK_FP:-$CFG_ASK_FP}"
SYSTEM_ONE_BASH_ASK_IRREVERSIBLE="${PRE_ASK_IRR:-$CFG_ASK_IRR}"
SYSTEM_ONE_BASH_ASK_LEAVES_MACHINE="${PRE_ASK_LM:-$CFG_ASK_LM}"
SYSTEM_ONE_BASH_ASK_NETWORK_INSTALL="${PRE_ASK_NI:-$CFG_ASK_NI}"
# Per-hook mode (SYSTEM_ONE_BASH_MODE) wins over the shared SYSTEM_ONE_MODE;
# an environment value (PRE_MODE, the test runner's override) wins over both.
MODE="${PRE_MODE:-${CFG_BASH_MODE:-${CFG_MODE:-shadow}}}"
THRESHOLD="${SYSTEM_ONE_BASH_ASK:-0.70}"
MODEL="${PRE_MODEL:-${CFG_MODEL:-english}}"

# Gate: the file's thresholds, each replaced by its override when one is set.
# An override that is not a number makes jq fail, which fails open.
GATE=$(printf '%s' "$GATE" | jq -c \
    --arg fp "${SYSTEM_ONE_BASH_ASK_FOREIGN_PROCESS:-}" \
    --arg irr "${SYSTEM_ONE_BASH_ASK_IRREVERSIBLE:-}" \
    --arg lm "${SYSTEM_ONE_BASH_ASK_LEAVES_MACHINE:-}" \
    --arg ni "${SYSTEM_ONE_BASH_ASK_NETWORK_INSTALL:-}" \
    '. as $g
     | [["foreign_process", $fp], ["irreversible", $irr], ["leaves_machine", $lm], ["network_install", $ni]]
     | map(select(.[1] != "" and ($g | has(.[0]))) | {(.[0]): (.[1] | tonumber)})
     | add // {} | $g + .' 2>/dev/null)
[ -n "$GATE" ] || exit 0

STATE_CMD="$COMMAND"
if [ "$KEEP" != 0 ] && [ -r "$STATE_AWK" ]; then
    STATE_CMD=$(printf '%s\n' "$COMMAND" | awk -v "KEEP=$KEEP" -f "$STATE_AWK" 2>/dev/null) || STATE_CMD="$COMMAND"
    [ -n "$STATE_CMD" ] || STATE_CMD="$COMMAND"
fi

ACTED=false
[ "$MODE" = act ] && ACTED=true   # recorded as acted only if would_act also holds (below)

RESP=$(jq -cn --arg cwd "$CWD" --arg cmd "$STATE_CMD" --argjson q "$QUESTIONS" \
        '{state: ("cwd: " + $cwd + "\ncommand:\n" + $cmd), questions: $q}' 2>/dev/null \
    | "$WRAPPER" ask --hook bash --session "$SESSION" --threshold "$THRESHOLD" --gate "$GATE" \
        --model "$MODEL" --keep-state --fail-open --acted "$ACTED" --extra "$EXTRA" 2>/dev/null) || exit 0
[ -z "$RESP" ] && exit 0
[ "$MODE" = act ] || exit 0

WOULD=$(printf '%s' "$RESP" | jq -r '.would_act // false' 2>/dev/null)
[ "$WOULD" = true ] || exit 0

REASON=$(printf '%s' "$RESP" | jq -r '
    [.fired[] | "\(.q)=\(.value * 100 | round / 100)"] | join(", ")
    | "system-one: the decision model rates this command as likely destructive (" + . + "). It is a probabilistic check beside the exact guards, at per-question thresholds; confirm the command is meant to do this."' 2>/dev/null)
[ -n "$REASON" ] || exit 0
jq -cn --arg r "$REASON" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $r}}'
exit 0
