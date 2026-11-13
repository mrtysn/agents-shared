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
# spoke. A relative path to a file the user opens outside the terminal (html, htm, png, jpg, jpeg,
# gif, svg, mp4, mov, webm, pdf, zip) is refused even when prose had it: the question must stand
# alone, so it names the absolute path too. A relative md, csv, json or txt path is a code or config
# reference, read in the terminal, and stays relative. Same reader call, same fail-open behaviour.
#
# A third trigger needs no transcript: a label coined in the session. Refused (exit 2) when the
# questions or their options name a letter label (capitals A to H) as "option B", "pair A",
# "direction C" (after option, direction, pair, plan, variant, version, choice, route, design,
# palette, approach or layout), "B or C", "A vs B" or "A/B", and that letter is not defined in
# the same call's text as "B: …", "B = …", "B — …" or "B (…)". The letters were named on a form
# or in earlier prose; the user deciding from the prompt alone does not know what they stand for.
#
# A fourth trigger only nudges and never refuses: when the hook ends with exit 0 and a question text is over
# 300 characters with no blank line, or an option description holds a line break (the terminal renders it as
# a replacement character) or is over 240 characters, the agent gets a PreToolUse additionalContext with the
# layout template (survey 2026-11-12: 51% of 4,572 questions had no blank line in a long text). It reads the
# call alone, so it waits for nothing. To measure adoption, rerun the count over questions asked in sessions
# started after 2026-11-12 (extract-session-text.py --all --kinds calls --json --grep AskUserQuestion) and
# compare the share of long texts with no blank line against that 51%.
#
# Bash, not zsh, to match the hooks beside it.

INPUT=$(cat)

# A nudge that never blocks: when the hook ends with exit 0 and the question breaks the layout, the agent
# gets a note (PreToolUse additionalContext) with the template. Read from the call alone, no transcript.
LAYOUT=$(printf '%s' "$INPUT" | jq -r '
  [ .tool_input.questions[]? |
    (if ((.question // "") | length) > 300 and (((.question // "") | test("\n[ \t]*\n")) | not) then "paragraph" else empty end),
    (if any(.options[]?; ((.description // "") | test("[\r\n]"))) then "break" else empty end),
    (if any(.options[]?; ((.description // "") | length) > 240) then "long" else empty end)
  ] | unique | join(",")' 2>/dev/null) || LAYOUT=""
emit_layout_nudge() {
    local msg="Question layout (docs/on-demand/asking-for-decisions.md):"
    case ",$LAYOUT," in *,paragraph,*) msg="$msg a question text over 300 characters is one paragraph and renders as one bold block." ;; esac
    case ",$LAYOUT," in *,break,*) msg="$msg a line break inside an option description renders as a replacement character." ;; esac
    case ",$LAYOUT," in *,long,*) msg="$msg an option description over 240 characters crowds the options." ;; esac
    msg="$msg Next time: the topic on line 1, a blank line, one fact per line (numbered when they are items), a blank line, the question alone on the last line; describe each item once, in its option or in a fact line; keep each option description to one line."
    jq -cn --arg c "$msg" '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $c}}'
}
trap 'rc=$?; [ "$rc" -eq 0 ] && [ -n "$LAYOUT" ] && emit_layout_nudge' EXIT

ALLTEXT=$(printf '%s' "$INPUT" | jq -r '[.tool_input.questions[]? | .question, (.options[]? | .label, .description)] | map(select(type == "string")) | join("\n")' 2>/dev/null) || ALLTEXT=""
NOUNS='option|direction|pair|plan|variant|version|choice|route|design|palette|approach|layout'
LETTERREF="\\b(($NOUNS)s? [A-H]|[A-H] (or|and|vs\\.?) [A-H]|[A-H]/[A-H])\\b"
REFS=$(printf '%s' "$ALLTEXT" | grep -Eo "$LETTERREF" | grep -Eo '\b[A-H]\b' | sort -u)
for L in $REFS; do
    printf '%s' "$ALLTEXT" | grep -Eq "\\b$L( ?[:=—–]| \\()" && continue
    REF=$(printf '%s' "$ALLTEXT" | grep -Eo "$LETTERREF" | grep -E "\\b$L\\b" | head -n1)
    cat >&2 <<MSG
BLOCKED: this question names "$REF", but the letter $L is never defined in the question or its options. A label coined on a form or in earlier prose means nothing to a user deciding from the prompt alone.

Each question stands alone (docs/on-demand/asking-for-decisions.md): put the facts inside the question. Name the thing itself ("the bear and bunny pair", not "B"), or define the letter where it is used ("B (bear and bunny)"), then re-issue the call.
MSG
    exit 2
done

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

read_visible() {
    ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds assistant --since-last-user --json 2>/dev/null) || exit 0
    # jq failing on the reader's output is not proof the turn was silent.
    printf '%s' "$ROWS" | jq -e -s 'type == "array"' >/dev/null 2>&1 || exit 0
    VISIBLE=$(printf '%s' "$ROWS" | jq -r -s '.[] | .text // empty' 2>/dev/null) || exit 0
}

# True while the evidence a refusal would rest on is missing: an absolute path not yet in
# visible text, or a pointer with no visible text at all.
visible_evidence_missing() {
    local P
    while IFS= read -r P; do
        case "$P" in /*) printf '%s' "$VISIBLE" | grep -Fq -- "$P" || return 0 ;; esac
    done <<PATHLIST
$PATHS
PATHLIST
    [ "$HAS_POINTER" = 1 ] && ! printf '%s' "$VISIBLE" | grep -q '[^[:space:]]' && return 0
    return 1
}

read_visible
# The text sent in the same message as this question can reach the transcript file a moment
# after the hook runs (a refusal came back though the path sat in a text block written three
# seconds earlier; another, in a 59MB transcript, was still missing after 3s though the entry
# was timestamped 4s before the question). Read again before refusing, so a lagging write is
# not read as a silent turn. Waits only while evidence is missing, so a true refusal costs 12s.
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    visible_evidence_missing || break
    sleep 1
    read_visible
done

if [ -n "$PATHS" ]; then
    while IFS= read -r P; do
        [ -n "$P" ] || continue
        case "$P" in
            /*)
                printf '%s' "$VISIBLE" | grep -Fq -- "$P" && continue
                WHY="the absolute path $P never appeared in visible text since the user last spoke" ;;
            *)
                # A relative code or config reference (a .md, .csv, .json or .txt file) is read, not opened.
                case "$(printf '%s' "$P" | tr 'A-Z' 'a-z')" in *.md|*.csv|*.json|*.txt) continue ;; esac
                WHY="the question names a relative path ($P); name the absolute path in the question text too, since a question stands alone" ;;
        esac
        cat >&2 <<MSG
BLOCKED: the file this question rests on was never sent as an absolute path in visible text: $WHY. Text in thinking never reaches the user.

What this hook checks: the absolute path appears in a visible assistant text block written since the user's last typed prompt or answered question (a question this hook refused does not count as an answer). Use the absolute path in the question as well (docs/on-demand/asking-for-decisions.md, absolute-paths-for-handoff). If refused twice, put the facts and the decision in a plain reply and let the user answer in text.
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
