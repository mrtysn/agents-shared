#!/bin/bash
# PreToolUse hook (Edit|Write): keep auto-memory index lines topic-only, and
# refuse a memory that duplicates a rule
#
# MEMORY.md loads into every session in its project; the memory files load only
# on recall. So a fact in an index line is paid for in every session whether or
# not the topic comes up, and the index is where private detail leaks. The
# companion rule (claude/rules/memory-hygiene.md) says what to write; this
# enforces the two halves that a script can check.
#
# On a write under <config>/projects/*/memory/:
#   - MEMORY.md: every index line that is new or changed relative to the file on
#     disk must be a topic label — no digits, no currency symbol, at most
#     MAX_WORDS words after the dash. Entries whose file says `type: feedback`
#     are exempt: a prohibition has to fire before the mistake, so its
#     instruction stays in the index line.
#   - any other file being created: its slug must not match a rule in
#     <config>/rules/. A memory restating a loaded rule costs twice and drifts.
#
# Only the lines being introduced are checked, so a whole-file rewrite of an
# index that already carries old offenders is not blocked for them.
#
# Fails closed, like the other PreToolUse guards: a guard that cannot run
# refuses rather than waving the write through.

set -uo pipefail

MAX_WORDS=12

fail() {
    echo "memory-lint: $*" >&2
    exit 2
}

command -v jq >/dev/null 2>&1 || fail "jq is required and was not found; install it or wire this hook out"

input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -n "$path" ] || exit 0

case "$path" in
    */projects/*/memory/*.md) ;;
    *) exit 0 ;;
esac

memory_dir=$(dirname "$path")
base=$(basename "$path")
config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
rules_dir="$config_dir/rules"

case "$tool" in
    Write) text=$(printf '%s' "$input" | jq -r '.tool_input.content // empty') ;;
    Edit)  text=$(printf '%s' "$input" | jq -r '.tool_input.new_string // empty') ;;
    *) exit 0 ;;
esac

# --- MEMORY.md: index-line shape --------------------------------------------

if [ "$base" = "MEMORY.md" ]; then
    existing=""
    [ -r "$path" ] && existing=$(cat "$path")
    while IFS= read -r line; do
        case "$line" in
            "- ["*) ;;
            *) continue ;;
        esac
        # unchanged lines were already accepted (or predate the hook)
        if [ -n "$existing" ] && printf '%s\n' "$existing" | grep -qxF -- "$line"; then
            continue
        fi
        slug=$(printf '%s' "$line" | sed -n 's/.*](\([^)]*\)\.md).*/\1/p')
        [ -n "$slug" ] || continue
        entry_type=""
        if [ -r "$memory_dir/$slug.md" ]; then
            entry_type=$(sed -n '1,/^---$/{/^---$/!p;}' "$memory_dir/$slug.md" | sed -n 's/^[[:space:]]*type:[[:space:]]*//p' | head -1)
        fi
        [ "$entry_type" = "feedback" ] && continue
        hook=${line#*— }
        [ "$hook" = "$line" ] && hook=${line#*-- }
        words=$(printf '%s' "$hook" | wc -w | tr -d ' ')
        bad=""
        case "$hook" in *[0-9]*) bad="digits" ;; esac
        case "$hook" in *[\$€₺£]*) bad="${bad:+$bad, }currency" ;; esac
        [ "$words" -gt "$MAX_WORDS" ] && bad="${bad:+$bad, }over $MAX_WORDS words"
        if [ -n "$bad" ]; then
            fail "index line for $slug carries a fact ($bad). Keep the fact in $slug.md and make the line a topic label. If this entry is a prohibition, mark the file \`type: feedback\`."
        fi
    done <<< "$text"
    exit 0
fi

# --- new memory file: rule collision ----------------------------------------

[ -e "$path" ] && exit 0            # editing an existing memory is not a new duplicate
[ -d "$rules_dir" ] || exit 0

normalize() {
    printf '%s' "$1" | sed -E 's/^(feedback|reference|project|user)[_-]//; s/_/-/g' | tr '[:upper:]' '[:lower:]'
}

slug=$(normalize "${base%.md}")
for rule in "$rules_dir"/*.md; do
    [ -e "$rule" ] || continue
    rname=$(basename "$rule" .md)
    if [ "$(normalize "$rname")" = "$slug" ]; then
        fail "$base duplicates the rule $rules_dir/$rname.md, which already loads in every session. Write no memory for it; edit the rule if it is wrong."
    fi
done
exit 0
