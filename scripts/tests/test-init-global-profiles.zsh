#!/bin/zsh
# DESC: Test init-global.sh's profile switch: personal/ content linked only on the personal profile
set -uo pipefail

repo=${0:A:h:h:h}
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT
export XDG_CONFIG_HOME=$work/xdg CLAUDE_CONFIG_DIR=$work/cfg
# An empty dev root: init-global.sh scans $DEV_ROOT for repos that skip the push guard, and on a
# machine with such repos its summary says "denylist", which the denylist checks below read as a warning.
export DEV_ROOT=$work/dev
mkdir -p $CLAUDE_CONFIG_DIR $DEV_ROOT

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

mkdir -p $CLAUDE_CONFIG_DIR/hooks
ln -s /bin/ls $CLAUDE_CONFIG_DIR/hooks/cc-statusline-event.zsh      # another repo's hook link
check "unset profile installs" install
check "hooks: subagent-guard linked" test -L $CLAUDE_CONFIG_DIR/hooks/subagent-guard.sh -a -x $CLAUDE_CONFIG_DIR/hooks/subagent-guard.sh
check "hooks: data files and tests/ not linked" test ! -e $CLAUDE_CONFIG_DIR/hooks/rule-triggers.tsv -a ! -e $CLAUDE_CONFIG_DIR/hooks/tests
check "hooks: another repo's link left alone" test "$(readlink $CLAUDE_CONFIG_DIR/hooks/cc-statusline-event.zsh)" = /bin/ls
check "hooks: a linked hook finds its repo folder" eval "print '{}' | $CLAUDE_CONFIG_DIR/hooks/show-rule-at-action.sh"
check "unset: personal skill not linked" test ! -e $CLAUDE_CONFIG_DIR/skills/$one_skill
check "unset: personal rule not linked" test ! -e $CLAUDE_CONFIG_DIR/rules/$one_rule
check "unset: personal/ folder itself not linked" test ! -e $CLAUDE_CONFIG_DIR/skills/personal
check "unset: shared rule linked" test -L $CLAUDE_CONFIG_DIR/rules/question-handling.md

check "missing denylist is reported" grep -q 'Push denylist missing' $work/out
mkdir -p $XDG_CONFIG_HOME/agents-shared
print $'# only a comment\n\n' > $XDG_CONFIG_HOME/agents-shared/push-denylist.txt
check "no-entry denylist installs" install
check "no-entry denylist warns loudly" grep -q 'PUSH DENYLIST HAS NO ENTRIES' $work/out
print 'somename' >> $XDG_CONFIG_HOME/agents-shared/push-denylist.txt
check "filled denylist installs" install
check "filled denylist does not warn" eval '! grep -qi "denylist" $work/out'

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
