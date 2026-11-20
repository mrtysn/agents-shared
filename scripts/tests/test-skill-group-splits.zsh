#!/bin/zsh
# DESC: Test the split migration in sync-skill-group-settings.py and report-skill-group-use.py's old-name attribution
set -uo pipefail

as=${0:A:h:h:h}
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT
dev=$work/dev
export SKILL_GROUP_CACHE=$work/cache.json

pass=0 fail=0
check() {  # check <label> <condition...>
  local label=$1; shift
  if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); print -r -- "FAIL $label"; fi
}
mkrepo() {  # mkrepo <name> <settings.local.json content>
  mkdir -p $dev/$1/.claude && git -C $dev/$1 init -q && print -r -- $2 > $dev/$1/.claude/settings.local.json
}
migrate() { python3 $as/scripts/sync-skill-group-settings.py --migrate-splits --dev-root $dev "$@" > $work/out 2>&1 }
val() { jq -r --arg k "$2@skills-dir" 'if .enabledPlugins | has($k) then .enabledPlugins[$k] else "absent" end' $dev/$1/.claude/settings.local.json }

mkrepo used '{"enabledPlugins": {"motion@skills-dir": true}}'
mkrepo unused '{"enabledPlugins": {"motion@skills-dir": true}}'
mkrepo parentoff '{"enabledPlugins": {"motion@skills-dir": false}}'
mkrepo decided '{"enabledPlugins": {"motion@skills-dir": true, "gsap@skills-dir": false}}'
mkrepo committed '{"enabledPlugins": {"motion@skills-dir": true}}'
git -C $dev/committed add -f .claude/settings.local.json
jq -n --arg u $dev/used --arg d $dev/decided --arg c $dev/committed --arg p $dev/parentoff '{days: 30, groups: [
  {group: "gsap", folders: {($u + "/sub"): 2, ($d): 1, ($c): 1, ($p): 3}},
  {group: "web-animation", folders: {}}]}' > $SKILL_GROUP_CACHE

check "a dry run writes nothing" eval "migrate --dry-run && test \"\$(val used gsap)\" = absent"
check "the migration runs" migrate
check "a repo that used the moved skills gets the new group on" test "$(val used gsap)" = true
check "a new group it never used gets no entry" test "$(val used web-animation)" = absent
check "a repo that did not use them is left alone" test "$(val unused gsap)" = absent
check "a repo with the old group off is left alone" test "$(val parentoff gsap)" = absent
check "a recorded choice is kept" test "$(val decided gsap)" = false
check "a committed settings file is reported, not changed" eval "test \"\$(val committed gsap)\" = absent && grep -q 'committed commits' $work/out"
check "a second run changes nothing" eval "migrate && ! grep -q 'added' $work/out"

touch -t 202001010000 $SKILL_GROUP_CACHE
mkrepo late '{"enabledPlugins": {"motion@skills-dir": true}}'
check "a stale cache skips the migration" eval "migrate && grep -q 'skipped' $work/out && test \"\$(val late gsap)\" = absent"

# report-skill-group-use.py: a run under a group's old name counts for the group holding the skill now.
check "an old-name run counts for the skill's group today" python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('r', '$as/scripts/report-skill-group-use.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
homes = {'gsap-core': ['gsap'], 'shared': ['a', 'b']}
assert r.home_group('motion:gsap-core', homes) == 'gsap'
assert r.home_group('gsap:gsap-core', homes) == 'gsap'
assert r.home_group('b:shared', homes) == 'b'
assert r.home_group('gone:unknown', homes) == 'gone'
"

print "skill-group splits: $pass passed, $fail failed"
(( fail == 0 ))
