#!/bin/zsh
# Stop hook: during an away stretch, refuse to let the session end its turn while nothing is armed to wake it.
#
# The stretch is opened by the user's `/away` command (hooks/open-away-stretch.sh; state kept by
# scripts/away-obligation). The failure this prevents (2026-10-19): the agent filed a job for 09:00 and ended
# its turn; nothing woke it, so it sat idle for seven hours and the job's failure went unseen.
#
# Something is *armed* when either
#   - a live background shell of this session exists (scripts/list-session-background-shells.sh;
#     SESSION_SHELLS_LISTER replaces it): a plain shell only, never a `monitor` or `orphan` block, because a
#     Monitor's events do not wake an idle session, or
#   - a ScheduleWakeup or CronCreate call stands since the user last spoke (scripts/extract-session-text.py
#     --since-last-user; never a hand-rolled transcript parser). A wakeup that has already fired (its prompt came
#     back as a META row), and any wakeup before a `ScheduleWakeup {stop: true}`, no longer counts; a CronCreate
#     with `recurring: false` is treated like a wakeup.
#
# Then it blocks: {"decision":"block","reason":...} with the facts and the way out. It lets the stop through when
#   - stop_hook_active is true (the session is already continuing because of a Stop hook),
#   - two refusals were already made in this stretch (it logs that, once, and runs `notify`),
#   - no stretch is open, it is closed, or its end time is past,
#   - the shell lister or the transcript reader fails: it never blocks on a read it could not make.
# Refusals are counted per stretch, across turns, in the state file. No network, no model call.
#
# Cases: hooks/tests/away-stop-cases.tsv, run by hooks/tests/run-away-stretch.sh.

HERE=${0:A:h}
OBLIGATION=${AWAY_OBLIGATION:-$HERE/../scripts/away-obligation}
SHELLS_LISTER=${SESSION_SHELLS_LISTER:-$HERE/../scripts/list-session-background-shells.sh}
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}
NOTIFY=${NOTIFY_CMD:-$HOME/bin/notify}
MAX_REFUSALS=2

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
[[ $(print -rn -- "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null) == true ]] && exit 0
SESSION=$(print -rn -- "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
TRANSCRIPT=$(print -rn -- "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[[ -n $SESSION ]] || exit 0
[[ -x $OBLIGATION ]] || exit 0

STATE=$("$OBLIGATION" status --session "$SESSION" --json 2>/dev/null) || exit 0
[[ $(print -rn -- "$STATE" | jq -r '.open // false' 2>/dev/null) == true ]] || exit 0
REFUSALS=$(print -rn -- "$STATE" | jq -r '.refusals // 0' 2>/dev/null) || exit 0
QUOTE=$(print -rn -- "$STATE" | jq -r '.quote // ""')
END_HHMM=$(print -rn -- "$STATE" | jq -r '.end_hhmm // ""')
STATE_DIR=${AWAY_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/agents-shared/away}

# --- armed? ---
[[ -x $SHELLS_LISTER ]] || exit 0
SHELLS=$("$SHELLS_LISTER" --session "$SESSION" 2>/dev/null) || exit 0
# Top-level lines are shells; a child is indented, a Monitor or an orphan carries a label first.
[[ -n $(print -r -- "$SHELLS" | grep -E '^[0-9]') ]] && exit 0

[[ -r $TRANSCRIPT && -r $READER ]] || exit 0
ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds calls,user --since-last-user --json 2>/dev/null) || exit 0
ARMED=$(print -r -- "$ROWS" | jq -rs '
  . as $rows
  | ([ range(0; length) as $i | $rows[$i]
       | select(.group == "calls" and .tool == "ScheduleWakeup" and (.input.stop // false)) | $i ] | max // -1) as $stopped
  | [ range(0; length) as $i | $rows[$i] as $r
      | select($i > $stopped and $r.group == "calls"
               and (($r.tool == "ScheduleWakeup" and (($r.input.stop // false) | not))
                    or $r.tool == "CronCreate"))
      | ($r.input.prompt // "") as $p
      | select(($r.tool == "CronCreate" and (($r.input.recurring // true) != false))
               or ($p == "")
               or ([ range($i + 1; $rows | length) as $j | $rows[$j]
                     | select(.label == "META" and (.text | startswith($p[0:60]))) ] | length == 0)) ]
  | length' 2>/dev/null) || exit 0
[[ $ARMED == <-> ]] || exit 0
(( ARMED > 0 )) && exit 0

# --- nothing armed ---
if (( REFUSALS >= MAX_REFUSALS )); then
  if [[ $(print -rn -- "$STATE" | jq -r '.gave_up // false') != true ]]; then
    "$OBLIGATION" give-up --session "$SESSION" >/dev/null 2>&1
    mkdir -p "$STATE_DIR" 2>/dev/null
    jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg s "$SESSION" --arg q "$QUOTE" --argjson n "$REFUSALS" \
      '{ts: $ts, session_id: $s, event: "stop allowed after refusals", refusals: $n, quote: $q}' >> "$STATE_DIR/log.jsonl" 2>/dev/null
    "$NOTIFY" away-hook 1 "A session in an away stretch ended its turn with nothing armed to wake it (refused $REFUSALS times): $QUOTE" >/dev/null 2>&1
  fi
  exit 0
fi

"$OBLIGATION" refuse --session "$SESSION" >/dev/null 2>&1 || exit 0
REASON="Away stretch open (user said: '$QUOTE', until $END_HHMM). Nothing is armed to wake this session. Arm a waiter on the next thing you owe: ScheduleWakeup at its due time, or Bash run_in_background with an until-loop that exits on every end state of the job you filed (ok, failed, cancelled). Read its result when it fires. Ask no questions during this stretch; decide and report. If the work is truly finished: away-obligation close --reason '<why>'."
jq -cn --arg r "$REASON" '{decision: "block", reason: $r}'
