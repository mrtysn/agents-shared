#!/bin/zsh
# DESC: Test pre-commit-check.zsh and sync-external-skills-reviewed.zsh in throwaway repos with fake sync and check scripts
set -uo pipefail

as=${0:A:h:h:h}
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT
export SKILL_SYNC_WORKTREE=$work/wt GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t

pass=0 fail=0
check() {  # check <label> <condition...>
  local label=$1; shift
  if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); print -r -- "FAIL $label"; fi
}

# A repo shaped like agents-shared: the two scripts under test, a fake sync and a fake check.
r=$work/repo
mkdir -p $r/scripts $r/claude/skills/demo
git -C $r init -q -b main
git -C $r config core.hooksPath /dev/null
cp $as/scripts/pre-commit-check.zsh $as/scripts/sync-external-skills-reviewed.zsh $r/scripts/
print -r -- '#!/usr/bin/env bash
# fake sync: appends a line, or writes conflict markers when asked
if [ "${1:-}" = conflict ]; then printf "<<<<<<< local\na\n=======\nb\n>>>>>>> upstream@1\n" > claude/skills/demo/SKILL.md
else echo "upstream line" >> claude/skills/demo/SKILL.md; fi' > $r/scripts/sync-external-skills.sh
print -r -- '#!/bin/zsh
[[ -e ${0:A:h:h}/FAIL ]] && { print -r -- "-- claude/skills/other: a warning"; print "!! claude/skills/demo: broken"; print "checked 1 skills: 1 problems"; exit 1; }; exit 0' > $r/scripts/check-skills.zsh
print 'base' > $r/claude/skills/demo/SKILL.md
git -C $r add -A && git -C $r commit -q -m init
precommit() { (cd $r && zsh scripts/pre-commit-check.zsh) > $work/out 2>&1 }
sync() { (cd $r && zsh scripts/sync-external-skills-reviewed.zsh "$@") > $work/out 2>&1 }

# --- pre-commit ---
print 'a change' >> $r/claude/skills/demo/SKILL.md && git -C $r add -A
check "a clean skill change passes" precommit
touch $r/FAIL
check "check-skills problems refuse a skill change" eval '! precommit'
check "the refusal shows the problem" grep -q '!! claude/skills/demo: broken' $work/out
check "the refusal leaves out warnings" eval '! grep -q "^-- " $work/out'
check "the refusal leaves out the summary" eval '! grep -q "^checked " $work/out'
git -C $r reset -q && mkdir -p $r/hooks && print 'x' > $r/hooks/demo.sh && git -C $r add hooks
check "check-skills problems refuse a hook change" eval '! precommit'
git -C $r rm -q --cached hooks/demo.sh && rm -r $r/hooks && git -C $r add -A
rm $r/FAIL
printf '<<<<<<< local\nx\n=======\ny\n>>>>>>> upstream@1\n' > $r/claude/skills/demo/SKILL.md && git -C $r add -A
check "staged conflict markers refuse the commit" eval '! precommit'
printf 'Title\n=======\n' > $r/claude/skills/demo/SKILL.md && git -C $r add -A
check "a setext heading is not a conflict" precommit
git -C $r checkout -q -- . && git -C $r reset -q --hard

# --- reviewed sync ---
check "start runs the sync in a worktree" sync start
check "the live checkout is untouched" test "$(cat $r/claude/skills/demo/SKILL.md)" = base
check "the worktree holds the change" grep -q 'upstream line' $work/wt/claude/skills/demo/SKILL.md
check "a second start refuses" eval '! sync start'
check "diff names the file" eval 'sync diff && grep -q demo/SKILL.md $work/out'
check "land needs a message" eval '! sync land'
check "land merges" sync land "update demo from upstream"
check "the live checkout now has it" grep -q 'upstream line' $r/claude/skills/demo/SKILL.md
check "the worktree is gone" test ! -e $work/wt

check "start with a conflict" sync start conflict
check "land refuses conflict markers" eval '! sync land "x"'
check "the live checkout still has no markers" eval '! grep -q "<<<<<<<" $r/claude/skills/demo/SKILL.md'
check "abort drops the worktree" sync abort
check "and the branch" eval '! git -C $r show-ref --quiet refs/heads/skill-sync'

print -r -- 'local edit' >> $r/claude/skills/demo/SKILL.md
check "start refuses with uncommitted skill changes" eval '! sync start'

print "reviewed sync and pre-commit: $pass passed, $fail failed"
(( fail == 0 ))
