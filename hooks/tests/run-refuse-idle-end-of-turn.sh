#!/bin/zsh
# DESC: Run refuse-idle-end-of-turn.sh against built transcripts and real transcript tails, checking block or pass
#
# Built cases write a small transcript (a typed prompt, then the assistant's rows) and feed the hook a Stop
# payload pointing at it. Real cases cut a recorded transcript at the line where a bad turn ended; they are
# listed in fixtures/idle-end-of-turn-real.tsv (session id, last line, want, name) and skipped when that
# transcript is not on this machine. -v prints every case, not just failures.
set -uo pipefail

HERE=${0:A:h}
HOOK=$HERE/../refuse-idle-end-of-turn.sh
REAL=$HERE/fixtures/idle-end-of-turn-real.tsv
verbose=0
[[ ${1:-} == -v ]] && verbose=1

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
fail=0
total=0
skipped=0

# No away stretch unless a case says so.
print -r -- $'#!/bin/zsh\nprint \'{"open": false}\'' > $work/away-closed; chmod +x $work/away-closed
print -r -- $'#!/bin/zsh\nprint \'{"open": true}\'' > $work/away-open; chmod +x $work/away-open
export AWAY_OBLIGATION=$work/away-closed

row() {  # type json-content [origin-kind]
  jq -cn --arg t $1 --argjson c "$2" --arg o "${3:-human}" '{parentUuid: null, isSidechain: false, uuid: "u",
    timestamp: "2026-10-28T05:00:00.000Z", userType: "external", entrypoint: "cli", cwd: "/tmp/idle-fixture",
    sessionId: "00000000-0000-4000-8000-000000000003", version: "2.1.299", type: $t}
    + (if $t == "user" then {origin: {kind: $o}} else {} end) + {message: {role: $t, content: $c}}'
}
prompt() { row user "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')"; }
say() { row assistant "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')"; }
call() {  # id tool input-json
  row assistant "$(jq -cn --arg i $1 --arg n $2 --argjson in "$3" '[{type: "tool_use", id: $i, name: $n, input: $in}]')"
}
result() {  # id text
  row user "$(jq -cn --arg i $1 --arg x "$2" '[{type: "tool_result", tool_use_id: $i, content: $x}]')"
}
ask() { call toolu_q AskUserQuestion '{"questions":[{"question":"Next?","header":"Next","options":[{"label":"Build it"},{"label":"Stop here"}],"multiSelect":true}]}'; }
answered() { result toolu_q "Your questions have been answered: \"Next?\"=\"${1:-Build it}\""; }
bash_call() { call toolu_b$1 Bash "{\"command\":\"echo $1\"${2:+,\"run_in_background\":true}}"; }
spawn() { call toolu_a$1 Agent '{"description":"do a thing","prompt":"do it","model":"sonnet"}'; }
handback() { jq -cn --arg x "<agent-message from=\"a$1\">\n[Subagent hand-back] done" '{type: "queue-operation", operation: "enqueue",
    timestamp: "2026-10-28T05:01:00.000Z", sessionId: "00000000-0000-4000-8000-000000000003", content: $x}'; }
notify() { row user "$(jq -cn --arg x "<task-notification>\n<task-id>t$1</task-id>\n<tool-use-id>toolu_b$1</tool-use-id>\n<status>completed</status>\n</task-notification>" '$x')" task-notification; }

check() {  # name want active transcript-lines...
  local name=$1 want=$2 active=$3; shift 3
  local t=$work/$total.jsonl
  print -rl -- "$@" > $t
  run_case "$name" $want $active $t
}

run_case() {  # name want active transcript
  local name=$1 want=$2 active=$3 t=$4 out got=pass
  out=$(jq -cn --arg p $t --argjson a $active '{session_id: "s", transcript_path: $p, stop_hook_active: $a, hook_event_name: "Stop"}' | $HOOK)
  [[ $(print -r -- "$out" | jq -r '.decision // empty' 2>/dev/null) == block ]] && got=block
  total=$(( total + 1 ))
  if [[ $got == $want ]]; then (( verbose )) && print "ok    $name"
  else fail=$(( fail + 1 )); print "FAIL  $name: want $want got $got"; fi
}

REPORT=$'The camera fretboard is built, committed and pushed (ec98b6d).\n\n**Your steps**\n- Open Music Playground and go to Guitar → Practice.\n- Earlier steps, still open: loopback latency, a real .nam capture.'
SOURCES=$'I found four public sets with real guitar footage and known string and fret.\n\nSources:\n- [Guitar-TECHS](https://guitar-techs.github.io)\n- [GuitarSet](https://archives.ismir.net/ismir2018/paper/000188.pdf)'
CHOICE=$'Nothing is being set up yet. What I\'d set up, if you want it, is a way to measure accuracy. The choice that shapes it is where the answer key comes from.'
ANNOUNCE=$'Both renders pass. I\'ll render a tall-phone aspect too.'
GOAHEAD=$'The skill is drafted. Say go ahead and I\'ll edit its SKILL.md.'
STEPS=$'To do that I need from Ecem: her CV and the signed form.'
DONE=$'Committed and pushed (ab12cd3).\n\nNothing left: the fix is in and the tests pass.'
DONE_OFFER=$'Committed.\n\nWant me to also add a test?\nNothing left otherwise.'

