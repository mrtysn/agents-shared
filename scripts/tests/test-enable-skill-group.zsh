#!/bin/zsh
# DESC: Test enable-skill-group.zsh against a stub claude CLI: its refusals, the switch it runs, and its log
set -uo pipefail

repo=${0:A:h:h:h}
script=$repo/scripts/enable-skill-group.zsh
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT

# A stub claude that records its arguments and the folder it ran in.
mkdir -p $work/bin
print -r -- '#!/bin/zsh
print -r -- "$PWD $*" >> '$work'/claude-calls' > $work/bin/claude
chmod +x $work/bin/claude
export PATH=$work/bin:$PATH SKILL_GROUP_LOG=$work/log.tsv SKILL_GROUP_CACHE=$work/none.json

target=$work/target
mkdir -p $target/sub && git -C $target init -q
target=$(git -C $target rev-parse --show-toplevel)

pass=0 fail=0
check() {  # check <label> <condition...>
  local label=$1; shift
  if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); print -r -- "FAIL $label"; fi
}
run() { (cd $1 && shift && zsh $script "$@") > $work/out 2>&1 }

check "outside a git repo refuses" eval "! run $work art --reason x"
check "an unknown group refuses" eval "! run $target no-such-group --reason x"
check "a switch without a reason refuses" eval "! run $target art"
check "nothing ran on a refusal" test ! -e $work/claude-calls

check "a group switches on from a subfolder" run $target/sub art --reason "logo work"
check "it ran in the repo root with local scope" grep -qx "$target plugin enable art@skills-dir --scope local" $work/claude-calls
check "it logged the switch with its reason" grep -q "$target	art	on	logo work" $work/log.tsv
check "it tells the agent to ask for /reload-plugins" grep -q 'reload-plugins' $work/out

check "a group switches off" run $target art --off --reason "done"
check "the off switch ran" grep -qx "$target plugin disable art@skills-dir --scope local" $work/claude-calls
check "--list shows both switches" eval "run $target --list && grep -c '  art ' $work/out | grep -qx 2"

mkdir -p $target/.claude && print '{}' > $target/.claude/settings.local.json
git -C $target add -f .claude/settings.local.json
calls_before=$(wc -l < $work/claude-calls)
check "a repo that commits settings.local.json refuses" eval "! run $target art --reason x"
check "the refusal says to ask the user" grep -q 'Ask the user' $work/out
check "nothing ran for the tracked file" test "$(wc -l < $work/claude-calls)" = "$calls_before"

print "enable-skill-group: $pass passed, $fail failed"
(( fail == 0 ))
