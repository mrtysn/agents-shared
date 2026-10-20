#!/bin/bash
# DESC: PreToolUse hook — shows a rule's full text the first time its trigger fires in a session
#
# A rule that applies only when a particular tool call is made does not have to sit in
# every session's context. Its full text lives in docs/on-demand/<id>.md, and a row in
# hooks/rule-triggers.tsv says which tool call brings it up. This hook is registered once
# in settings.json; moving another rule out of claude/rules/ is a new row and a new doc,
# never another settings edit.
#
# Row columns, tab-separated (blank lines and # lines are skipped):
#   id       the doc is docs/on-demand/<id>.md, and the id names the once-per-session marker
#   tools    ERE matched against the whole tool name: Bash, Write|Edit, SendMessage ...
#   field    what the pattern is matched against: command, file_path, content, url, to
#            (a SendMessage recipient), or none (every call of the tool matches; pattern
#            is ignored)
#   pattern  ERE (grep -E) on that field
#   exclude  ERE on the same field that cancels a match, or `-` for none
#   mode     deny-once  the call is refused (exit 2) with the text, and the same action
#                       goes through when re-issued; for a rule that has to fire before
#                       the action
#            deny-each  like deny-once, but each distinct call (same tool input) is refused
#                       once, so every new message is stopped and a re-issue of the same
#                       one goes through; for a rule that has to be weighed at every use
#            note-once  the call goes ahead and the text is added to the model's context
#                       (hookSpecificOutput.additionalContext)
#   scope    optional. `main` fires the row only in the main conversation, not inside a
#            sub-agent (a sub-agent's hook input carries `agent_id`); anything else, or
#            nothing, fires it everywhere.
#
# Fires at most once per rule per session and per agent: a sub-agent carries its parent's
# session_id, so the marker is named for the session id plus the agent id (empty in the
# main conversation), and a sub-agent's first trip does not use up the parent's. Markers
# are files under $CLAUDE_CONFIG_DIR/rule-injection/, pruned after 14 days; when one cannot
# be written the call is not refused and no text is added. A missing doc file does nothing.
#
# Bash, not zsh, to match the hooks beside it. Written for bash 3.2 (macOS /bin/bash).

set -e

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty')
AGENT=$(printf '%s' "$INPUT" | jq -r '.agent_id // empty')
[ -n "$TOOL" ] || exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TRIGGERS=${RULE_TRIGGERS:-$HERE/rule-triggers.tsv}
DOCS="$HERE/../docs/on-demand"
STATE=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/rule-injection
[ -r "$TRIGGERS" ] || exit 0

field_value() {
    case "$1" in
        command)   printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' ;;
        file_path) printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' ;;
        content)   printf '%s' "$INPUT" | jq -r '.tool_input.content // .tool_input.new_string // empty' ;;
        url)       printf '%s' "$INPUT" | jq -r '.tool_input.url // empty' ;;
        to)        printf '%s' "$INPUT" | jq -r '.tool_input.to // empty' ;;
        *)         printf '' ;;
    esac
}

DENY_TEXT=
NOTE_TEXT=

while IFS=$'\t' read -r id tools field pattern exclude mode scope; do
    case "${id-}" in ''|'#'*) continue ;; esac
    printf '%s' "$TOOL" | grep -Eq "^($tools)\$" || continue
    [ "${scope-}" = main ] && [ -n "$AGENT" ] && continue

    if [ "$field" != none ]; then
        value=$(field_value "$field")
        [ -n "$value" ] || continue
        printf '%s' "$value" | grep -Eq -e "$pattern" || continue
        if [ "$exclude" != "-" ] && printf '%s' "$value" | grep -Eq -e "$exclude"; then
            continue
        fi
    fi

    doc="$DOCS/$id.md"
    [ -r "$doc" ] || continue

    mark="$STATE/${SESSION:-no-session}${AGENT:+-$AGENT}-$id"
    if [ "$mode" = deny-each ]; then
        mark="$mark-$(printf '%s' "$INPUT" | jq -cS '.tool_input' | shasum | cut -c1-16)"
    fi
    [ -e "$mark" ] && continue
    {
        mkdir -p "$STATE" &&
        find "$STATE" -type f -mtime +14 -delete &&
        : > "$mark"
    } 2>/dev/null || continue

    text=$(cat "$doc")
    case "$mode" in
        deny-once|deny-each) DENY_TEXT="$DENY_TEXT
$text
" ;;
        *)         NOTE_TEXT="$NOTE_TEXT
$text
" ;;
    esac
done < "$TRIGGERS"

if [ -n "$DENY_TEXT" ]; then
    {
        echo "BLOCKED once: this call meets a standing rule. Its text:"
        printf '%s\n' "$DENY_TEXT$NOTE_TEXT"
        echo "Re-issue the call if it still fits the rule."
    } >&2
    exit 2
fi

if [ -n "$NOTE_TEXT" ]; then
    jq -n --arg n "A standing rule applies to what you are doing:$NOTE_TEXT" \
        '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $n}}'
fi
exit 0
