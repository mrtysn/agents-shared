#!/bin/zsh
# UserPromptSubmit hook: the user's `/away` command opens or closes an away stretch for this session.
#
# The failure this exists to prevent (2026-10-19): the user said "keep my machine idle between 8am and 9am
# and then carry on". The agent filed a job for 09:00, ended its turn, nothing woke it, and it sat idle for
# seven hours; the filed job failed unseen. The stretch is declared by an explicit command, never guessed
# from phrasing; hooks/refuse-stop-while-away.sh is the half that holds the agent to it.
#
#   /away until HH:MM [note]   local time, the next time the clock reads it; 11pm and 8:30 am also read
#   /away for 2h [note]        2h, 90m, 1h30m; 2hrs, 2 hours and 1h 30m also read
#   /away off                  closes the stretch
#   /away                      a span that cannot be read: the prompt goes through and the agent is ordered to
#                              ask for the span at once with AskUserQuestion, then open the stretch itself
#
# The verb is case-insensitive. Sentence punctuation after the verb or the value ("/away until 23:00. go",
# "/away off.") is ignored. A bare hour such as 23 or 2300 is not read: it could be a time or a count.
#
# A stretch always ends, at most 12 hours out. Only a prompt that starts with `/away` touches it: any other
# typed prompt, a task notification or a wakeup prompt leaves it as it is. State is kept by
# scripts/away-obligation (see its header); no network, no model call. Fails open and silent when the state
# cannot be written or jq is missing.
#
# Cases: hooks/tests/away-prompt-cases.tsv, run by hooks/tests/run-away-stretch.sh.

setopt extended_glob
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

USAGE_TEXT="/away needs a span: '/away until HH:MM' (local time, or 11pm), '/away for 2h' (or 90m, 1h30m, 2 hours), or '/away off'. A stretch is at most 12 hours."

# A span that cannot be read is not dropped: the user is about to leave and would have to retype. The prompt
# goes through with an order to ask for the span at once and open the stretch from the answer.
ask_span() {  # why
  local line=${FIRST_LINE[1,300]}
  local ctx="The user typed an away command but its span could not be read ($1). They are about to leave. Your first action, before any other work or text, is one AskUserQuestion asking how long they will be away: options such as for 1h, for 2h, until a time of day, and off. Wait for the answer. Then open the stretch yourself: ${OBLIGATION:A} open --session $SESSION --quote '$line' until HH:MM (or for 2h), and follow the stretch rules from then on: arm a waiter before ending any turn, ask no more questions. $USAGE_TEXT"
  jq -cn --arg m "/away: $1. Asking you for the span." --arg c "$ctx" \
    '{systemMessage: $m, hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
  exit 0
}

FIRST_LINE=${TRIMMED%%$'\n'*}
WORDS=(${=FIRST_LINE})   # WORDS[1] is /away
strip_punct() { print -rn -- "${1%%[.,;:!?]##}"; }
VERB=$(strip_punct "${${WORDS[2]:-}:l}")
VALUE=$(strip_punct "${${WORDS[3]:-}:l}")
NEXT=$(strip_punct "${${WORDS[4]:-}:l}")

# Spellings of the same span: "2 hours", "1h 30m", "11 pm" join into one word; "2hrs" becomes 2h, "11pm" becomes 23:00.
if [[ $VERB == for ]]; then
  if [[ $VALUE =~ '^[0-9]+$' && $NEXT =~ '^(hours?|hrs?|h|minutes?|mins?|m)$' ]]; then VALUE=$VALUE$NEXT
  elif [[ $VALUE =~ '^[0-9]+(h|hours?|hrs?)$' && $NEXT =~ '^[0-9]+(m|mins?|minutes?)$' ]]; then VALUE=$VALUE$NEXT; fi
  VALUE=${VALUE//(#b)([0-9]##)(hours|hour|hrs|hr)/${match[1]}h}
  VALUE=${VALUE//(#b)([0-9]##)(minutes|minute|mins|min)/${match[1]}m}
elif [[ $VERB == until ]]; then
  [[ $VALUE =~ '^[0-9]{1,2}(:[0-9]{2})?$' && $NEXT =~ '^(am|pm)$' ]] && VALUE=$VALUE$NEXT
  if [[ $VALUE =~ '^([0-9]{1,2})(:([0-9]{2}))?(am|pm)$' ]]; then
    hour=$match[1]; minute=${match[3]:-00}
    if (( 10#$hour >= 1 && 10#$hour <= 12 )); then
      (( 10#$hour == 12 )) && hour=0
      [[ $match[4] == pm ]] && hour=$(( 10#$hour + 12 ))
      VALUE=$(printf '%02d:%s' $((10#$hour)) $minute)
    fi
  fi
fi

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
    [[ -n $VALUE ]] || ask_span "/away $VERB has no value"
    QUOTE=${FIRST_LINE[1,300]}
    if ! OUT=$("$OBLIGATION" open --session "$SESSION" --quote "$QUOTE" "$VERB" "$VALUE" 2>&1); then
      ask_span "${OUT#away-obligation: }"
    fi
    CONTEXT="The user opened an away stretch ($OUT). They are not at the machine, and nobody will answer questions: decide and report. Before ending any turn during the stretch, arm a waiter on the next thing you owe: ScheduleWakeup at its due time, or Bash run_in_background with an until-loop that exits on every end state of the job you filed (ok, failed, cancelled), and read its result when it fires. A Stop hook refuses the end of turn while nothing is armed. If the work is truly finished: away-obligation close --reason '<why>'."
    jq -cn --arg m "Away stretch open $OUT" --arg c "$CONTEXT" \
      '{systemMessage: $m, hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
    exit 0
    ;;
  *)
    ask_span "${WORDS[2]:+'${WORDS[2]}' is not until, for or off}${WORDS[2]:-no span given}"
    ;;
esac
