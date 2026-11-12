#!/bin/bash
# DESC: PreToolUse hook on AskUserQuestion|Skill|Agent|SendMessage — refuses requested content written in the same turn as a tool call
#
# The failure this prevents (survey of 12 sessions since 2026-09-11, 14 instances): the user asked to see content
# ("list me all the names you suggested chronologically", "give me the text already", "claude why do you ignore my
# table request"), and the agent wrote it as text in the same turn as a following AskUserQuestion, Skill or Agent
# call. The screen collapses text written before a tool call to one summary line, so the user saw a summary where
# the content should be and asked again. The cause was upstream: claude/rules/end-every-turn-with-a-next-step.md
# pushes every turn to end in AskUserQuestion, so requested content got attached to a question.
#
# Refused (exit 2), once per turn, when all hold:
#   - the call is AskUserQuestion, Skill, Agent or SendMessage (Bash, Read and Edit gather data for the answer);
#   - the user's last typed prompt (an interrupt marker is a prompt that asks for nothing; a slash command's args count) asks to see content:
#     the pattern in hooks/show-request-pattern.txt, which refuse-idle-end-of-turn.sh reads too, so the two agree;
#   - the turn already holds assistant text of 40+ characters, or a list or table, since that prompt;
#   - no earlier call of those tools, answered, follows that text: this is the first call after it.
# Once per turn: a marker file keyed by session id and prompt time under
# ${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/refuse-requested-content-before-tool-call/.
# Fails open: a missing transcript or reader, an unreadable pattern, a reader error or garbage stdin never block.
# The transcript lags the conversation, so when the content is not seen yet the read is repeated up to 3 times,
# 1 second apart, before the call is allowed.
#
# Cases: hooks/tests/run-refuse-requested-content-before-tool-call.sh. Bash, to match the hooks beside it.

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
case "$TOOL" in AskUserQuestion|Skill|Agent|SendMessage) ;; *) exit 0 ;; esac
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}
PATTERN_FILE="$HERE/show-request-pattern.txt"
[ -r "$READER" ] && [ -r "$PATTERN_FILE" ] || exit 0
PATTERN=$(head -n1 "$PATTERN_FILE")
[ -n "$PATTERN" ] || exit 0

# Prints "skip" when the call is allowed whatever is read next, "<prompt time>" when the turn holds requested
# content ahead of this call, nothing when the content is not seen (yet). Return 3 when the transcript could not be read.
verdict() {
    local rows
    rows=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant,agents,calls,tools --json --max-chars 400 2>/dev/null) || return 3
    printf '%s' "$rows" | jq -rs --arg pat "$PATTERN" '
      [ .[] | select(type == "object" and (.sidechain | not)) ] as $rows
      | ([ range(0; $rows | length) as $i | $rows[$i]
           | select(.group == "user" and .label == "USER" and .origin == "human" and (.meta | not)
                    and ((.text // "") | test("^\\s*<(bash-|local-command)") | not)) | $i ] | max // -1) as $p
      | if $p < 0 then "skip" else
        ($rows[$p].text // "" | (capture("<command-args>(?<a>[\\s\\S]*)</command-args>").a // .)) as $prompt
        | if ($prompt | test($pat) | not) then "skip" else
          $rows[$p + 1:] as $turn
          | ([ range(0; $turn | length) as $i | $turn[$i]
               | select(.group == "assistant"
                        and (((.text // "") | length) >= 40
                             or ((.text // "") | test("(?m)^\\s*([-*•]|[0-9]+[.)])\\s+\\S|^\\s*\\|.*\\|")))) | $i ] | first // -1) as $t
          | if $t < 0 then empty else
            ([ range($t + 1; $turn | length) as $i | $turn[$i]
               | select(.label == "ASK" or .label == "CALL Skill" or .label == "SENDMSG" or .label == "AGENT-SPAWN")
               | . as $c
               | select([ $turn[$i + 1:][] | select(.tool_use_id == $c.tool_use_id and (.label | test("^(TOOL-)?RESULT"))) ] | length > 0) ]
             | length) as $answeredAfter
            | if $answeredAfter > 0 then "skip" else $rows[$p].time // "x" end
          end
        end
      end' 2>/dev/null
}

OUT=""
for attempt in 0 1 2 3; do
    OUT=$(verdict); rc=$?
    [ "$rc" = 3 ] && exit 0
    [ "$OUT" = skip ] && exit 0
    [ -n "$OUT" ] && break
    # The prompt asked for content but none is seen: the text may not be written yet.
    [ "$attempt" = 3 ] && exit 0
    sleep 1
done
[ -n "$OUT" ] || exit 0

DIR="${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/refuse-requested-content-before-tool-call"
KEY=$(printf '%s_%s' "${SESSION:-nosession}" "$OUT" | tr -c 'A-Za-z0-9._-' '_')
[ -e "$DIR/$KEY" ] && exit 0
mkdir -p "$DIR" 2>/dev/null && : > "$DIR/$KEY" 2>/dev/null || exit 0

cat >&2 <<MSG
BLOCKED: you were asked to show content and wrote it in the same turn as a tool call. Text before a tool call can be collapsed on the user's screen to one line. End this turn with the content as plain text and no tool call (no proceed question needed). If a decision is also open, state it in that closing text and say the question follows on the user's next message.
MSG
exit 2
