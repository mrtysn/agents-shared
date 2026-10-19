#!/bin/bash
# DESC: PreToolUse hook on AskUserQuestion — refuses a question that points at facts never sent
#
# Covers docs/on-demand/asking-for-decisions.md ("each question must stand alone"). A
# question that says "the table above" or "as listed" relies on text the user has seen. If the
# assistant sent no visible text since the user last spoke (its table or findings were only in
# thinking), the pointer leads nowhere and the user answers blind.
#
# Refused (exit 2) when both hold:
#   - some question's text contains pointer wording: "above", "the table", "as listed",
#     "listed above", "shown above", "see above" (case-insensitive, whole words)
#   - the assistant has written no text block since the last user reply, a typed prompt or the
#     answer to an earlier AskUserQuestion (read with scripts/extract-session-text.py
#     --since-last-user, never a parser of this hook's own)
# Allowed otherwise, and always when the transcript cannot be read (fails open: a missing
# path, a missing reader or a reader error never blocks a question).
#
# A second, independent trigger covers a file the question rests on. Refused (exit 2) when a
# question's text contains a file path (a token with a "/" ending in html, htm, png, jpg, jpeg,
# gif, svg, mp4, mov, webm, pdf, md, csv, json, txt or zip; URLs with "://" and glob patterns
# with "*" or "?" are not file paths)
# unless that path is ABSOLUTE and appears in a visible assistant text block since the user last
# spoke. A relative path is refused even when prose had it: the question must stand alone, so
# it names the absolute path too. Same reader call, same fail-open behaviour.
#
# Bash, not zsh, to match the hooks beside it.

INPUT=$(cat)

TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null) || exit 0
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0

QUESTIONS=$(printf '%s' "$INPUT" | jq -r '[.tool_input.questions[]?.question // empty] | join("\n")' 2>/dev/null) || exit 0
[ -n "$QUESTIONS" ] || exit 0

POINTER='\b(above|the table|as listed|listed above|shown above|see above)\b'
PATHRE='[^[:space:]"'"'"'`()<>,;]*/[^[:space:]"'"'"'`()<>,;]*\.(html|htm|png|jpg|jpeg|gif|svg|mp4|mov|webm|pdf|md|csv|json|txt|zip)\b'

HAS_POINTER=0
printf '%s' "$QUESTIONS" | grep -Eqi "$POINTER" && HAS_POINTER=1
PATHS=$(printf '%s' "$QUESTIONS" | grep -Eoi "$PATHRE" | grep -v -e '://' -e '[*?]')
[ "$HAS_POINTER" = 1 ] || [ -n "$PATHS" ] || exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
READER="$HERE/../scripts/extract-session-text.py"
[ -r "$READER" ] || exit 0

ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds assistant --since-last-user --json 2>/dev/null) || exit 0
# jq failing on the reader's output is not proof the turn was silent.
printf '%s' "$ROWS" | jq -e -s 'type == "array"' >/dev/null 2>&1 || exit 0
VISIBLE=$(printf '%s' "$ROWS" | jq -r -s '.[] | .text // empty' 2>/dev/null) || exit 0

if [ -n "$PATHS" ]; then
    while IFS= read -r P; do
        [ -n "$P" ] || continue
        case "$P" in
            /*)
                printf '%s' "$VISIBLE" | grep -Fq -- "$P" && continue
                WHY="the absolute path $P never appeared in visible text since the user last spoke" ;;
            *)
                WHY="the question names a relative path ($P); name the absolute path in the question text too, since a question stands alone" ;;
        esac
        cat >&2 <<MSG
BLOCKED: the file this question rests on was never sent as an absolute path in visible text: $WHY. Text in thinking never reaches the user.

Write the absolute path on its own line in a text block, then ask in a LATER response of this same turn (text in the same response as the question is not yet in the transcript when this hook runs; a tool call in between flushes it). Use the absolute path in the question as well (docs/on-demand/asking-for-decisions.md, absolute-paths-for-handoff).
MSG
        exit 2
    done <<PATHLIST
$PATHS
PATHLIST
fi

[ "$HAS_POINTER" = 1 ] || exit 0
# Any visible text block this turn means the pointer can lead somewhere.
printf '%s' "$VISIBLE" | grep -q '[^[:space:]]' && exit 0

WORD=$(printf '%s' "$QUESTIONS" | grep -Eoi "$POINTER" | head -n1)
cat >&2 <<MSG
BLOCKED: this question points at "$WORD", but you have sent no visible text since the user last spoke. Text that exists only in thinking was never shown, so nothing it points at reached the user.

Each question stands alone (docs/on-demand/asking-for-decisions.md). Do one of:
  - put the facts inside the question text itself (the list, the table's rows, what is at stake), then re-issue the call
  - send them in a plain reply that ends without a question, and ask in the next turn
  - for a long or visual decision, use an HTML decision form (/new-html-page, decision-form mode)
If the user's last answer asked for output ("list me them in a table"), send that output in a reply before asking anything.
MSG
exit 2
