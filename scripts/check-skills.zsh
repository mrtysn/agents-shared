#!/bin/zsh
# DESC: Offline structural check of claude/skills, rules and commands (frontmatter, links, installed symlinks)
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
  - skill, rule or command not linked into ~/.claude (honours $CLAUDE_CONFIG_DIR),
    or a link there into this checkout that dangles
Warnings (`-- <path>: <what>`): own skills (no source.json) lacking
argument-hint, allowed-tools, or "Use when" in the description.
USAGE
  exit 0
fi

ROOT=${0:A:h:h}
CFG=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
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
for d in $ROOT/claude/skills/*(N/); do
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

# --- rule links ---
for r in $ROOT/claude/rules/*.md(N); do
  nrules=$((nrules+1))
  for t in ${(f)"$(grep -oE '\]\([^)#[:space:]]+\.md(#[^)]*)?\)' $r | sed -E 's/^\]\(//; s/(#[^)]*)?\)$//' || true)"}; do
    [[ $t == *://* ]] && continue
    [[ -f $ROOT/claude/rules/$t ]] || fail $r "link to $t does not resolve"
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
check_links skills $ROOT/claude/skills/*(N/)
check_links rules $ROOT/claude/rules/*.md(N)
check_links commands $ROOT/claude/commands/*.md(N)
local k l
for k in skills rules commands; do
  for l in $CFG/$k/*(N@); do
    [[ $(readlink $l) == $ROOT/* && ! -e $l ]] && fail $l "dangling link into this checkout"
  done
done

print "checked $nskills skills, $nrules rules: $problems problems, $warnings warnings"
(( problems == 0 ))
