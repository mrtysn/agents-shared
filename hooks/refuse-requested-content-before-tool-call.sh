#!/bin/bash
# DESC: PreToolUse hook on AskUserQuestion|Skill|Agent|SendMessage|Bash|Edit|Write — refuses requested content, or a copy-ready draft, written in the same turn as a tool call, and any change made before the user's question is answered
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
#      - no earlier call of any tool, answered, follows that text: this is the first call after it;
#      - no end of turn follows that text: a Stop-hook feedback row, a task notification or an agent message after it
#        means the reply was finished and shown, and the draft does not count.
#      For Bash, Edit and Write the hook exits at once when the transcript holds no fence, and reads the transcript once.
#   3. work before content: the call is Edit, Write, or a Bash call that is not obviously read-only, and
#      - the user's last typed prompt asks to see content (the same pattern as trigger 1);
#      - the turn holds no delivered content since that prompt: no assistant text of 200+ characters and no two list or
#        table lines. A short announcement ("Finishing the repo sync first, then the list.") is not content.
#      Incident (2026-11-13, session 4218922c-be05-4fef-8b66-67738a973da4): "ok, list me /outstanding and continue" was
#      followed by many Bash and Edit calls and a 45-character announcement before the list, because trigger 1 exempts
#      Bash, Edit and Write and its 40-character text test passed the announcement. A read-only Bash call (ls, cat, grep,
#      git status/log/diff/show, gh ... view/list, jq, sed without -i, no output redirection to a file) gathers the data
#      for the answer and is never refused, which is why the test is the kind of call, not a count of calls: a count would
#      refuse the reads that "list me X" needs, or let a few edits through. The reason says to deliver the content as
#      text first and then continue with the work. Reads the transcript once.
#   4. reply before work: the call is Edit, Write, or a Bash call that is not obviously read-only, and
#      - the user's latest message was queued mid-turn (the reader's USER(queued) row; hand-backs from agents, task
#        notifications, cross-session messages and Stop-hook feedback do not count, and a typed prompt does not trigger);
#      - nothing has replied to it since: no assistant text, and no AskUserQuestion the user answered.
#      The refusal quotes the message and says to reply, then repeat the call. Text written in the same message as the
#      call reaches the transcript only with that call, so the reply is seen by the next call, not this one.
#      Incident (2026-11-15, session e19f1208-233d-48c5-96aa-041940a58196): "what do you mean?" and "I am not alex
#      claude", both queued mid-turn, were followed by a profile written, scripts edited, pages published and commits
#      pushed with no reply; the typed prompt before them had been answered. The first version of this trigger matched
#      questions by wording, in typed and queued messages, and took 80 characters of text as the answer: of its 21
#      refusals that day 14 were false, mostly orders phrased as questions ("when I am on local, give me a toggle",
#      "can you open the correct link") and read-only calls, and a note about other work passed as an answer. Whether a
#      message is a question is judged by the agent under claude/rules/question-handling.md; this trigger checks only
#      that a mid-turn message got a reply. No once-per-turn marker: it ends when the reply exists.
# Reply text written between tool calls can be stored in the transcript as a thinking block holding the server's short
# summary of it, with no text block (2026-11-15, session 75b44d1f-4c1d-4a8f-ad27-84c543a389e5: five of ten replies;
# the reader's NARRATION rows, told from reasoning by the block's signature). Trigger 1 counts a NARRATION row as text
# written ahead of the call, and trigger 4 as a reply to a mid-turn message, since a resumed session draws the
# summary as an ordinary reply line (Claude Code 2.1.325, read from rendered screens). Trigger 3 does not count it as delivered content: the user saw a summary at most. A THINKING row
# is reasoning and counts for nothing.
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
# True when a Bash command is obviously read-only. Quoted strings are dropped, the rest is split into simple commands,
# and each one's first word (after env assignments and cd) must be a known reader. Anything unknown counts as changing.
bash_is_readonly() {
    local cmd=$1 stripped seg w sub
    [ -n "$cmd" ] || return 0
    stripped=$(printf '%s' "$cmd" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
    # output redirection to a file (not /dev/null or an fd copy) changes state
    stripped=$(printf '%s' "$stripped" | sed -E 's#[0-9]*>&[0-9-]+##g; s#&>>?[[:space:]]*/dev/null##g; s#[0-9]*>>?[[:space:]]*/dev/null##g')
    case "$stripped" in *\>*) return 1 ;; esac
    while IFS= read -r seg; do
        seg=$(printf '%s' "$seg" | sed -E 's/^[[:space:]]+//; s/^(\(|\{)[[:space:]]*//; s/^([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)+//')
        [ -n "$seg" ] || continue
        set -f; set -- $seg; set +f
        w=${1##*/}; sub=${2:-}
        case "$w" in
            cd|ls|cat|head|tail|grep|egrep|rg|wc|jq|pwd|stat|which|file|tree|du|df|ps|date|echo|printf|sort|uniq|cut|tr|awk|basename|dirname|realpath|readlink|test|\[|true|false|nl|column|lsof|pgrep|uptime|whoami|hostname|uname|env|type|command|fi|then|else|done|do|for|if|while|\)|\}) ;;
            curl) case " $* " in *" -X"*|*" -d"*|*" --data"*|*" -F"*|*" --form"*|*" -T"*|*" --upload"*|*" -o"*|*" -O"*|*" --output"*|*" --remote-name"*) return 1 ;; esac ;;
            sed) case " $* " in *" -i"*|*" --in-place"*) return 1 ;; esac ;;
            find) case " $* " in *" -delete"*|*" -exec"*|*" -ok"*) return 1 ;; esac ;;
            git) case "$sub" in status|log|diff|show|rev-parse|ls-files|blame|describe|remote|shortlog|ls-remote|cat-file|grep|rev-list|reflog|name-rev|merge-base) ;;
                     submodule) [ "${3:-}" = status ] || return 1 ;;
                     *) return 1 ;; esac ;;
            # The transcript readers in this repo's scripts/ only read, unless told to write a file with --out.
            python|python3)
                case "${sub##*/}" in extract-session-text.py|find-repeated-user-prompts.py) ;; *) return 1 ;; esac
                case " $* " in *" --out"*) return 1 ;; esac ;;
            gh) case "${3:-}" in view|list|status|checks|diff) ;; *) return 1 ;; esac ;;
            *) return 1 ;;
        esac
    done <<EOT
