#!/bin/bash
# PostToolUse + PostToolUseFailure (Bash) hook: writes the outcome receipt
# for the matching Bash PreToolUse verdict (hooks/system-one-bash.sh),
# section 13 of the design doc. It runs no model; it is bookkeeping only, so
# it fires in every mode (shadow, show, act) and never blocks.
#
# Two events, one script, because Claude Code routes a Bash call by its
# exit status (read from the 2.1.282 binary in review): exit 0 (or a code
# the tool interprets as non-error) ends in PostToolUse with
# tool_response {stdout, stderr, interrupted, ...} -- no exit code field at
# all -- while any other exit ends in PostToolUseFailure with
# `error` ("Exit code N\n<stderr>..."), `is_interrupt` and `is_timeout`,
# and PostToolUse does not fire. Wired to PostToolUse only, every failed
# command would read as "did not run".
#
# Matching, in order:
#   1. tool_use_id: the PreToolUse hook logs the call's tool_use_id on its
#      verdict row (--extra); both post events carry the same id, so this is
#      an exact join, immune to the same command running twice.
#   2. state_sha256 fallback, for verdict rows from before tool_use_id was
#      logged: rebuilds the exact state string the PreToolUse hook hashed
#      (same cwd, same heredoc normalisation) and takes the most recent row
#      with that hash that no outcome row already references.
#
# Row: {"kind":"outcome","ref":<verdict id>,"ran":true,"exit_code":<int or
# null>,"failed":<bool>,"interrupted":<bool>} appended to the same
# shadow/bash/<session>.jsonl. exit_code is 0 on PostToolUse, the N of
# "Exit code N" on PostToolUseFailure, else null (a timeout, an interrupt, a
# pre-spawn error). A verdict row with no outcome row by the next prompt
# means the command never ran (denied, cancelled, or blocked by another
# guard) -- scripts/system-one-receipts.py reads it that way.
#
# Fails open on everything: no command, no session, no matching verdict row,
# an unreadable shadow log. Cheap (no model call, no network): a handful of
# jq/tail calls over a small tail window. settings.json: one entry each under
# PostToolUse and PostToolUseFailure, matcher Bash, timeout 3.
#
# Bash 3.2, like the hooks beside it.

set -u

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -n "$COMMAND" ] || exit 0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null)
EVENT=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // ""' 2>/dev/null)
TOOL_USE_ID=$(printf '%s' "$INPUT" | jq -r '.tool_use_id // ""' 2>/dev/null)

# {exit_code, failed, interrupted} from the event's own shape. An explicit
# exit code field is honoured first if a future version adds one.
OUTCOME=$(printf '%s' "$INPUT" | jq -c '
    (.tool_response // {}) as $r
    | (.error // "" | if type == "string" then . else tostring end) as $err
    | (.hook_event_name // "") as $ev
    | ($err | [capture("^Exit code (?<n>[0-9]+)") | .n | tonumber] | .[0] // null) as $errcode
    | (($r.exit_code // $r.exitCode // $r.code) | if type == "number" then . else null end) as $explicit
    | (.is_interrupt // $r.interrupted // false) as $intr
    | {
        exit_code: (if $explicit != null then $explicit
                    elif $ev == "PostToolUseFailure" then $errcode
                    elif $intr == true then null
                    else 0 end),
        failed: ($ev == "PostToolUseFailure"),
        interrupted: ($intr == true)
      }' 2>/dev/null)
[ -n "$OUTCOME" ] || OUTCOME='{"exit_code":null,"failed":false,"interrupted":false}'

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
QUESTIONS_FILE="$HERE/system-one-bash-questions.json"
STATE_AWK="$HERE/system-one-bash-state.awk"
KEEP=$(jq -r '.state.heredoc_keep // 0' "$QUESTIONS_FILE" 2>/dev/null)

CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-one.local.sh"
[ -r "$CONFIG" ] || exit 0
PRE_STATE_DIR="${SYSTEM_ONE_STATE_DIR:-}"
CFG_STATE_DIR=$( ( . "$CONFIG" 2>/dev/null || exit 1; printf '%s' "${SYSTEM_ONE_STATE_DIR:-}" ) ) || exit 0
STATE_DIR="${PRE_STATE_DIR:-${CFG_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/system-one}}"

SESSION_SAFE=$(printf '%s' "$SESSION" | tr -dc 'A-Za-z0-9_-')
[ -n "$SESSION_SAFE" ] || SESSION_SAFE=_nosession
BASH_LOG="$STATE_DIR/shadow/bash/$SESSION_SAFE.jsonl"
[ -r "$BASH_LOG" ] || exit 0

# Last 40 lines: a session with heavy Bash use can have several verdict rows
# between two post calls only when tool calls run in parallel; 40 is generous
# headroom over the 1:1 pairing the hook normally sees.
TAIL=$(tail -n 40 "$BASH_LOG" 2>/dev/null)
[ -n "$TAIL" ] || exit 0
ALREADY=$(printf '%s\n' "$TAIL" | jq -r 'select((.kind // "") == "outcome") | .ref // empty' 2>/dev/null)

REF=""
if [ -n "$TOOL_USE_ID" ]; then
    REF=$(printf '%s\n' "$TAIL" | jq -r --arg t "$TOOL_USE_ID" \
        'select((.kind // "") != "outcome") | select(.tool_use_id == $t) | select(.id != null) | .id' 2>/dev/null | tail -n 1)
fi

if [ -z "$REF" ]; then
    # Same state the PreToolUse hook built, so the sha256 matches byte for byte.
    STATE_CMD="$COMMAND"
    if [ "$KEEP" != 0 ] && [ -r "$STATE_AWK" ]; then
        STATE_CMD=$(printf '%s\n' "$COMMAND" | awk -v "KEEP=$KEEP" -f "$STATE_AWK" 2>/dev/null) || STATE_CMD="$COMMAND"
        [ -n "$STATE_CMD" ] || STATE_CMD="$COMMAND"
    fi
    STATE="cwd: $CWD
command:
$STATE_CMD"
    SHA=$(printf '%s' "$STATE" | shasum -a 256 2>/dev/null | cut -d' ' -f1)
    [ -n "$SHA" ] || exit 0
    CANDIDATES=$(printf '%s\n' "$TAIL" | jq -r --arg sha "$SHA" \
        'select((.kind // "") != "outcome") | select(.tool_use_id == null) | select(.state_sha256 == $sha) | select(.id != null) | .id' 2>/dev/null)
    # Most recent unclaimed match wins: a denied earlier run of the same
    # command (no outcome row) must not absorb this run's receipt.
    while IFS= read -r rid; do
        [ -n "$rid" ] || continue
        printf '%s\n' "$ALREADY" | grep -qxF "$rid" && continue
        REF="$rid"
    done <<<"$CANDIDATES"
fi
[ -n "$REF" ] || exit 0
printf '%s\n' "$ALREADY" | grep -qxF "$REF" && exit 0   # already receipted (a hook re-run)

jq -cn --arg ref "$REF" --argjson o "$OUTCOME" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" \
    '{ts: $ts, kind: "outcome", ref: $ref, ran: true} + $o' >>"$BASH_LOG" 2>/dev/null
exit 0
