#!/bin/bash
# DESC: PreToolUse hook on AskUserQuestion|Skill|Agent|SendMessage|Bash|Edit|Write — refuses requested content, or a copy-ready draft, written in the same turn as a tool call
#
# The failure this prevents (survey of 12 sessions since 2026-09-11, 14 instances): the user asked to see content
# ("list me all the names you suggested chronologically", "give me the text already", "claude why do you ignore my
# table request"), and the agent wrote it as text in the same turn as a following AskUserQuestion, Skill or Agent
# call. The screen collapses text written before a tool call to one summary line, so the user saw a summary where
# the content should be and asked again. The cause was upstream: claude/rules/end-every-turn-with-a-next-step.md
# pushes every turn to end in AskUserQuestion, so requested content got attached to a question.
#
# A second failure, same mechanism: the user asked for no content, but the agent wrote a copy-ready draft (an email, a
# message in a fenced code block) and then ran a Bash call (a git commit) in the same turn. The draft was collapsed to
# one line and never seen. The prompt was a correction, not a "show me", so the first trigger did not fire.
#
# Refused (exit 2), once per turn, when either trigger holds:
#   1. show request: the call is AskUserQuestion, Skill, Agent or SendMessage (Bash, Read and Edit gather data for the
#      answer), and
#      - the user's last typed prompt (an interrupt marker is a prompt that asks for nothing; a slash command's args count) asks to see content:
#        the pattern in hooks/show-request-pattern.txt, which refuse-idle-end-of-turn.sh reads too, so the two agree;
#      - the turn already holds assistant text of 40+ characters, or a list or table, since that prompt;
#      - no earlier call of those tools, answered, follows that text: this is the first call after it.
#   2. draft: the call is AskUserQuestion, Skill, Agent, SendMessage, Bash, Edit or Write, whatever the prompt says, and
#      - the turn holds assistant text with a fenced code block (a line starting with three backticks) since the last typed prompt;
#      - no earlier call of any tool, answered, follows that text: this is the first call after it.
#      For Bash, Edit and Write the hook exits at once when the transcript holds no fence, and reads the transcript once.
# Once per turn: a marker file keyed by session id and prompt time under
# ${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/refuse-requested-content-before-tool-call/.
# A call made by a sub-agent (the input carries agent_id) is never refused.
# Fails open: a missing transcript or reader, an unreadable pattern, a reader error or garbage stdin never block.
# The transcript lags the conversation, so for trigger 1 (the four tools), when the prompt asks for content that is not seen
# yet, the read is repeated up to 3 times, 1 second apart, before the call is allowed. Trigger 2 reads once.
#
# Cases: hooks/tests/run-refuse-requested-content-before-tool-call.sh. Bash, to match the hooks beside it.

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0

TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
# A sub-agent's input carries agent_id and the parent's transcript path: its calls are not the parent's turn, and no
# one reads a sub-agent's text before them.
[ -z "$(printf '%s' "$INPUT" | jq -r '.agent_id // empty' 2>/dev/null)" ] || exit 0
SHOW=false
case "$TOOL" in
    AskUserQuestion|Skill|Agent|SendMessage) SHOW=true ;;
    Bash|Edit|Write) ;;
    *) exit 0 ;;
esac
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0
# Bash, Edit and Write only matter when a fenced block is in the transcript at all: skip the reader otherwise.
if [ "$SHOW" = false ]; then grep -q '```' "$TRANSCRIPT" 2>/dev/null || exit 0; fi

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}
PATTERN_FILE="$HERE/show-request-pattern.txt"
[ -r "$READER" ] || exit 0
PATTERN=""
if [ "$SHOW" = true ] && [ -r "$PATTERN_FILE" ]; then PATTERN=$(head -n1 "$PATTERN_FILE"); fi
if [ "$SHOW" = true ] && [ -z "$PATTERN" ]; then SHOW=false; fi

