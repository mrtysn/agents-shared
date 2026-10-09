#!/bin/zsh
# DESC: List the live background shells of one Claude Code session (pid, elapsed, command)
set -euo pipefail

usage() {
  cat <<'USAGE'
usage: list-session-background-shells.sh --session ID [--older-than MINUTES]

Prints one line per live background shell of the Claude Code session ID:
  PID  ELAPSED  COMMAND (trimmed to about 100 chars)
Prints nothing and exits 0 when there are none.

A background shell is a child of a `claude` process whose stdout is a
.../<SESSION_ID>/tasks/<id>.output file. A session resumed under a new
`claude` process keeps its older shells under the old process, so every
`claude` process is checked, not only the current one.

  --session ID          session id to match (required)
  --older-than MINUTES  only shells running at least this long
USAGE
}

session=""
older=0
while (( $# )); do
  case "$1" in
    --session) session="${2:-}"; shift 2 ;;
    --older-than) older="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) print -u2 "unknown argument: $1"; usage >&2; exit 2 ;;
  esac
done
[[ -n "$session" ]] || { print -u2 "--session is required"; usage >&2; exit 2; }
[[ "$older" == <-> ]] || { print -u2 "--older-than takes whole minutes"; exit 2; }

# Shell children of every claude process: "pid etime command".
candidates=$(ps -axo pid=,ppid=,etime=,comm=,command= | awk '
  { pid=$1; ppid=$2; etime=$3; comm=$4
    line[pid]=$0; par[pid]=ppid; et[pid]=etime
    if (comm == "claude" || comm ~ /\/claude$/) isclaude[pid]=1 }
  END {
    for (p in par) if (isclaude[par[p]] && line[p] ~ /shell-snapshots/) {
      cmd=line[p]
      sub(/^.*eval /, "", cmd)
      sub(/ < \/dev\/null.*$/, "", cmd)
      print p "\t" et[p] "\t" cmd
    }
  }')
[[ -n "$candidates" ]] || exit 0

pids=${(j:,:)${(f)candidates}%%$'\t'*}
owned=$(lsof -a -p "$pids" -d 1 -Fpn 2>/dev/null | awk -v s="/$session/tasks/" '
  /^p/ { p=substr($0,2) } /^n/ && index($0, s) { print p }')
[[ -n "$owned" ]] || exit 0

# The caller's own shell (and a hook's) is an ancestor: a foreground command's
# stdout is also a tasks/*.output file, so ancestors are skipped, as is anything
# under 5 s old, which is a foreground command of a parallel tool call.
ancestors=()
anc=$$
while (( anc > 1 )); do
  ancestors+=($anc)
  anc=$(ps -o ppid= -p $anc 2>/dev/null | tr -d ' ') || break
  [[ -n "$anc" ]] || break
done

for line in ${(f)candidates}; do
  pid=${line%%$'\t'*}
  (( ${ancestors[(Ie)$pid]} )) && continue
  (( ${${(f)owned}[(Ie)$pid]} )) || continue
  rest=${line#*$'\t'}
  et=${rest%%$'\t'*}
  cmd=${rest#*$'\t'}
  cmd=${cmd#\'}; cmd=${cmd%\'}
  cmd=${cmd//$'\n'/ }
  # etime [[dd-]hh:]mm:ss -> minutes
  days=0; clock=$et
  [[ $et == *-* ]] && { days=${et%%-*}; clock=${et#*-}; }
  parts=(${(s,:,)clock})
  secs=0
  for x in $parts; do secs=$(( secs * 60 + 10#$x )); done
  (( days * 86400 + secs >= 5 )) || continue
  mins=$(( days * 1440 + secs / 60 ))
  (( mins >= older )) || continue
  print -r -- "$pid  $et  ${cmd[1,100]}"
done
