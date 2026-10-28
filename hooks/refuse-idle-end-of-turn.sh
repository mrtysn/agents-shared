#!/bin/zsh
# Stop hook: refuse, once per turn, an end of turn that leaves the session idle with a next step untaken and
# unasked.
#
# The failure this prevents (2026-10-28, music-playground): a feature was finished and installed, and the turn
# ended on a report whose open items were the user's hardware steps. The user asked a research question; the
# answer pointed at the obvious next work, and the turn ended. The user asked "why have you stopped?"; the reply
# named "the choice that shapes it" in prose and ended again. Mined logs: 122 typed nudges ("continue", "why did
# you stop") in 66 sessions in a month, and /ask-open-decisions typed by hand 408 times in 34 days.
#
# It blocks ({"decision":"block"}) when the last assistant text
#   - offers work or poses a choice in prose ("want me to", "say the word", "if you'd like", "the choice is"),
#     whatever else holds (text inside quotation marks or backticks is not read: a reply that quotes a phrase to
#     explain it is not making the offer); or
#   - ends the turn idle: no AskUserQuestion answered since the user's last typed prompt with no work after it,
#     no background work launched since that prompt still unreported, and no last line "Nothing left …".
# It lets the stop through when
#   - stop_hook_active is true (the session already continued once because of a Stop hook),
#   - an away stretch is open (hooks/refuse-stop-while-away.sh owns those turns, and they ask nothing),
#   - the user's last prompt tells it to stop ("stop", "that's all", "pause"),
#   - the transcript or the reader cannot be read: it never blocks on a read it could not make.
# Background work is an Agent spawn not set to run in the foreground, a SendMessage that resumed a sub-agent, a
# Bash call with run_in_background or one whose timeout moved it to the background, a Monitor, ScheduleWakeup or CronCreate; it is reported by a task notification
# or a sub-agent hand-back (each hand-back counts, since a resumed agent hands back again under the same id).
# No network, no model call.
#
# Covers claude/rules/end-every-turn-with-a-next-step.md. Cases: hooks/tests/run-refuse-idle-end-of-turn.sh.

