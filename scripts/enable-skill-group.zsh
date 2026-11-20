#!/bin/zsh
# DESC: Switch a skill group on or off for the current repo (gitignored local scope), recording why
#
# The one way an agent switches a group: it runs `claude plugin enable|disable <group>@skills-dir
# --scope local` in the repo root, as Skill Tree's switch does, after these checks:
#   - the folder is in a git repo, and the group is one claude/skill-groups.json names;
#   - the repo's .claude/settings.local.json is not tracked by git (a repo that commits it is the
#     user's to change: the script refuses and says so).
# Every switch is appended to the log below (time, repo, group, on|off, reason), which `--list`
# reads and hooks/note-skill-groups-used-here.sh uses to name a group switched on here that has
# gone unused, so it can be switched off again.
#
# Usage:
#   enable-skill-group.zsh <group> --reason "<what this session needs it for>"
#   enable-skill-group.zsh <group> --off --reason "<why>"
#   enable-skill-group.zsh --list            # this repo's recorded switches and the groups' recent use
#
# Afterwards the session ends its turn asking the user to type /reload-plugins; nothing else makes
# the change live in an open session.
# SKILL_GROUP_LOG overrides the log path, SKILL_GROUP_CACHE the usage cache (tests).
set -euo pipefail

AS=${0:A:h:h}
LOG=${SKILL_GROUP_LOG:-${XDG_STATE_HOME:-$HOME/.local/state}/agents-shared/skill-group-switches.tsv}
CACHE=${SKILL_GROUP_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/skill-group-use.json}

die() { print -u2 -r -- "enable-skill-group: $*"; exit 1; }

root=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repo: switch groups from the repo the work is in"

if [[ ${1:-} == --list ]]; then
  print -r -- "Recorded switches for $root (log: $LOG):"
  if [[ -r $LOG ]]; then
    awk -F'\t' -v r="$root" '$2 == r {printf "  %s  %-20s %-3s  %s\n", $1, $3, $4, $5}' $LOG
  fi
  if [[ -r $CACHE ]]; then
    print -r -- "Uses in this repo over the usage cache's window ($(jq -r .days $CACHE) days):"
    jq -r --arg r "$root" '.groups[] | {group, n: ([.folders | to_entries[] | select(.key == $r or (.key | startswith($r + "/"))) | .value] | add // 0)} | select(.n > 0) | "  \(.group) \(.n)"' $CACHE
  fi
  exit 0
fi

group=${1:-}; shift || true
[[ -n $group && $group != -* ]] || die 'usage: enable-skill-group.zsh <group> [--off] --reason "<why>"   (or --list)'
state=on reason=""
while (( $# )); do
  case $1 in
    --off) state=off ;;
    --reason) shift; reason=${1:-} ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done
[[ -n $reason ]] || die "--reason is required: say what this session needs the group for, so it can be switched off later"

jq -e --arg g "$group" '.defaults | has($g)' $AS/claude/skill-groups.json >/dev/null ||
  die "no skill group '$group': the groups are $(jq -r '.defaults | keys | join(", ")' $AS/claude/skill-groups.json)"

if git -C $root ls-files --error-unmatch .claude/settings.local.json >/dev/null 2>&1; then
  die "$root commits .claude/settings.local.json, so switching a group there changes a tracked file. Ask the user before changing it; nothing was switched."
fi

command -v claude >/dev/null || die "the claude CLI is not on PATH"
verb=enable; [[ $state == off ]] && verb=disable
(cd $root && claude plugin $verb "$group@skills-dir" --scope local) || die "claude plugin $verb $group@skills-dir failed"

mkdir -p ${LOG:h}
print -r -- "$(date +%Y-%m-%dT%H:%M:%S)"$'\t'"$root"$'\t'"$group"$'\t'"$state"$'\t'"${reason//$'\t'/ }" >> $LOG
print -r -- "Switched $group $state for $root (recorded in $LOG)."
print -r -- "Now end the turn in text asking the user to type /reload-plugins; never through AskUserQuestion."
