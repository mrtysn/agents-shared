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
#   - `opus` or `fable` (or a full id containing either) for a task whose description opens
#     with a build verb ("Build", "Fix", "Implement", ...): the table puts ordinary
#     implementation on sonnet. Once per session and description, so a call that really
#     is judgment work passes when it is issued again unchanged; on the session's first
#     call both reasons arrive in one refusal. A heuristic on the first word: it cannot
#     judge the task, only that the description reads like the sonnet row.
# Allowed with the table attached (`additionalContext`):
#   - a session's first Agent call, once per session_id, that names a model: the table
#     and size limits reach the session with the call, so every later spawn is sized
#     by them. The marker is a file under ${XDG_CACHE_HOME:-$HOME/.cache}, which
#     survives a resumed session; when it cannot be written the note is sent each time.
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

guide_limits() {
    # The bullets under "## Keep it small while it runs", bold markers dropped.
    [ -r "$GUIDE" ] || return
    local limits
    limits=$(awk '/^## Keep it small while it runs/{on=1; next} on && /^## /{exit} on && /^- /' "$GUIDE" \
        | sed -e 's/^- /  /' -e 's/\*\*//g')
    if [ -n "$limits" ]; then
        printf '%s\n' "$limits"
    else
        echo "  (size limits not found: no bullets under '## Keep it small while it runs' in $GUIDE)"
    fi
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
        echo "A lookup of up to ~5 tool calls is done in this session instead."
        echo
        echo "Keep it small while it runs:"
        guide_limits
        echo
        echo "Put this table, these limits and a ~250-word report cap in the sub-agent's brief,"
        echo "and name where any file it produces goes. Re-issue the call."
    } >&2
    exit 2
}

# The first Agent call of a session carries the table as added context. A call with no
# session_id, or a marker that cannot be written, passes without it.
FIRST=0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty')
AGENT=$(printf '%s' "$INPUT" | jq -r '.agent_id // empty')
if [ -n "$SESSION" ]; then
    # A sub-agent carries its parent's session_id, so the marker names the agent as well.
    SEEN_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/subagent-sizing"
    MARK="$SEEN_DIR/$SESSION${AGENT:+-$AGENT}"
    if mkdir -p "$SEEN_DIR" 2>/dev/null && [ ! -e "$MARK" ] && : > "$MARK" 2>/dev/null; then
        FIRST=1
        find "$SEEN_DIR" -type f -mtime +14 -delete 2>/dev/null || true
    fi
fi

[ -z "$MODEL" ] && deny "this Agent call sets no model."

# opus and fable (also as a full model id) are allowed without effort, but not for work the
# table gives to sonnet. Week of 2026-10-12: asset-pipeline's heaviest session ran 1,772
# sub-agent requests on opus at ~290k context for tasks described "Build ...", "Fix ...",
# "Offload ...": 127M weighted tokens, 16% of the whole week. The description's first word
# (letters only, so "Fix:" and "- Build" count) is matched against build verbs, and the
# refusal is once per session and description. When the session's first-call refusal is
# due as well, one message carries both reasons and the repeat passes.
IMPL=0
IMPL_SENTENCE=
if [ -n "$SESSION" ]; then
    case "$MODEL" in
        opus|fable|*opus*|*fable*)
            DESC=$(printf '%s' "$INPUT" | jq -r '.tool_input.description // empty')
            WORD=$(printf '%s' "$DESC" | head -n1 | tr '[:upper:]' '[:lower:]' | sed -E 's/^[^a-z]*([a-z]+).*/\1/')
            case "$WORD" in
                build|builds|building|built|fix|fixes|fixing|fixed|implement|implements|implementing|implemented|add|adds|adding|added|write|writes|writing|wrote|refactor|refactors|refactoring|wire|wires|wiring|offload|offloads|offloading|auto|create|creates|creating|created|migrate|migrates|migrating|port|ports|porting|rename|renames|renaming|patch|patches|patching|install|installs|installing|convert|converts|converting|extract|extracts|extracting|apply|applies|applying|make|makes|making|made|update|updates|updating|move|moves|moving|edit|edits|editing|change|changes|changing|remove|removes|removing|delete|deletes|deleting|generate|generates|generating)
                    SUM=$(printf '%s' "$DESC" | cksum | cut -d' ' -f1)
                    IMPL_MARK="$SEEN_DIR/impl-$SESSION${AGENT:+-$AGENT}-$SUM"
                    if [ ! -e "$IMPL_MARK" ] && : > "$IMPL_MARK" 2>/dev/null; then
                        IMPL=1
                        IMPL_SENTENCE="this spawn runs $MODEL for \"$DESC\", which reads as implementation. The table below puts ordinary implementation on sonnet (effort medium, high for a bug fix); $MODEL costs more per token and is for design and judgment. If this task really needs design or cross-codebase judgment, issue the same call again unchanged and it will pass."
                    fi
                    ;;
            esac
            ;;
    esac
fi

# A first call that is also a build-verb opus spawn is refused once with both reasons; a
# first call that only names a model goes through with the table attached.
CONTEXT=
if [ "$FIRST" = 1 ]; then
    [ "$IMPL" = 1 ] && deny "this is the session's first Agent call, and the table below is shown once. Also, $IMPL_SENTENCE"
    CONTEXT="Sub-agent sizing (docs/size-subagents-to-the-task.md in agents-shared), shown once for this session. Pick each sub-agent's model by the work:
$(guide_table)

Edits never go in the haiku row: nothing checks a sub-agent's edits mid-run. Where a task could sit in two rows and its difficulty is unknown, start in the lower row. A lookup of up to ~5 tool calls is done in this session instead.

Keep it small while it runs:
$(guide_limits)

Put this table, these limits and a ~250-word report cap in the sub-agent's brief, and name where any file it produces goes."
fi
[ "$IMPL" = 1 ] && deny "$IMPL_SENTENCE"

DEFAULT=
if [ -z "$EFFORT" ]; then
    case "$MODEL" in
        haiku)  DEFAULT=low ;;
        sonnet) DEFAULT=medium ;;
    esac
fi
if [ -n "$DEFAULT" ] || [ -n "$CONTEXT" ]; then
    [ -n "$DEFAULT" ] && echo "require-subagent-sizing: model $MODEL named no effort; set effort $DEFAULT (docs/size-subagents-to-the-task.md)" >&2
    # permissionDecision allow rides with updatedInput only; context alone leaves the permission flow as it was.
    printf '%s' "$INPUT" | jq -c --arg e "$DEFAULT" --arg c "$CONTEXT" \
        '{hookSpecificOutput: ({hookEventName: "PreToolUse"}
            + (if $e != "" then {permissionDecision: "allow", updatedInput: (.tool_input + {effort: $e})} else {} end)
            + (if $c != "" then {additionalContext: $c} else {} end))}'
fi

exit 0
