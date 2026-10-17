#!/bin/bash
# DESC: PreToolUse hook on Agent — refuses a sub-agent spawn that names no model, fills in a missing effort
#
# The guidance is docs/size-subagents-to-the-task.md. It is not a rule: it is not
# loaded into sessions, so this hook is how it reaches one. The hook makes the model
# choice explicit; it cannot judge whether the chosen model fits the task, only
# that one was chosen.
#
# Refused (exit 2):
#   - no `model`
#   - a session's first Agent call, once per session_id, so the table below reaches
#     the session before it picks a model. The marker is a file under $TMPDIR; when
#     it cannot be written the call is not refused.
#   - `opus` or `fable` for a task whose description opens with a build verb ("Build",
#     "Fix", "Implement", ...): the table puts ordinary implementation on sonnet. Once
#     per session and description, so a call that really is judgment work passes when
#     it is issued again unchanged. A heuristic on the first word: it cannot judge the
#     task, only that the description reads like the sonnet row.
# Rewritten (allowed, with `effort` added through updatedInput):
#   - `model` haiku with no `effort`  -> effort low
#   - `model` sonnet with no `effort` -> effort medium
#   (the table's values for those rows; one stderr line says what was set)
# Always allowed:
#   - subagent_type "fork", which ignores model and effort
#   - opus or fable without effort (the table's last row omits it)
#   - any other model string, so a new model name is never blocked here
#
# The sizing table printed on refusal is read from the docs file itself, so
# the two cannot drift. Bash, not zsh, to match the hooks beside it.

set -e

INPUT=$(cat)

TYPE=$(printf '%s' "$INPUT" | jq -r '.tool_input.subagent_type // empty')
MODEL=$(printf '%s' "$INPUT" | jq -r '.tool_input.model // empty')
EFFORT=$(printf '%s' "$INPUT" | jq -r '.tool_input.effort // empty')

[ "$TYPE" = "fork" ] && exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GUIDE="$HERE/../docs/size-subagents-to-the-task.md"

guide_table() {
    # The markdown table under "## Pick by the work", header and separator dropped.
    [ -r "$GUIDE" ] || { echo "  (guidance file not found: $GUIDE)"; return; }
    awk '/^## Pick by the work/{on=1; next} on && /^## /{exit} on && /^\|/ && !/^\|---/ && !/^\| The sub-agent does/' "$GUIDE" \
        | sed -e 's/^| */  /' -e 's/ *| */   model /' -e 's/ *| */   effort /' -e 's/ *|$//'
}

deny() {
    echo "BLOCKED: $1" >&2
    {
        echo
        echo "Size the sub-agent to the task (docs/size-subagents-to-the-task.md in agents-shared):"
        echo
        guide_table
        echo
        echo "Edits never go in the haiku row: nothing checks a sub-agent's edits mid-run. Where a"
        echo "task could sit in two rows and its difficulty is unknown, start in the lower row."
        echo "A lookup of up to ~5 tool calls is done in this session instead. Put this table"
        echo "and a ~250-word report cap in the sub-agent's brief, and name where any file it"
        echo "produces goes. Re-issue the call."
    } >&2
    exit 2
}

# The first Agent call of a session is refused once, so the table arrives before the
# model is chosen. A call with no session_id, or a marker that cannot be written, passes.
FIRST=0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty')
AGENT=$(printf '%s' "$INPUT" | jq -r '.agent_id // empty')
if [ -n "$SESSION" ]; then
    # A sub-agent carries its parent's session_id, so the marker names the agent as well.
    SEEN_DIR="${TMPDIR:-/tmp}/agents-shared-subagent-sizing"
    MARK="$SEEN_DIR/$SESSION${AGENT:+-$AGENT}"
    if mkdir -p "$SEEN_DIR" 2>/dev/null && [ ! -e "$MARK" ] && : > "$MARK" 2>/dev/null; then
        FIRST=1
        find "$SEEN_DIR" -type f -mtime +14 -delete 2>/dev/null || true
    fi
fi

[ -z "$MODEL" ] && deny "this Agent call sets no model."
[ "$FIRST" = 1 ] && deny "this is the session's first Agent call; the sizing table is shown once, before you choose."

# opus and fable are allowed without effort, but not for work the table gives to sonnet.
# Week of 2026-10-12: asset-pipeline's heaviest session ran 1,772 sub-agent requests on
# opus at ~290k context for tasks described "Build ...", "Fix ...", "Offload ...": 127M
# weighted tokens, 16% of the whole week.
if [ -n "$SESSION" ] && { [ "$MODEL" = opus ] || [ "$MODEL" = fable ]; }; then
    DESC=$(printf '%s' "$INPUT" | jq -r '.tool_input.description // empty')
    WORD=$(printf '%s' "$DESC" | tr '[:upper:]' '[:lower:]' | awk '{print $1}')
    case "$WORD" in
        build|fix|implement|add|write|refactor|wire|offload|auto-route|create|migrate|port|rename|patch|install|convert|extract|apply|make|update|move)
            SUM=$(printf '%s' "$DESC" | cksum | cut -d' ' -f1)
            IMPL_MARK="$SEEN_DIR/impl-$SESSION${AGENT:+-$AGENT}-$SUM"
            if [ ! -e "$IMPL_MARK" ] && : > "$IMPL_MARK" 2>/dev/null; then
                deny "this spawn runs $MODEL for \"$DESC\", which reads as implementation. The table below puts ordinary implementation on sonnet (effort medium, high for a bug fix); $MODEL is for design and judgment, at twice sonnet's price. If this task really needs design or cross-codebase judgment, issue the same call again unchanged and it will pass."
            fi
            ;;
    esac
fi

if [ -z "$EFFORT" ]; then
    case "$MODEL" in
        haiku)  DEFAULT=low ;;
        sonnet) DEFAULT=medium ;;
        *)      DEFAULT= ;;
    esac
    if [ -n "$DEFAULT" ]; then
        echo "require-subagent-sizing: model $MODEL named no effort; set effort $DEFAULT (docs/size-subagents-to-the-task.md)" >&2
        printf '%s' "$INPUT" | jq -c --arg e "$DEFAULT" \
            '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow", updatedInput: (.tool_input + {effort: $e})}}'
        exit 0
    fi
fi

exit 0