check "report of user steps, nothing asked"          block false "$(prompt 'build T14')" "$(bash_call 1)" "$(say $REPORT)"
check "research answer, nothing asked"               block false "$(prompt 'find videos with guitars with known ground truths?')" "$(say $SOURCES)"
check "choice posed in prose"                        block false "$(prompt 'what are we setting up? why have you stopped?')" "$(say $CHOICE)"
check "announced next step, then ended"              block false "$(prompt 'render it')" "$(bash_call 1)" "$(say $ANNOUNCE)"
check "permission asked in prose for settled work"   block false "$(prompt 'improve the skill')" "$(say $GOAHEAD)"
check "user-steps list"                              block false "$(prompt 'apply for her')" "$(say $STEPS)"
check "slash-command answer, nothing asked"          block false "$(prompt $'<command-message>be-literal</command-message>\n<command-name>/be-literal</command-name>\n<command-args>why had you stopped?</command-args>')" "$(say 'I stopped because the answer was the whole task as I read it.')"
check "ended on an answered question"                pass  false "$(prompt 'what next?')" "$(say 'Two items remain.')" "$(ask)" "$(answered 'Stop here')" "$(say 'Stopping here.')"
check "worked after the answer, then reported"       block false "$(prompt 'what next?')" "$(ask)" "$(answered)" "$(bash_call 1)" "$(say 'Built and committed.')"
check "answered, then a prose offer"                 block false "$(prompt 'what next?')" "$(ask)" "$(answered 'Stop here')" "$(say 'Stopping. Want me to clean up the branch?')"
check "background agent still running"               pass  false "$(prompt 'fix the setup')" "$(spawn 1)" "$(say 'Findings come when it reports.')"
check "background agent reported, nothing asked"     block false "$(prompt 'fix the setup')" "$(spawn 1)" "$(handback 1)" "$(say 'It fixed the setup in three commits.')"
check "one of two agents reported"                   pass  false "$(prompt 'fix both')" "$(spawn 1)" "$(spawn 2)" "$(handback 1)" "$(say 'One is back; waiting on the other.')"
check "background shell still running"               pass  false "$(prompt 'run the suites')" "$(bash_call 1 bg)" "$(say 'The suites run for about 10 minutes; I will read them when they finish.')"
check "background shell finished, nothing asked"     block false "$(prompt 'run the suites')" "$(bash_call 1 bg)" "$(notify 1)" "$(say 'All suites pass.')"
check "wakeup armed"                                 pass  false "$(prompt 'check at 9')" "$(call toolu_w ScheduleWakeup '{"delaySeconds":600,"prompt":"check the job"}')" "$(say 'I will check at 09:00.')"
check "nothing left line"                            pass  false "$(prompt 'commit it')" "$(bash_call 1)" "$(say $DONE)"
check "nothing left line under a prose offer"        block false "$(prompt 'commit it')" "$(say $DONE_OFFER)"
check "trigger phrase in double quotes"              pass  false "$(prompt 'why did the hook fire?')" "$(say $'It matched "tell me to" in my last answer.\n\nNothing left: that was all you asked.')"
check "trigger phrase in backticks"                  pass  false "$(prompt 'why did the hook fire?')" "$(say $'It matched `want me to` in my last answer.\n\nNothing left: that was all you asked.')"
check "offer beside a quoted phrase"                 block false "$(prompt 'why did the hook fire?')" "$(say $'It matched "tell me to". Want me to fix it?')"
check "user said stop"                               pass  false "$(prompt 'stop')" "$(say 'Stopped. The branch is left as it was.')"
check "user said that's all"                         pass  false "$(prompt "that's all for today")" "$(say 'Done.')"
check "already continuing (stop_hook_active)"        pass  true  "$(prompt 'build it')" "$(say $REPORT)"
check "missing transcript"                           pass  false

AWAY_OBLIGATION=$work/away-open check "away stretch open"  pass  false "$(prompt 'build it')" "$(say $REPORT)"

# Real tails: cut the recorded transcript at the last line of the turn and run the hook on it.
if [[ -r $REAL ]]; then
  while IFS=$'\t' read -r sid last want name; do
    [[ -z $sid || $sid == \#* ]] && continue
    src=( ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/*/$sid.jsonl(N) )
    if (( ! $#src )); then skipped=$(( skipped + 1 )); continue; fi
    t=$work/real-$total.jsonl
    head -n $last $src[1] > $t
    run_case "real: $name" $want false $t
  done < $REAL
fi

(( verbose || fail )) && print
print "$(( total - fail ))/$total passed$( (( skipped )) && print ", $skipped real cases skipped (transcript not on this machine)")"
(( fail == 0 ))