HERE=${0:A:h}
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}
OBLIGATION=${AWAY_OBLIGATION:-$HERE/../scripts/away-obligation}

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
[[ $(print -rn -- "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null) == true ]] && exit 0
SESSION=$(print -rn -- "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRANSCRIPT=$(print -rn -- "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[[ -r $TRANSCRIPT && -r $READER ]] || exit 0

if [[ -n $SESSION && -x $OBLIGATION ]]; then
  STATE=$("$OBLIGATION" status --session "$SESSION" --json 2>/dev/null)
  [[ $(print -rn -- "$STATE" | jq -r '.open // false' 2>/dev/null) == true ]] && exit 0
fi

ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant,agents,calls,tools --json --max-chars 400 2>/dev/null) || exit 0

VERDICT=$(print -r -- "$ROWS" | jq -rs '
  def offer: "say the word|(do you |would you )?want me to|would you like me to|shall i |should i (go|proceed|build|run|start|do|edit|add|make|commit|fix|wire|set)|let me know (if|when|whether|which)|tell me (to|if|when|which)|if you.?d like|if you want|if you prefer|ready (to (go|proceed) )?when you are|your call|up to you|(waits?|waiting) (for|on) your (word|go|call|ok)|on your (word|go-ahead|say-so)|the (choice|decision|question)( that [a-z ]+)? (is|here is)|which (one|would you|do you)";
  [ .[] | select(type == "object" and (.sidechain | not)) ] as $rows
  | ([ range(0; $rows | length) as $i | $rows[$i]
       | select(.group == "user" and .label == "USER" and .origin == "human" and (.meta | not)
                and ((.text // "") | test("^\\s*<(bash-|local-command)") | not)) | $i ] | max // -1) as $p
  | if $p < 0 then "pass" else
    ($rows[$p].text // "" | (capture("<command-args>(?<a>[\\s\\S]*)</command-args>").a // .)) as $prompt
    | $rows[$p + 1:] as $turn
    | ([ $turn[] | select(.group == "assistant") | .text ] | last // "") as $text
    | ($text | .[(length - 600 | if . < 0 then 0 else . end):] | gsub("\"[^\"]*\"|`[^`]*`|“[^”]*”"; " ")) as $tail
    | ([ $tail | match(offer; "gi") | .string ] | last // "") as $phrase
    | ([ range(0; $turn | length) as $i | select($turn[$i].label == "RESULT AskUserQuestion") | $i ] | max // -1) as $a
    | ([ $turn[$a + 1:][] | select(.group == "calls" or .label == "AGENT-SPAWN" or .label == "SENDMSG") ] | length) as $workAfterAsk
    | ([ $turn[] | select(
           (.label == "AGENT-SPAWN" and ((.input.run_in_background // true) != false))
           or (.group == "calls" and .tool == "Bash" and (.input.run_in_background // false) == true)
           or (.group == "calls" and (.tool == "Monitor" or .tool == "CronCreate"))
           or (.group == "calls" and .tool == "ScheduleWakeup" and ((.input.stop // false) | not))
           or (.label == "RESULT SendMessage" and ((.text // "") | test("resumedAgentId")))
           or (.label == "TOOL-RESULT Bash" and ((.text // "") | test("moved to the background \\(ID:")))) ] | length) as $launched
    | ([ $turn[] | select(.group == "user") | .text // "" | capture("<agent-message from=\"(?<id>[^\"]+)\"").id ] | length) as $handbacks
    | ([ $turn[] | select(.group == "user") | .text // "" | capture("<tool-use-id>(?<id>[^<]+)</tool-use-id>").id ]
       | unique | length + $handbacks) as $reported
    | ([ $turn[] | select(.label == "RESULT Agent") ] | length) as $syncDone
    | ([ $text | split("\n")[] | select(test("\\S")) ] | last // "") as $lastLine
    | if $phrase != "" then "offer\t\($phrase)"
      elif ($prompt | length) < 60 and ($prompt | test("^\\s*(stop|stop here|that.?s (all|it)|enough|nothing else|pause|hold on|wait|no more|done for (now|today))\\b"; "i")) then "pass"
      elif $a >= 0 and $workAfterAsk == 0 then "pass"
      elif $launched > ($reported + $syncDone) then "pass"
      elif ($lastLine | test("^[\\s*_>#-]*nothing (else |more )?(is )?left\\b"; "i")) then "pass"
      else "idle" end
    end' 2>/dev/null) || exit 0
[[ -n $VERDICT && $VERDICT != pass ]] || exit 0

ASK="Call AskUserQuestion now: first any open decision, then the proceed question (multiSelect): one option per unfinished part of what the user asked for that you could do next, recommended first and marked (Recommended), and last \"Stop here\". A step only the user can take is an option only when your own remaining work waits on it (a login, a reboot before a test). What the user does with a finished deliverable (upload, paste, send, deploy) is never an option, and neither is work nobody asked for. The ask-open-decisions skill, step 5, has the format. Answering a question still authorizes no edits: offering the follow-up in the question is what replaces stopping."
if [[ $VERDICT == offer* ]]; then
  PHRASE=${VERDICT#offer$'\t'}
  REASON="Your reply ends by offering work or posing a choice in prose (\"$PHRASE\"), which leaves the user to re-type it (claude/rules/end-every-turn-with-a-next-step.md). If it is work already authorized or plainly in scope, do it now instead of asking. Otherwise: $ASK"
else
  REASON="You are ending the turn idle: nothing was asked since the user's last prompt (or work followed the answer), no background work is pending, and the reply does not end with a 'Nothing left' line (claude/rules/end-every-turn-with-a-next-step.md). The user does not want turns that stop for no reason. Do one of these: (1) if authorized work remains that you can do, including anything you said you would do next, do it now; (2) otherwise $ASK (3) if nothing of what the user asked for is left, end with one line: 'Nothing left: <what was delivered>.' Do not list the user's own use of the deliverable before it."
fi
jq -cn --arg r "$REASON" '{decision: "block", reason: $r}'
