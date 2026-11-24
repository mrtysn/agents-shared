#!/bin/zsh
# DESC: Fail when loaded text outside the personal/ folders names a personal-only tool or domain
#
# Rules, skills, commands, on-demand docs and hooks reach every profile's sessions unless they
# sit under a personal/ folder (claude/rules/personal/, claude/skills/personal/,
# docs/on-demand/personal/, hooks/personal/), which only the personal profile links or reads. This check keeps that
# split: any file outside those folders that names a token from
# scripts/personal-only-tokens.txt is a failure, printed as `!! <path>:<line>: <token>`.
#
# Not scanned: vendored upstream copies (.upstream/, override.patch, source.json), whose text
# is not ours. Hook test fixtures (hooks/tests/), scripts/ and docs/provenance are not loaded
# into sessions and are not scanned either. A hook's own text is: what it prints reaches the
# session, so personal wording in it prints only when scripts/agent-profile says personal, or
# the hook is moved to hooks/personal/.
#
# usage: check-personal-split.zsh
set -euo pipefail

ROOT=${0:A:h:h}
TOKENS=$ROOT/scripts/personal-only-tokens.txt
[[ -r $TOKENS ]] || { print -u2 "check-personal-split: $TOKENS is missing"; exit 1; }

local -a toks files
toks=(${(f)"$(grep -vE '^[[:space:]]*(#|$)' $TOKENS)"})
(( ${#toks} )) || { print -u2 "check-personal-split: no tokens in $TOKENS"; exit 1; }

# One ERE: (^|[^[:alnum:]_])(tok1|tok2|...)([^[:alnum:]_]|$), dots escaped.
local alt=${(j:|:)${toks//./\\.}}
local re="(^|[^[:alnum:]_])(${alt})([^[:alnum:]_]|$)"

files=(
  $ROOT/claude/rules/**/*(N.)
  $ROOT/claude/skills/**/*(N.)
  $ROOT/claude/commands/**/*(N.)
  $ROOT/docs/on-demand/**/*(N.)
  $ROOT/hooks/**/*(N.)
)
# Matched below $ROOT only: a checkout that itself sits under a folder named personal
# (~/dev/personal/agents-shared) would otherwise lose every file to this filter.
files=(${files:#$ROOT/*/personal/*})
files=(${files:#$ROOT/hooks/tests/*})
files=(${files:#*/__pycache__/*})
files=(${files:#*/.upstream/*})
files=(${files:#*/override.patch})
files=(${files:#*/source.json})

# An empty list would pass by checking nothing, and grep with no files reads stdin and hangs.
(( ${#files} )) || { print -u2 "check-personal-split: found no files to check under $ROOT"; exit 1; }

problems=0
local hit
for hit in ${(f)"$(grep -HniE -e $re -- $files 2>/dev/null || true)"}; do
  [[ -n $hit ]] || continue
  local file=${hit%%:*} rest=${hit#*:}
  local line=${rest%%:*} text=${rest#*:}
  local tok=$(print -r -- $text | grep -oiE -e $re | head -n 1 | sed -E 's/^[^[:alnum:]]//; s/[^[:alnum:]]$//')
  print -r -- "!! ${file#$ROOT/}:$line: names '$tok', which belongs under a personal/ folder"
  problems=$((problems+1))
done

print "checked ${#files} files against ${#toks} personal-only tokens: $problems problems"
(( problems == 0 ))
