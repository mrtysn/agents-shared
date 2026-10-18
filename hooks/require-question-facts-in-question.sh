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
# Bash, not zsh, to match the hooks beside it.

INPUT=$(cat)

TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null) || exit 0
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0

QUESTIONS=$(printf '%s' "$INPUT" | jq -r '[.tool_input.questions[]?.question // empty] | join("\n")' 2>/dev/null) || exit 0
[ -n "$QUESTIONS" ] || exit 0

POINTER='\b(above|the table|as listed|listed above|shown above|see above)\b'
printf '%s' "$QUESTIONS" | grep -Eqi "$POINTER" || exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
READER="$HERE/../scripts/extract-session-text.py"
[ -r "$READER" ] || exit 0

ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds assistant --since-last-user --json 2>/dev/null) || exit 0
# Any visible text block this turn means the pointer can lead somewhere.
if printf '%s' "$ROWS" | jq -e -s 'any(.[]; (.text // "") | test("\\S"))' >/dev/null 2>&1; then
    exit 0
fi
# jq failing on the reader's output is not proof the turn was silent.
printf '%s' "$ROWS" | jq -e -s 'type == "array"' >/dev/null 2>&1 || exit 0

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
