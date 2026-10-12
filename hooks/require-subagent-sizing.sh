#!/bin/bash
# DESC: PreToolUse hook on Agent — refuses a sub-agent spawn that names no model, fills in a missing effort
#
# The rule is claude/rules/size-subagents-to-the-task.md. A rule is advice the
# model forgets in a long context; this makes the model choice explicit. It
# cannot judge whether the chosen model fits the task, only that one was chosen.
#
# Refused (exit 2):
#   - no `model`
# Rewritten (allowed, with `effort` added through updatedInput):
#   - `model` haiku with no `effort`  -> effort low
#   - `model` sonnet with no `effort` -> effort medium
#   (the rule's values for those rows; one stderr line says what was set)
# Always allowed:
#   - subagent_type "fork", which ignores model and effort
#   - opus or fable without effort (the rule's last row omits it)
#   - any other model string, so a new model name is never blocked here
#
# The sizing table printed on refusal is read from the rule file itself, so
# the two cannot drift. Bash, not zsh, to match the hooks beside it.

set -e

INPUT=$(cat)

TYPE=$(printf '%s' "$INPUT" | jq -r '.tool_input.subagent_type // empty')
MODEL=$(printf '%s' "$INPUT" | jq -r '.tool_input.model // empty')
EFFORT=$(printf '%s' "$INPUT" | jq -r '.tool_input.effort // empty')

[ "$TYPE" = "fork" ] && exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RULE="$HERE/../claude/rules/size-subagents-to-the-task.md"

rule_table() {
    # The markdown table under "## Pick by the work", header and separator dropped.
    [ -r "$RULE" ] || { echo "  (rule file not found: $RULE)"; return; }
    awk '/^## Pick by the work/{on=1; next} on && /^## /{exit} on && /^\|/ && !/^\|---/ && !/^\| The sub-agent does/' "$RULE" \
        | sed -e 's/^| */  /' -e 's/ *| */   model /' -e 's/ *| */   effort /' -e 's/ *|$//'
}

deny() {
    echo "BLOCKED: $1" >&2
    {
        echo
        echo "Size the sub-agent to the task (claude/rules/size-subagents-to-the-task.md):"
        echo
        rule_table
        echo
        echo "A lookup of up to ~5 tool calls is done in this session instead. Put this table"
        echo "and a ~250-word report cap in the sub-agent's brief. Re-issue the call."
    } >&2
    exit 2
}

[ -z "$MODEL" ] && deny "this Agent call sets no model."

if [ -z "$EFFORT" ]; then
    case "$MODEL" in
        haiku)  DEFAULT=low ;;
        sonnet) DEFAULT=medium ;;
        *)      DEFAULT= ;;
    esac
    if [ -n "$DEFAULT" ]; then
        echo "require-subagent-sizing: model $MODEL named no effort; set effort $DEFAULT (claude/rules/size-subagents-to-the-task.md)" >&2
        printf '%s' "$INPUT" | jq -c --arg e "$DEFAULT" \
            '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "allow", updatedInput: (.tool_input + {effort: $e})}}'
        exit 0
    fi
fi

exit 0
