#!/bin/zsh
# Cases for scripts/register-claude-account, run against a stub home folder.
set -uo pipefail
here=${0:A:h:h}
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
export HOME=$t/home XDG_CONFIG_HOME=$t/home/.config
mkdir -p $HOME/.claude $HOME/.claude-personal $HOME/.claude-work
print 'AGENT_PROFILE=work' > $HOME/.claude/paths.local.sh
f=$XDG_CONFIG_HOME/agents-shared/claude-accounts
fail=0; n=0
check() { n=$((n+1)); [[ "$2" == "$3" ]] || { fail=$((fail+1)); print "FAIL $1: want [$3] got [$2]"; } }
rows() { grep -v '^#' $f | tr '\t' ' '; }

$here/register-claude-account $HOME/.claude >/dev/null
check "default account named after its profile" "$(rows)" "work ~/.claude"
$here/register-claude-account $HOME/.claude-personal >/dev/null
check "second folder appended by folder name" "$(rows)" $'work ~/.claude\npersonal ~/.claude-personal'
$here/register-claude-account $HOME/.claude-personal >/dev/null
check "rerun changes nothing" "$(rows | wc -l | tr -d ' ')" "2"
rm $f; rm $HOME/.claude/paths.local.sh
$here/register-claude-account $HOME/.claude >/dev/null
check "no profile falls back to main" "$(rows)" "main ~/.claude"
print 'work ~/somewhere-else' >> $f
out=$($here/register-claude-account $HOME/.claude-work 2>&1); rc=$?
check "taken name refuses" "$rc" "1"
check "taken name said" "${out:0:44}" "register-claude-account: the name 'work' is "
print "register-claude-account tests: $n cases, $fail failed"; exit $((fail>0))
