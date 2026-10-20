#!/bin/zsh
# DESC: Run the away-stretch hooks (open-away-stretch.sh, refuse-stop-while-away.sh) against their case files
#
# Not run through `bash`: the hooks and this runner are zsh.
set -uo pipefail
zmodload zsh/datetime

HERE=${0:A:h}
OPEN_HOOK=$HERE/../open-away-stretch.sh
STOP_HOOK=$HERE/../refuse-stop-while-away.sh
OBLIGATION=$HERE/../../scripts/away-obligation
PROMPT_CASES=$HERE/away-prompt-cases.tsv
STOP_CASES=$HERE/away-stop-cases.tsv
FIXTURES=$HERE/fixtures/away

verbose=0
case ${1:-} in
  -h|--help) cat <<'USAGE'
usage: run-away-stretch.sh [-v]

Feeds each prompt case to open-away-stretch.sh (a UserPromptSubmit payload) and each stop case to
refuse-stop-while-away.sh (a Stop payload with a fixture transcript, the shell lister stubbed through
SESSION_SHELLS_LISTER and notify through NOTIFY_CMD), each with a state directory of its own, and
compares the verdict and the state file with the expected ones. The clock is fixed with AWAY_NOW.

  -v   print every case, not just failures
USAGE
     exit 0 ;;
  -v|--verbose) verbose=1 ;;
esac

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
export NOTIFY_CMD=$work/notify
cat > $NOTIFY_CMD <<NOTIFY
#!/bin/zsh
print -r -- "\$*" >> $work/notified
NOTIFY
chmod +x $NOTIFY_CMD

# 2026-10-20 03:00 local
now=$(strftime -r '%Y-%m-%d %H:%M' '2026-10-20 03:00')
export AWAY_NOW=$now

fail=0
total=0
report() {  # exit-status name detail
  total=$(( total + 1 ))
  if [[ $1 == 0 ]]; then
    (( verbose )) && print "ok    $2"
  else
    fail=$(( fail + 1 )); print "FAIL  $2: $3"
  fi
  return 0
}

fresh_state() { export AWAY_STATE_DIR=$(mktemp -d $work/state.XXXXXX); rm -f $work/notified; }

# --- prompt cases ---
while IFS=$'\t' read -r name pre prompt want after; do
  [[ -z $name || $name == \#* ]] && continue
  fresh_state
  session=prompt-$total
  [[ $pre == open ]] && $OBLIGATION open --session $session --quote pre until 09:00 >/dev/null
  prompt=$(print -r -- "$prompt")           # decode \n
  payload=$(jq -cn --arg s $session --arg p "$prompt" '{session_id: $s, prompt: $p, hook_event_name: "UserPromptSubmit"}')
  out=$(print -rn -- "$payload" | $OPEN_HOOK)
  got=silent
  if [[ -n $out ]]; then
    if [[ $(print -r -- "$out" | jq -r '.decision // empty') == block ]]; then
      got=error
    else
      ctx=$(print -r -- "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')
      sysmsg=$(print -r -- "$out" | jq -r '.systemMessage // empty')
      case $ctx in
        *"opened an away stretch"*) got=open; [[ $sysmsg == "Away stretch open until "* ]] || got="open without a systemMessage" ;;
        *"closed by the user"*) got=closed ;;
        *"No away stretch"*) got=no-stretch ;;
        *) got="other: $ctx" ;;
      esac
    fi
  fi
  case $($OBLIGATION status --session $session --json | jq -r '.why_not') in
    none) state_got=none ;;
    "") state_got=open ;;
    *) state_got=not-open ;;
  esac
  [[ $got == $want && $state_got == $after ]]
  report $? "prompt: $name" "want $want/$after got $got/$state_got  [$prompt]"
done < $PROMPT_CASES

# --- the CLI ---
fresh_state
$OBLIGATION open --session cap for 30h >/dev/null
end=$($OBLIGATION status --session cap --json | jq -r .end)
[[ $end == $(( now + 43200 )) ]]
report $? "open: a 30h stretch ends 12h out" "end $end, want $(( now + 43200 ))"

