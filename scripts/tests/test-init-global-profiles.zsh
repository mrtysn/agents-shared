#!/bin/zsh
# DESC: Test init-global.sh's profile switch: personal/ content linked only on the personal profile
set -uo pipefail

repo=${0:A:h:h:h}
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT
export XDG_CONFIG_HOME=$work/xdg CLAUDE_CONFIG_DIR=$work/cfg
mkdir -p $CLAUDE_CONFIG_DIR

pskills=($repo/claude/skills/personal/*(N/))
prules=($repo/claude/rules/personal/*.md(N))
(( ${#pskills} && ${#prules} )) || { print "no personal/ content to test with"; exit 1; }
one_skill=${pskills[1]:t} one_rule=${prules[1]:t}

pass=0 fail=0
check() {  # check <label> <condition...>
  local label=$1; shift
  if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); print -r -- "FAIL $label"; fi
}
install() { bash $repo/scripts/init-global.sh > $work/out 2>&1 || { cat $work/out; return 1; } }

check "unset profile installs" install
check "unset: personal skill not linked" test ! -e $CLAUDE_CONFIG_DIR/skills/$one_skill
check "unset: personal rule not linked" test ! -e $CLAUDE_CONFIG_DIR/rules/$one_rule
check "unset: personal/ folder itself not linked" test ! -e $CLAUDE_CONFIG_DIR/skills/personal
check "unset: shared rule linked" test -L $CLAUDE_CONFIG_DIR/rules/question-handling.md

print 'AGENT_PROFILE=personal' > $CLAUDE_CONFIG_DIR/paths.local.sh
check "personal installs" install
check "personal: skill linked" test -L $CLAUDE_CONFIG_DIR/skills/$one_skill
check "personal: rule linked" test -L $CLAUDE_CONFIG_DIR/rules/$one_rule

print 'AGENT_PROFILE="work"   # the laptop' > $CLAUDE_CONFIG_DIR/paths.local.sh
check "work installs" install
check "work: skill link removed" test ! -e $CLAUDE_CONFIG_DIR/skills/$one_skill -a ! -L $CLAUDE_CONFIG_DIR/skills/$one_skill
check "work: rule link removed" test ! -L $CLAUDE_CONFIG_DIR/rules/$one_rule
check "work: summary counts the removals" grep -q 'out of profile' $work/out

print 'AGENT_PROFILE=persnal' > $CLAUDE_CONFIG_DIR/paths.local.sh
check "a misspelt profile refuses to install" eval '! install'

print "init-global profiles: $pass passed, $fail failed"
(( fail == 0 ))