# Prints "skip" when the call is allowed whatever is read next, "show<TAB><prompt time>" when the turn holds requested
# content ahead of this call, "draft<TAB><prompt time>" when it holds a fenced draft, "retry" when the prompt asks for
# content that is not seen (yet). Return 3 when the transcript could not be read.
verdict() {
    local rows
    rows=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant,agents,calls,tools --json --max-chars 400 2>/dev/null) || return 3
    printf '%s' "$rows" | jq -rs --arg pat "$PATTERN" --argjson show "$SHOW" '
      def answered($turn; $from; $pred):
        [ range($from; $turn | length) as $i | $turn[$i]
          | select(.label | test($pred))
          | . as $c
          | select([ $turn[$i + 1:][] | select(.tool_use_id == $c.tool_use_id and (.label | test("^(TOOL-)?RESULT"))) ] | length > 0) ]
        | length;
      [ .[] | select(type == "object" and (.sidechain | not)) ] as $rows
      | ([ range(0; $rows | length) as $i | $rows[$i]
           | select(.group == "user" and .label == "USER" and .origin == "human" and (.meta | not)
                    and ((.text // "") | test("^\\s*<(bash-|local-command)") | not)) | $i ] | max // -1) as $p
      | if $p < 0 then "skip" else
        ($rows[$p].text // "" | (capture("<command-args>(?<a>[\\s\\S]*)</command-args>").a // .)) as $prompt
        | ($rows[$p].time // "x") as $time
        | $rows[$p + 1:] as $turn
        | (if ($show | not) or ($prompt | test($pat) | not) then "skip" else
            ([ range(0; $turn | length) as $i | $turn[$i]
               | select(.group == "assistant"
                        and (((.text // "") | length) >= 40
                             or ((.text // "") | test("(?m)^\\s*([-*•]|[0-9]+[.)])\\s+\\S|^\\s*\\|.*\\|")))) | $i ] | first // -1) as $t
            | if $t < 0 then "retry" else
              if answered($turn; $t + 1; "^(ASK|CALL Skill|SENDMSG|AGENT-SPAWN)$") > 0 then "skip" else "show\t" + $time end
              end
          end) as $s
        | if ($s | startswith("show")) then $s else
          ([ range(0; $turn | length) as $i | $turn[$i]
             | select(.group == "assistant" and ((.text // "") | test("(?m)^[ \\t]*```"))) | $i ] | first // -1) as $d
          | if $d >= 0 and answered($turn; $d + 1; "^(CALL |ASK$|SENDMSG$|AGENT-SPAWN$)") == 0 then "draft\t" + $time else $s end
        end
      end' 2>/dev/null
}

OUT=""
for attempt in 0 1 2 3; do
    OUT=$(verdict); rc=$?
    [ "$rc" = 3 ] && exit 0
    case "$OUT" in show*|draft*) break ;; esac
    # Only the four tools wait for text still being written, and only when the prompt asked for content.
    [ "$OUT" = retry ] && [ "$attempt" != 3 ] || exit 0
    sleep 1
done
KIND=${OUT%%$'\t'*}
STAMP=${OUT#*$'\t'}
[ -n "$STAMP" ] || exit 0

DIR="${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/refuse-requested-content-before-tool-call"
KEY=$(printf '%s_%s' "${SESSION:-nosession}" "$STAMP" | tr -c 'A-Za-z0-9._-' '_')
[ -e "$DIR/$KEY" ] && exit 0
mkdir -p "$DIR" 2>/dev/null && : > "$DIR/$KEY" 2>/dev/null || exit 0

if [ "$KIND" = draft ]; then
cat >&2 <<MSG
BLOCKED: you wrote a copy-ready draft (a fenced code block) in the same turn as a tool call. Text before a tool call can be collapsed on the user's screen to one line, so the draft may never be seen. End this turn with the draft as the last text and no tool call; do the tool work in the next turn.
MSG
else
cat >&2 <<MSG
BLOCKED: you were asked to show content and wrote it in the same turn as a tool call. Text before a tool call can be collapsed on the user's screen to one line. End this turn with the content as plain text and no tool call (no proceed question needed). If a decision is also open, state it in that closing text and say the question follows on the user's next message.
MSG
fi
exit 2
