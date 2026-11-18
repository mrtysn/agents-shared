#!/bin/zsh
# DESC: list the repos under a folder whose own core.hooksPath skips githooks/pre-push's name guard
#
# The name guard runs from the global core.hooksPath (githooks/). A repo that sets a
# core.hooksPath of its own runs those hooks instead, so its pushes are never scanned and
# nothing says so. This prints one line per git repo directly under ROOT whose own
# core.hooksPath is set and is not githooks/:
#     <folder>  <OWNER/NAME>  <public|visibility unknown>  core.hooksPath=<value>
# A repo is left out when it is private (the guard would skip it anyway), or when it is in the
# exempt list (see githooks/pre-push), which skips it on purpose. Visibility comes from
# githooks/pre-push's cache, and when the cache has no answer under 7 days old, from
# `gh api repos/OWNER/NAME --jq .private`, cached the same way; with gh missing, offline or
# refused, the repo is "visibility unknown" and listed.
# init-global.sh prints these lines in its summary. Exit 0 always; no output means no bypass.
#
# usage: list-push-guard-bypasses.zsh [ROOT]   (default: $DEV_ROOT, else this checkout's parent)
set -uo pipefail

checkout=${0:A:h:h}
githooks=$checkout/githooks
root=${1:-${DEV_ROOT:-${checkout:h}}}
exempt_list=${AGENTS_PUSH_DENYLIST_EXEMPT:-${XDG_CONFIG_HOME:-$HOME/.config}/agents-shared/push-denylist-exempt.txt}
cache=${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/repo-visibility

for dir in $root/*(N/); do
  dir=${dir%/}
  [[ -e $dir/.git ]] || continue
  [[ ${dir:A} == $checkout ]] && continue   # this checkout: init-global.sh reports its own hooks path
  own=$(git -C $dir config --local --get core.hooksPath 2>/dev/null) || continue
  [[ -n $own ]] || continue
  [[ $own == /* ]] && abs=$own || abs=$dir/$own
  [[ ${abs:A} == ${githooks:A} ]] && continue
  url=$(git -C $dir remote get-url origin 2>/dev/null) || continue
  parts=(${(s:/:)${${${url%/}%.git}//:/\/}})
  (( ${#parts} >= 2 )) || continue
  repo="${parts[-2]}/${parts[-1]}"
  if [[ -r $exempt_list ]] && sed -e 's/#.*//' -e 's/[[:space:]]//g' $exempt_list | grep -qixF -- $repo; then
    continue
  fi
  vis=""
  file=$cache/${(L)parts[-2]}__${(L)parts[-1]}
  [[ -n $(find $cache -maxdepth 1 -type f -name ${file:t} -mtime -7 2>/dev/null) ]] && vis=$(<$file)
  if [[ $vis != (private|public) ]] && command -v gh >/dev/null 2>&1; then
    case $(GH_PROMPT_DISABLED=1 gh api "repos/${parts[-2]}/${parts[-1]}" --jq .private 2>/dev/null) in
      true) vis=private ;;
      false) vis=public ;;
      *) vis="" ;;
    esac
    [[ -n $vis ]] && mkdir -p $cache && print -r -- $vis > $file
  fi
  [[ $vis == private ]] && continue
  [[ $vis == public ]] || vis="visibility unknown"
  print -r -- "${dir:t}  $repo  $vis  core.hooksPath=$own"
done
exit 0
