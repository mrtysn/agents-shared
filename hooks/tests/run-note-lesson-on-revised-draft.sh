#!/bin/zsh
# DESC: Run note-lesson-on-revised-draft.sh against built transcripts and check block or pass for each case
#
# Each case writes a small transcript (typed prompts and assistant rows) and feeds the hook a Stop payload
# pointing at it. -v prints every case, not just failures.
set -uo pipefail

HERE=${0:A:h}
HOOK=$HERE/../note-lesson-on-revised-draft.sh
verbose=0
[[ ${1:-} == -v ]] && verbose=1

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
fail=0
total=0

row() {  # type json-content
  jq -cn --arg t $1 --argjson c "$2" '{parentUuid: null, isSidechain: false, uuid: "u", timestamp: "2026-11-12T05:00:00.000Z",
    userType: "external", entrypoint: "cli", cwd: "/tmp/draft-fixture", sessionId: "00000000-0000-4000-8000-000000000003",
    version: "2.1.292", type: $t} + (if $t == "user" then {origin: {kind: "human"}} else {} end)
    + {message: {role: $t, content: $c}}'
}
prompt() { row user "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')"; }
say() { row assistant "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')"; }

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

DISCORD=$'Draft:\n\n```\nHello all,\n\nWe re-ordered the priorities.\n```'
DISCORD2=$'Revised:\n\n```\nHello all,\n\nThe image shows the new order.\n```'
MENTION=$'```\n@Ege thanks for the builds, could you add me to the repositories?\n```'
EMAIL=$'```\nHi Alex,\n\nThursday works.\n\nBest,\nSam\n```'
TURKISH=$'```\nEge selamlar nasılsın?\n\nBir şey sormak istedim.\n```'
DECORATOR=$'```\n@app.route("/health")\ndef health(): return "ok"\n```'
JAVA=$'```\n@Override public String toString() { return name; }\n```'
CODE=$'```\nhi = 1\n```'

check "discord draft revised after a prompt"        block false "$(prompt 'reply to them')" "$(say $DISCORD)" "$(prompt 'no need to say that')" "$(say $DISCORD2)"
check "email draft revised"                         block false "$(prompt 'draft it')" "$(say $EMAIL)" "$(prompt 'shorter')" "$(say $EMAIL)"
check "mention draft revised"                       block false "$(prompt 'ask ege')" "$(say $MENTION)" "$(prompt 'why tag him')" "$(say $MENTION)"
check "turkish dm revised"                          block false "$(prompt 'draft in turkish')" "$(say $TURKISH)" "$(prompt 'no circumflex')" "$(say $TURKISH)"
check "first draft only"                            pass  false "$(prompt 'reply to them')" "$(say $DISCORD)"
check "draft, then a non-draft reply"               pass  false "$(prompt 'reply')" "$(say $DISCORD)" "$(prompt 'thanks')" "$(say 'Filed.')"
check "draft two prompts back, not the last turn"   pass  false "$(prompt 'reply')" "$(say $DISCORD)" "$(prompt 'file it')" "$(say 'Filed.')" "$(prompt 'next')" "$(say $DISCORD2)"
check "decorator code blocks are not messages"      pass  false "$(prompt 'fix')" "$(say $DECORATOR)" "$(prompt 'again')" "$(say $DECORATOR)"
check "java annotation is not a message"            pass  false "$(prompt 'fix')" "$(say $JAVA)" "$(prompt 'again')" "$(say $JAVA)"
check "ordinary code is not a message"              pass  false "$(prompt 'fix')" "$(say $CODE)" "$(prompt 'again')" "$(say $CODE)"
check "already continuing (stop_hook_active)"       pass  true  "$(prompt 'reply')" "$(say $DISCORD)" "$(prompt 'shorter')" "$(say $DISCORD2)"
check "missing transcript"                          pass  false

(( verbose || fail )) && print
print "$(( total - fail ))/$total passed"
(( fail == 0 ))
