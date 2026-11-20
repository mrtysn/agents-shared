#!/bin/zsh
# DESC: Sync external skills in a separate git worktree, so nothing reaches live sessions until the diff is read and landed
#
# ~/.claude/skills links into this checkout, so a sync run here is live in every session the moment
# it writes, conflict markers included. This wrapper runs scripts/sync-external-skills.sh in a worktree
# on its own branch instead; the live checkout changes only at `land`, after review.
#
# Usage:
#   sync-external-skills-reviewed.zsh start [<sync args>...]   # e.g. start, start gamedev, start --adopt-listing x
#   sync-external-skills-reviewed.zsh diff                     # the changes waiting in the worktree
#   sync-external-skills-reviewed.zsh land "<commit message>"  # commit there, merge here, remove the worktree
#   sync-external-skills-reviewed.zsh abort                    # drop the worktree and its branch
#
# `start` needs no uncommitted change under claude/skills/ here (the worktree is cut from HEAD).
# `land` refuses while any file in the worktree holds conflict markers; resolve them there first
# (claude/skills/update-external-skills/SKILL.md, step 4), editing files under the worktree path.
# The worktree path is printed by every command. SKILL_SYNC_WORKTREE overrides it (tests).
set -euo pipefail

REPO=${0:A:h:h}
WT=${SKILL_SYNC_WORKTREE:-${XDG_STATE_HOME:-$HOME/.local/state}/agents-shared/skill-sync-worktree}
BRANCH=skill-sync

die() { print -u2 -r -- "sync-external-skills-reviewed: $*"; exit 1; }
have_wt() { git -C $REPO worktree list --porcelain | grep -qx "worktree ${WT:A}" }

case ${1:-} in
  start)
    shift
    have_wt && die "a sync is already waiting in $WT: run diff, then land or abort"
    [[ -z $(git -C $REPO status --porcelain -- claude/skills) ]] ||
      die "uncommitted changes under claude/skills/ in $REPO; commit them first so the sync's diff stands alone"
    mkdir -p ${WT:h}
    git -C $REPO show-ref --quiet refs/heads/$BRANCH && git -C $REPO branch -D $BRANCH >/dev/null
    git -C $REPO worktree add -q -b $BRANCH $WT HEAD
    print -r -- "worktree: $WT (branch $BRANCH, from $(git -C $REPO rev-parse --short HEAD))"
    (cd $WT && bash scripts/sync-external-skills.sh "$@")
    print -r -- ""
    print -r -- "Nothing is live yet. Review: $0 diff   then: $0 land \"<message>\" or $0 abort"
    ;;
  diff)
    have_wt || die "no sync waiting (run start)"
    git -C $WT add -A
    git -C $WT diff --cached --stat
    print -r -- "full diff: git -C $WT diff --cached"
    ;;
  land)
    shift
    msg=${1:-}
    [[ -n $msg ]] || die 'land needs a commit message: land "update <skill> from upstream"'
    have_wt || die "no sync waiting (run start)"
    git -C $WT add -A
    if git -C $WT grep --cached -lIE '^<<<<<<< ' >/dev/null 2>&1 && git -C $WT grep --cached -lIE '^>>>>>>> ' >/dev/null 2>&1; then
      die "conflict markers remain in $WT: $(git -C $WT grep --cached -lIE '^<<<<<<< ' | tr '\n' ' ')"
    fi
    if git -C $WT diff --cached --quiet; then
      print -r -- "the sync changed nothing; dropping the worktree"
    else
      git -C $WT commit -q -m "$msg"
      git -C $REPO merge -q --no-edit $BRANCH || die "merging $BRANCH into $(git -C $REPO branch --show-current) failed; resolve it there, then run abort"
      print -r -- "landed: $(git -C $REPO log --oneline -1)"
    fi
    git -C $REPO worktree remove --force $WT
    git -C $REPO branch -D $BRANCH >/dev/null
    print -r -- "Push when ready; run scripts/init-global.sh if a skill directory was added or removed."
    ;;
  abort)
    have_wt && git -C $REPO worktree remove --force $WT
    git -C $REPO show-ref --quiet refs/heads/$BRANCH && git -C $REPO branch -D $BRANCH >/dev/null
    print -r -- "dropped the sync worktree; nothing changed in $REPO"
    ;;
  *) sed -n '2,19p' $0 | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