$OBLIGATION open --session ex for 1h >/dev/null
[[ $(AWAY_NOW=$(( now + 7200 )) $OBLIGATION status --session ex --json | jq -r .why_not) == expired ]]
report $? "status: expired after its end" "not reported as expired"
[[ $($OBLIGATION open --session until-next quote-unused until 02:00 2>&1) == "away-obligation: open takes"* ]]
report $? "open: stray words are an error" "accepted"
$OBLIGATION open --session nx --quote q until 14:00 >/dev/null
[[ $($OBLIGATION status --session nx --json | jq -r .end) == $(( now + 11 * 3600 )) ]]
report $? "open: 14:00 at 03:00 is 11h out" "end is not 11h out"
$OBLIGATION open --session nx2 --quote q until 02:00 >/dev/null
[[ $($OBLIGATION status --session nx2 --json | jq -r .end) == $(( now + 43200 )) ]]
report $? "open: 02:00 at 03:00 is tomorrow's, so it is capped at 12h" "end is not 12h out"
$OBLIGATION close --session ex --reason "job ok" >/dev/null
[[ $($OBLIGATION status --session ex --json | jq -r .closed_reason) == "job ok" ]]
report $? "close: records the reason" "reason missing"
$OBLIGATION close --session ex >/dev/null 2>&1
[[ $? != 0 ]]
report $? "close: refuses without --reason" "closed without a reason"

# --- stop cases ---
lister=$work/lister
while IFS=$'\t' read -r name stretch refusals active shells fixture want after; do
  [[ -z $name || $name == \#* ]] && continue
  fresh_state
  session=stop-$total
  case $stretch in
    open|closed|expired)
      $OBLIGATION open --session $session --quote "keep my machine idle until 9" for 1h >/dev/null
      for (( i = 0; i < refusals; i++ )); do $OBLIGATION refuse --session $session >/dev/null; done
      [[ $stretch == closed ]] && $OBLIGATION close --session $session --reason test >/dev/null
      if [[ $stretch == expired ]]; then
        jq -c --argjson e $(( now - 60 )) '.end = $e' $AWAY_STATE_DIR/$session.json > $work/s.json \
          && mv $work/s.json $AWAY_STATE_DIR/$session.json
      fi
      ;;
  esac
  case $shells in
    none) printf '#!/bin/zsh\nexit 0\n' > $lister ;;
    shell) printf '#!/bin/zsh\nprint "4242  05:12  sleep 600"\nprint "    4243  05:12  sleep 600"\n' > $lister ;;
    monitor) printf '#!/bin/zsh\nprint "monitor 4242  05:12  until false; do sleep 5; done"\nprint "    4243  05:12  sleep 5"\n' > $lister ;;
    orphan) printf '#!/bin/zsh\nprint "orphan 4242  05:12  sleep 600"\n' > $lister ;;
    fail) printf '#!/bin/zsh\nexit 1\n' > $lister ;;
  esac
  chmod +x $lister
  transcript=$FIXTURES/$fixture.jsonl
  [[ $fixture == unreadable ]] && transcript=$work/does-not-exist.jsonl
  payload=$(jq -cn --arg s $session --arg t $transcript --argjson a $active \
    '{session_id: $s, transcript_path: $t, hook_event_name: "Stop", stop_hook_active: $a}')
  out=$(print -rn -- "$payload" | SESSION_SHELLS_LISTER=$lister $STOP_HOOK)
  got=allow
  if [[ -n $out ]]; then
    [[ $(print -r -- "$out" | jq -r '.decision // empty') == block ]] && got=block || got="other: $out"
  fi
  [[ $got == allow && -s $work/notified ]] && got=allow+notify
  count=-
  [[ -r $AWAY_STATE_DIR/$session.json ]] && count=$(jq -r .refusals $AWAY_STATE_DIR/$session.json)
  [[ $got == $want && $count == $after ]]
  report $? "stop: $name" "want $want/$after got $got/$count"
  if [[ $got == block ]]; then   # the block message carries the quote, the end time and the way out
    reason=$(print -r -- "$out" | jq -r .reason)
    [[ $reason == "Away stretch open (user said: 'keep my machine idle until 9', until "*"). Nothing is armed to wake this session."*"away-obligation close --reason '<why>'." ]]
    report $? "stop: $name (block message)" "message was: $reason"
  fi
done < $STOP_CASES

# the give-up is logged and notified once, however many more attempts follow
fresh_state
$OBLIGATION open --session once --quote q for 1h >/dev/null
$OBLIGATION refuse --session once >/dev/null; $OBLIGATION refuse --session once >/dev/null
printf '#!/bin/zsh\nexit 0\n' > $lister; chmod +x $lister
payload=$(jq -cn --arg t $FIXTURES/no-calls.jsonl '{session_id: "once", transcript_path: $t, stop_hook_active: false}')
for _ in 1 2 3; do print -rn -- "$payload" | SESSION_SHELLS_LISTER=$lister $STOP_HOOK >/dev/null; done
[[ $(wc -l < $work/notified | tr -d ' ') == 1 && $(wc -l < $AWAY_STATE_DIR/log.jsonl | tr -d ' ') == 1 ]]
report $? "stop: the give-up is logged and notified once" "notified $(wc -l < $work/notified | tr -d ' ') times"

if (( fail )); then
  print "$fail of $total cases failed"
  exit 1
fi
print "all $total cases passed"