$(printf '%s' "$stripped" | tr '&|;' '\n\n\n')
EOT
    return 0
}

SHOW=false
WORK=false
case "$TOOL" in
    AskUserQuestion|Skill|Agent|SendMessage) SHOW=true ;;
    Edit|Write) WORK=true ;;
    Bash)
        CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
        bash_is_readonly "$CMD" || WORK=true ;;
    *) exit 0 ;;
esac
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0
# A read-only Bash call only matters when a fenced block is in the transcript at all: skip the reader otherwise.
if [ "$SHOW" = false ] && [ "$WORK" = false ]; then grep -q '```' "$TRANSCRIPT" 2>/dev/null || exit 0; fi

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}
PATTERN_FILE="$HERE/show-request-pattern.txt"
[ -r "$READER" ] || exit 0

# Trigger 4: a message the user sent mid-turn gets a reply before the next change. Prints the message when it has none.
if [ "$WORK" = true ]; then
    Q4_MSG=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant,agents,thinking --json --max-chars 400 2>/dev/null | jq -rs '
        [ .[] | select(type == "object" and (.sidechain | not)) ] as $rows
        | ([ range(0; $rows | length) as $i | $rows[$i]
             | select(.group == "user" and (.label == "USER" or .label == "USER(queued)") and (.meta | not)
                      and ((.text // "") | test("^\\s*(<(bash-|local-command|task-notification|agent-message|cross-session-message|system-reminder)|Stop hook feedback:|Base directory for this skill|\\[Request interrupted)") | not)) | $i ] | max // -1) as $p
        | if $p < 0 or $rows[$p].label != "USER(queued)" then "" else
            ($rows[$p + 1:] | any(((.group == "assistant" or .label == "NARRATION") and ((.text // "") | test("\\S")))
                                   or (.label == "RESULT AskUserQuestion" and ((.text // "") | test("answered"))))) as $replied
            | if $replied then "" else ($rows[$p].text // "") end
          end' 2>/dev/null)
    if [ -n "$Q4_MSG" ]; then
        cat >&2 <<MSG
BLOCKED: the user sent a message while you were working, and you have not replied to it:

  ${Q4_MSG:0:300}

Reply to it in text first. Text written in the same message as a tool call is not seen until that call is made, so write the reply, then repeat this call. A question in it gets an answer, not an action (claude/rules/question-handling.md); an order in it, and the work already ordered, carry on after the reply.
MSG
        exit 2
    fi
fi
PATTERN=""
if { [ "$SHOW" = true ] || [ "$WORK" = true ]; } && [ -r "$PATTERN_FILE" ]; then PATTERN=$(head -n1 "$PATTERN_FILE"); fi
if [ -z "$PATTERN" ]; then SHOW=false; WORK=false; fi
# A state-changing Bash, Edit or Write call with no pattern to test still runs the draft check, which needs the fence.
if [ "$SHOW" = false ] && [ "$WORK" = false ]; then grep -q '```' "$TRANSCRIPT" 2>/dev/null || exit 0; fi

# Prints "skip" when the call is allowed whatever is read next, "show<TAB><prompt time>" when the turn holds requested
# content ahead of this call, "draft<TAB><prompt time>" when it holds a fenced draft, "retry" when the prompt asks for
# content that is not seen (yet). Return 3 when the transcript could not be read.
verdict() {
    local rows
    rows=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant,agents,calls,tools,thinking --json --max-chars 400 2>/dev/null) || return 3
    printf '%s' "$rows" | jq -rs --arg pat "$PATTERN" --argjson show "$SHOW" --argjson work "$WORK" '
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
        | (if $work and ($prompt | test($pat)) then
            (if ([ $turn[] | select(.group == "assistant") ]
                 | any(((.text // "") | length) >= 200
                       or (((.text // "") | [ scan("(?m)^\\s*([-*•]|[0-9]+[.)])\\s+\\S|^\\s*\\|.*\\|") ] | length) >= 2)))
                # A question form the user answered is the newer instruction ("give me a toggle", then "Build it").
                or ($turn | any(.label == "RESULT AskUserQuestion" and ((.text // "") | test("answered"))))
             then "skip" else "work\t" + $time end)
          elif ($show | not) or ($prompt | test($pat) | not) then "skip" else
            ([ range(0; $turn | length) as $i | $turn[$i]
               | select((.group == "assistant" or .label == "NARRATION")
                        and (((.text // "") | length) >= 40
                             or ((.text // "") | test("(?m)^\\s*([-*•]|[0-9]+[.)])\\s+\\S|^\\s*\\|.*\\|")))) | $i ] | first // -1) as $t
            | if $t < 0 then "retry" else
              if answered($turn; $t + 1; "^(ASK|CALL Skill|SENDMSG|AGENT-SPAWN)$") > 0 then "skip" else "show\t" + $time end
              end
          end) as $s
        | if ($s | startswith("show") or ($s | startswith("work"))) then $s else
          ([ range(0; $turn | length) as $i | $turn[$i]
             | select(.group == "user" and .origin != "human"
                      and (.label == "NOTIFY" or ((.text // "") | test("^\\s*(Stop hook feedback:|<task-notification|<agent-message)")))) | $i ] | max // -1) as $c
          | $turn[$c + 1:] as $open
          | ([ range(0; $open | length) as $i | $open[$i]
               | select(.group == "assistant" and ((.text // "") | test("(?m)^[ \\t]*```"))) | $i ] | first // -1) as $d
          | if $d >= 0 and answered($open; $d + 1; "^(CALL |ASK$|SENDMSG$|AGENT-SPAWN$)") == 0 then "draft\t" + $time else $s end
        end
      end' 2>/dev/null
}

OUT=""
for attempt in 0 1 2 3; do
    OUT=$(verdict); rc=$?
    [ "$rc" = 3 ] && exit 0
    case "$OUT" in show*|draft*|work*) break ;; esac
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

if [ "$KIND" = work ]; then
cat >&2 <<MSG
BLOCKED: you were asked to show content and have not delivered it: this call changes state before the content is in the turn. Deliver the requested content as text first (the list, table or answer itself; a short announcement does not count), then continue with the work. Content written in the same message as a tool call can be stored, and shown, as a short summary, and then it is not counted as delivered. Reading calls (ls, cat, grep, git status or log) that gather the data for the answer are fine.
MSG
elif [ "$KIND" = draft ]; then
cat >&2 <<MSG
BLOCKED: you wrote a copy-ready draft (a fenced code block) in the same turn as a tool call. Text before a tool call can be collapsed on the user's screen to one line, so the draft may never be seen. End this turn with the draft as the last text and no tool call; do the tool work in the next turn.
MSG
else
cat >&2 <<MSG
BLOCKED: you were asked to show content and wrote it in the same turn as a tool call. Text before a tool call can be collapsed on the user's screen to one line. End this turn with the content as plain text and no tool call (no proceed question needed). If a decision is also open, state it in that closing text as a plain statement. Do not promise a later message or question: you write only after the user does.
MSG
fi
exit 2
