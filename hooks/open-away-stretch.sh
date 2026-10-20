#!/bin/zsh
# UserPromptSubmit hook: the user's `/away` command opens or closes an away stretch for this session.
#
# The failure this exists to prevent (2026-10-19): the user said "keep my machine idle between 8am and 9am
# and then carry on". The agent filed a job for 09:00, ended its turn, nothing woke it, and it sat idle for
# seven hours; the filed job failed unseen. The stretch is declared by an explicit command, never guessed
# from phrasing; hooks/refuse-stop-while-away.sh is the half that holds the agent to it.
#
#   /away until HH:MM [note]   local time, the next time the clock reads it
#   /away for 2h [note]        2h, 90m or 1h30m
#   /away off                  closes the stretch
#   /away                      an error that names the usage; the prompt is not sent
#
# A stretch always ends, at most 12 hours out. Only a prompt that starts with `/away` touches it: any other
# typed prompt, a task notification or a wakeup prompt leaves it as it is. State is kept by
# scripts/away-obligation (see its header); no network, no model call. Fails open and silent when the state
# cannot be written or jq is missing.
#
# Cases: hooks/tests/away-prompt-cases.tsv, run by hooks/tests/run-away-stretch.sh.

HERE=${0:A:h}
OBLIGATION=${AWAY_OBLIGATION:-$HERE/../scripts/away-obligation}

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
PROMPT=$(print -rn -- "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)
SESSION=$(print -rn -- "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[[ -n $PROMPT && -n $SESSION ]] || exit 0

# Only a prompt that starts with /away as a word; leading blanks allowed.
TRIMMED=${PROMPT##[[:space:]]#}
[[ $TRIMMED == /away || $TRIMMED == /away[[:space:]]* ]] || exit 0
[[ -x $OBLIGATION ]] || exit 0

USAGE_TEXT="/away needs a span: '/away until HH:MM' (local time), '/away for 2h' (or 90m, 1h30m), or '/away off'. Add the user's own words after it if useful. A stretch is at most 12 hours."

refuse() {  # error shown to the user; the prompt is dropped
  jq -cn --arg r "$1" '{decision: "block", reason: $r}'
  exit 0
}

FIRST_LINE=${TRIMMED%%$'\n'*}
WORDS=(${=FIRST_LINE})   # WORDS[1] is /away
VERB=${WORDS[2]:-}

case $VERB in
  off)
    if "$OBLIGATION" close --session "$SESSION" --reason "user: /away off" >/dev/null 2>&1; then
      MSG="Away stretch closed by the user."
    else
      MSG="No away stretch was open."
    fi
    jq -cn --arg m "$MSG" '{systemMessage: $m, hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $m}}'
    exit 0
    ;;
  until|for)
    [[ -n ${WORDS[3]:-} ]] || refuse "/away $VERB needs a value. $USAGE_TEXT"
    QUOTE=${FIRST_LINE[1,300]}
    if ! OUT=$("$OBLIGATION" open --session "$SESSION" --quote "$QUOTE" "$VERB" "${WORDS[3]}" 2>&1); then
      refuse "${OUT#away-obligation: }. $USAGE_TEXT"
    fi
    CONTEXT="The user opened an away stretch ($OUT; they said: '$QUOTE'). They are not at the machine, and nobody will answer questions: decide and report. Before ending any turn during the stretch, arm a waiter on the next thing you owe: ScheduleWakeup at its due time, or Bash run_in_background with an until-loop that exits on every end state of the job you filed (ok, failed, cancelled), and read its result when it fires. A Stop hook refuses the end of turn while nothing is armed. If the work is truly finished: away-obligation close --reason '<why>'."
    jq -cn --arg m "Away stretch open $OUT" --arg c "$CONTEXT" \
      '{systemMessage: $m, hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
    exit 0
    ;;
  *)
    refuse "$USAGE_TEXT"
    ;;
esac
