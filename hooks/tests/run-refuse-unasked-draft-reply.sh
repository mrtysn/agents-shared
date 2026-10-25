#!/bin/zsh
# DESC: Run refuse-unasked-draft-reply.sh against built transcripts and check block or pass for each case
#
# Each case writes a small transcript (a typed prompt, then the assistant's rows) and feeds the hook a Stop
# payload pointing at it. -v prints every case, not just failures.
set -uo pipefail

HERE=${0:A:h}
HOOK=$HERE/../refuse-unasked-draft-reply.sh
verbose=0
[[ ${1:-} == -v ]] && verbose=1

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
fail=0
total=0

row() {  # type json-content
  jq -cn --arg t $1 --argjson c "$2" '{parentUuid: null, isSidechain: false, uuid: "u", timestamp: "2026-10-25T05:00:00.000Z",
    userType: "external", entrypoint: "cli", cwd: "/tmp/draft-fixture", sessionId: "00000000-0000-4000-8000-000000000002",
    version: "2.1.292", type: $t} + (if $t == "user" then {origin: {kind: "human"}} else {} end)
    + {message: {role: $t, content: $c}}'
}
prompt() { row user "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')"; }
say() { row assistant "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')"; }
ask() { row assistant '[{"type":"tool_use","id":"toolu_q","name":"AskUserQuestion","input":{"questions":[]}}]'; }

check() {  # name want active transcript-lines...
  local name=$1 want=$2 active=$3; shift 3
  local t=$work/$total.jsonl
  print -rl -- "$@" > $t
  local out got=pass
  out=$(jq -cn --arg p $t --argjson a $active '{session_id: "s", transcript_path: $p, stop_hook_active: $a, hook_event_name: "Stop"}' | $HOOK)
  [[ $(print -r -- "$out" | jq -r '.decision // empty' 2>/dev/null) == block ]] && got=block
  total=$(( total + 1 ))
  if [[ $got == $want ]]; then (( verbose )) && print "ok    $name"
  else fail=$(( fail + 1 )); print "FAIL  $name: want $want got $got"; fi
}

DRAFT=$'Here it is:\n\n```\nHi Alex,\n\nThursday 3pm works for me. See you then.\n\nBest regards,\nSam\n```'
TR_DRAFT=$'```\nAyşe selamlar,\n\nPerşembe uygun.\n\nTeşekkürler,\nDeniz\n```'
CODE=$'```\nhi = 1\nbest = 2\n```'
NOSIGN=$'```\nHi Alex,\n\nThursday works.\n```'

check "image prompt, draft, nothing asked"     block false "$(prompt '[Image #1]')" "$(say $DRAFT)"
check "pasted prompt, draft, nothing asked"    block false "$(prompt $'<pasted_content id="a1">\nare you free Thursday?\n</pasted_content id="a1">')" "$(say $DRAFT)"
check "turkish draft"                          block false "$(prompt '[Image #1]')" "$(say $TR_DRAFT)"
check "already continuing (stop_hook_active)"  pass  true  "$(prompt '[Image #1]')" "$(say $DRAFT)"
check "asked with AskUserQuestion first"       pass  false "$(prompt '[Image #1]')" "$(ask)" "$(say $DRAFT)"
check "typed prompt, no paste"                 pass  false "$(prompt 'reword the second line')" "$(say $DRAFT)"
check "image prompt, no draft"                 pass  false "$(prompt '[Image #1]')" "$(say 'The client accepted the scope.')"
check "code block, not a message"              pass  false "$(prompt '[Image #1]')" "$(say $CODE)"
check "greeting without sign-off"              pass  false "$(prompt '[Image #1]')" "$(say $NOSIGN)"
check "question asked before the paste"        block false "$(prompt 'draft it')" "$(ask)" "$(prompt '[Image #2]')" "$(say $DRAFT)"
check "missing transcript"                     pass  false

(( verbose || fail )) && print
print "$(( total - fail ))/$total passed"
(( fail == 0 ))
