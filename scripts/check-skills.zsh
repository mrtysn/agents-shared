#!/bin/zsh
# DESC: Offline structural check of claude/skills, rules and commands (frontmatter, links, installed symlinks, hook links)
set -euo pipefail
setopt extendedglob

if [[ "${1:-}" == (-h|--help) ]]; then
  cat <<'USAGE'
usage: check-skills.zsh

Offline structural check of this repo's skills, rules and commands.
Hard failures (exit 1), printed as `!! <path>: <what>`:
  - skill dir without SKILL.md that is not a pack (plugin.json + skills/*/SKILL.md)
  - non-kebab-case skill name, or frontmatter `name:` differing from the dir (own skills only)
  - frontmatter missing, unterminated, or without a non-empty description
  - claude/rules link `](x.md)` that does not resolve, or a [[wiki]] link
  - skill, rule, command or hook script not linked into ~/.claude (honours $CLAUDE_CONFIG_DIR),
    or a link there into this checkout that dangles
  - claude/{rules,skills}/personal/ entries not linked when the config folder's
    profile is personal, linked when it is not, or sharing a name with a shared entry
Warnings (`-- <path>: <what>`): own skills (no source.json) lacking
argument-hint, allowed-tools, or "Use when" in the description.
USAGE
  exit 0
fi

ROOT=${0:A:h:h}
CFG=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
PROFILE=$($ROOT/scripts/agent-profile $CFG)
problems=0 warnings=0 nskills=0 nrules=0 t=""
local -a subs

fail() { print -r -- "!! ${1#$ROOT/}: $2"; problems=$((problems+1)); }
warn() { print -r -- "-- ${1#$ROOT/}: $2"; warnings=$((warnings+1)); }

# check_skill <dir> : validates one dir holding SKILL.md
check_skill() {
  local dir=$1 f=$1/SKILL.md base=${1:t}
  nskills=$((nskills+1))
  [[ $base =~ '^[a-z0-9]+(-[a-z0-9]+)*$' ]] || fail $dir "name is not kebab-case"
  local -a lines; lines=("${(@f)$(<$f)}")
  if [[ "${lines[1]:-}" != '---' ]]; then fail $f "frontmatter does not start with ---"; return; fi
  local end=0 i
  for i in {2..${#lines}}; do [[ "${lines[i]}" == '---' ]] && { end=$i; break; }; done
  if (( end == 0 )); then fail $f "frontmatter is not closed with ---"; return; fi
  local -a fm; fm=("${(@)lines[2,end-1]}")
  local name="" desc="" haveargs=0 havetools=0 line n=${#fm} j
  for i in {1..$n}; do
    line=${fm[i]}
    case $line in
      name:*) name=${line#name:}; name=${name//[\"\' ]/} ;;
      argument-hint:*) haveargs=1 ;;
      allowed-tools:*) havetools=1 ;;
      description:*)
        desc=${line#description:}; desc=${desc##[[:space:]]#}
        if [[ $desc == (|'>'*|'|'*) ]]; then
          desc=""
          for ((j=i+1; j<=n; j++)); do
            [[ ${fm[j]} == [[:space:]]* ]] || break
            desc+=${fm[j]}
          done
        fi ;;
    esac
  done
  [[ -z ${desc//[[:space:]\"\']/} ]] && fail $f "missing or empty description"
  # vendored skills keep the name upstream gave them (e.g. react's vercel-*)
  local own=1; [[ -e $dir/source.json || -e ${dir:h:h}/source.json ]] && own=0
  (( own )) && [[ -n $name && $name != $base ]] && fail $f "name '$name' differs from directory '$base'"
  if (( own )); then
    (( haveargs )) || warn $f "own skill lacks argument-hint"
    (( havetools )) || warn $f "own skill lacks allowed-tools"
    [[ $desc == *"Use when"* ]] || warn $f 'description lacks "Use when"'
  fi
}

# --- skills ---
# claude/skills/personal/ holds skills for the personal profile only; it is not a skill.
local -a skill_dirs
skill_dirs=(${ROOT}/claude/skills/*(N/) ${ROOT}/claude/skills/personal/*(N/))
skill_dirs=(${skill_dirs:#$ROOT/claude/skills/personal})
for d in $skill_dirs; do
  if [[ -f $d/SKILL.md ]]; then
    check_skill $d
  elif [[ -f $d/.claude-plugin/plugin.json ]]; then
    [[ ${d:t} =~ '^[a-z0-9]+(-[a-z0-9]+)*$' ]] || fail $d "name is not kebab-case"
    subs=($d/skills/*/SKILL.md(N))
    (( ${#subs} )) || fail $d "pack has no skills/*/SKILL.md"
    for s in $subs; do check_skill ${s:h}; done
    for s in $d/skills/*(N/); do [[ -f $s/SKILL.md ]] || fail $s "pack skill dir lacks SKILL.md"; done
  else
    fail $d "no SKILL.md and not a pack (.claude-plugin/plugin.json + skills/*/SKILL.md)"
  fi
done

# --- group defaults: claude/skill-groups.json names every group, and only real groups ---
local groups_file=$ROOT/claude/skill-groups.json
if [[ ! -r $groups_file ]]; then
  fail $groups_file "missing: every skill group needs a committed default there"
else
  local -a packs named
  packs=(${ROOT}/claude/skills/*/.claude-plugin/plugin.json(N:h:h:t))
  named=(${(f)"$(jq -r '.defaults | keys[]' $groups_file)"})
  for g in $packs; do
    (( ${named[(Ie)$g]} )) || fail $groups_file "group '$g' has no entry under defaults (add \"$g\": false)"
  done
  for g in $named ${(f)"$(jq -r '.splits | to_entries[] | .key, .value[]' $groups_file)"}; do
    [[ -n $g ]] || continue
    (( ${packs[(Ie)$g]} )) || fail $groups_file "'$g' is not a group under claude/skills/"
  done
fi

# --- rule links ---
for r in $ROOT/claude/rules/*.md(N) $ROOT/claude/rules/personal/*.md(N); do
  nrules=$((nrules+1))
  for t in ${(f)"$(grep -oE '\]\([^)#[:space:]]+\.md(#[^)]*)?\)' $r | sed -E 's/^\]\(//; s/(#[^)]*)?\)$//' || true)"}; do
    [[ $t == *://* ]] && continue
    [[ -f ${r:h}/$t ]] || fail $r "link to $t does not resolve"
  done
  grep -qE '\[\[[^]]+\]\]' $r && fail $r "contains a [[wiki]] link"
done

# --- installed links ---
check_links() {  # <kind> <entries...>
  local kind=$1; shift
  local e
  for e in "$@"; do
    [[ -L $CFG/$kind/${e:t} ]] || fail $e "not linked in $CFG/$kind"
  done
}
check_links skills ${skill_dirs:#$ROOT/claude/skills/personal/*}
check_links rules $ROOT/claude/rules/*.md(N)
check_links commands $ROOT/claude/commands/*.md(N)
# hooks: the executable top-level scripts init-global.sh links (settings.json names them by that link)
check_links hooks $ROOT/hooks/*.(sh|py|zsh)(N.*)
# personal/ entries: linked exactly when the profile is personal, never shadowing a shared name
local p k l
for p in $ROOT/claude/skills/personal/*(N/) $ROOT/claude/rules/personal/*.md(N); do
  k=${${p:h:h}:t}
  [[ -e $ROOT/claude/$k/${p:t} ]] && fail $p "a shared $k entry has the same name"
  if [[ $PROFILE == personal ]]; then
    [[ -L $CFG/$k/${p:t} ]] || fail $p "not linked in $CFG/$k (profile personal)"
  else
    [[ $(readlink $CFG/$k/${p:t} 2>/dev/null) == $p ]] && fail $CFG/$k/${p:t} "linked, but the profile is ${PROFILE:-unset}"
  fi
done
for k in skills rules commands hooks; do
  for l in $CFG/$k/*(N@); do
    [[ $(readlink $l) == $ROOT/* && ! -e $l ]] && fail $l "dangling link into this checkout"
  done
done

print "checked $nskills skills, $nrules rules: $problems problems, $warnings warnings"
(( problems == 0 ))
