#!/bin/zsh
# Find installed skills matching a query and say whether each is active in a folder.
# Prints names and states only, never skill text, so a skill switched off for the folder
# does not reach the model's context just because it was searched for.
#
# Active-ness follows Skill Tree: a skill group is on or off through `enabledPlugins`
# ("<group>@skills-dir"), read from user, then the folder's .claude/settings.json, then the repo's
# .claude/settings.local.json, the last one that names it winning; a group nobody names is on.
# A flat skill follows `skillOverrides` the same way. A skill moved to a group's off/ folder is off
# everywhere.
#
# usage: find-local-skills.zsh QUERY [FOLDER]    FOLDER defaults to the current directory
# output: one line per match, "<state>\t<group/skill or skill>", states:
#   active | not-enabled-here (group off) | off-in-group | off (override) | slash-only | name-only

query=${1:-}
if [[ -z $query ]]; then
  print -u2 "usage: ${0:t} QUERY [FOLDER]"
  exit 2
fi
folder=${2:-$PWD}
config=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
skills=$config/skills
root=$(git -C $folder rev-parse --show-toplevel 2>/dev/null || print -r -- $folder)
settings=($config/settings.json $folder/.claude/settings.json $root/.claude/settings.local.json)

# the value the last settings file naming KEY under SECTION gives it; empty when none does
setting() {
  local section=$1 key=$2 file value out=
  for file in $settings; do
    [[ -f $file ]] || continue
    value=$(jq -r --arg s $section --arg k $key \
      '(.[$s] // {}) | if has($k) then .[$k] else empty end' $file 2>/dev/null)
    [[ -n $value ]] && out=$value
  done
  print -r -- $out
}

typeset -U hits
hits=(${(f)"$(grep -rilF --include=SKILL.md -- $query $skills/*/ 2>/dev/null)"})

for hit in $hits; do
  rel=${hit#$skills/}
  parts=(${(s:/:)rel})
  if [[ -d $skills/$parts[1]/.claude-plugin ]]; then
    group=$parts[1]
    if [[ $parts[2] == off ]]; then
      print -r -- "off-in-group"$'\t'"$group/$parts[3]"
      continue
    fi
    if [[ $(setting enabledPlugins "$group@skills-dir") == false ]]; then
      print -r -- "not-enabled-here (group off)"$'\t'"$group/$parts[3]"
    else
      print -r -- "active"$'\t'"$group/$parts[3]"
    fi
  else
    override=$(setting skillOverrides $parts[1])
    case $override in
      off) print -r -- "off (override)"$'\t'"$parts[1]" ;;
      slash-only|name-only) print -r -- "$override"$'\t'"$parts[1]" ;;
      *) print -r -- "active"$'\t'"$parts[1]" ;;
    esac
  fi
done | sort -u
