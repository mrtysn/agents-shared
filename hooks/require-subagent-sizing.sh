#!/bin/bash
# DESC: PreToolUse hook on Agent — refuses a sub-agent spawn that names no model
#
# The rule is claude/rules/size-subagents-to-the-task.md. A rule is advice the
# model forgets in a long context; this makes the choice explicit. It cannot
# judge whether the chosen model fits the task, only that one was chosen.
#
# Refused (exit 2):
#   - no `model`
#   - `model` haiku or sonnet with no `effort` (the table's top two rows)
# Always allowed:
#   - subagent_type "fork", which ignores model and effort
#   - opus or fable without effort (the table's last row omits it)
#   - any other model string, so a new model name is never blocked here
#
# Bash, not zsh, to match the hooks beside it.

set -e

INPUT=$(cat)

TYPE=$(printf '%s' "$INPUT" | jq -r '.tool_input.subagent_type // empty')
MODEL=$(printf '%s' "$INPUT" | jq -r '.tool_input.model // empty')
EFFORT=$(printf '%s' "$INPUT" | jq -r '.tool_input.effort // empty')

[ "$TYPE" = "fork" ] && exit 0

deny() {
    echo "BLOCKED: $1" >&2
    cat >&2 <<'TABLE'

Size the sub-agent to the task (claude/rules/size-subagents-to-the-task.md):

  Search/survey over ~5 tool calls, mechanical edits   model haiku   effort low
  Ordinary implementation, diff review under ~200 lines model sonnet  effort medium
  Design, larger review, cross-codebase judgment        model opus    (omit effort)

A lookup of up to ~5 tool calls is done in this session instead. Put this table
and a ~250-word report cap in the sub-agent's brief. Re-issue the call.
TABLE
    exit 2
}

[ -z "$MODEL" ] && deny "this Agent call sets no model."

case "$MODEL" in
    haiku|sonnet)
        [ -z "$EFFORT" ] && deny "model $MODEL needs an effort (low for haiku, medium for sonnet)."
        ;;
esac

exit 0
