#!/bin/zsh
# DESC: List the live background shells of one Claude Code session, with their child processes and listening ports
set -euo pipefail

usage() {
  cat <<'USAGE'
usage: list-session-background-shells.sh --session ID [--older-than MINUTES]

Prints the live background shells of the Claude Code session ID, one block each:
  PID  ELAPSED  COMMAND (trimmed to about 100 chars)
      PID  ELAPSED  CHILD COMMAND  [LISTEN addr:port ...]      (one per descendant)
and after them any orphan: a process whose output still goes to this session's
task files but whose shell is gone (its parent is launchd), marked `orphan`.
A Monitor (one armed by a subagent too) is a block marked `monitor`: its shell
writes to a pipe, so it is found as a piped shell-snapshot child of the `claude`
process this script runs under. Stop it with TaskStop when its task id is known,
else kill its pids.
Prints nothing and exits 0 when there is nothing alive.

Stopping a shell does not stop its children: a server started by the shell
keeps running and keeps its port. Stop every pid in a block, then run this
again; a block that is still printed is still alive.

A background shell is a child of a `claude` process whose stdout is a
.../<SESSION_ID>/tasks/<id>.output file. A session resumed under a new
`claude` process keeps its older shells under the old process, so every
`claude` process is checked, not only the current one. Orphans are found
through the same task files (under /tmp/claude-<uid>/*/<SESSION_ID>/tasks),
so a child that redirected its own output and lost its shell is not found.

  --session ID          session id to match (required)
  --older-than MINUTES  only shells running at least this long (orphans always print)
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

# One process snapshot: pid -> parent, elapsed, command.
typeset -A par et cmdof isclaude
typeset -A kids
while IFS= read -r line; do
  set -- ${=line}
  (( $# >= 4 )) || continue
  pid=$1; ppid=$2; e=$3; exe=${4#$'\x01'}
  par[$pid]=$ppid; et[$pid]=$e
  cmdof[$pid]=${line#*$'\x01'}
  [[ $exe == claude || $exe == */claude ]] && isclaude[$pid]=1
  kids[$ppid]+="$pid "
done < <(ps -axo pid=,ppid=,etime=,command= | awk '
  { match($0, /^ *[0-9]+ +[0-9]+ +[^ ]+ +/)
    print substr($0, 1, RLENGTH) "\x01" substr($0, RLENGTH + 1) }')

# etime [[dd-]hh:]mm:ss -> seconds
secs_of() {
  local e=$1 days=0 clock s=0 x
  [[ $e == *-* ]] && { days=${e%%-*}; clock=${e#*-}; } || clock=$e
  for x in ${(s,:,)clock}; do s=$(( s * 60 + 10#$x )); done
  print $(( days * 86400 + s ))
}

# Listening TCP sockets: pid -> "addr:port ..."
typeset -A listen
lp=""
while IFS= read -r l; do
  case $l in
    p*) lp=${l#p} ;;
    n*) [[ -n $lp ]] && listen[$lp]+="${l#n} " ;;
  esac
done < <(lsof -nP -iTCP -sTCP:LISTEN -Fpn 2>/dev/null)

# The caller's own shell is a child of claude too (a foreground command's stdout
# is also a tasks/*.output file), so this script's ancestors are skipped.
typeset -A ancestor
anc=$$
while (( anc > 1 )); do
  ancestor[$anc]=1
  anc=${par[$anc]:-0}
done

has_claude_ancestor() {
  local p=${par[$1]:-0}
  while (( p > 1 )); do
    (( ${isclaude[$p]:-0} )) && return 0
    p=${par[$p]:-0}
  done
  return 1
}

descendants() {  # prints every descendant pid of $1, depth first
  local c
  for c in ${=kids[$1]:-}; do
    print -- $c
    descendants $c
  done
}

print_block() {  # $1 pid, $2 label ("" or "orphan")
  local pid=$1 label=$2 c cmd
  cmd=${cmdof[$pid]//$'\n'/ }
  local tag=""; [[ -n $label ]] && tag="$label "
  print -r -- "${tag}${pid}  ${et[$pid]}  ${cmd[1,100]}${listen[$pid]:+  LISTEN ${listen[$pid]% }}"
  for c in $(descendants $pid); do
    cmd=${cmdof[$c]//$'\n'/ }
    print -r -- "    ${c}  ${et[$c]}  ${cmd[1,100]}${listen[$c]:+  LISTEN ${listen[$c]% }}"
  done
}

# Candidate shells: shell-snapshot children of a claude process.
candidates=()
for p in ${(k)par}; do
  (( ${isclaude[${par[$p]}]:-0} )) || continue
  [[ ${cmdof[$p]} == *shell-snapshots* ]] || continue
  (( ${ancestor[$p]:-0} )) && continue
  candidates+=($p)
done

typeset -A seen
if (( ${#candidates} )); then
  pids=${(j:,:)candidates}
  owned=$(lsof -a -p "$pids" -d 1 -Fpn 2>/dev/null | awk -v s="/$session/tasks/" '
    /^p/ { p=substr($0,2) } /^n/ && index($0, s) { print p }')
  # A Monitor's shell writes to a pipe, not a task file: it carries no session id,
  # so it is attributed through the claude process this script runs under.
  piped=$(lsof -a -p "$pids" -d 1 -Fpft 2>/dev/null | awk '
    /^p/ { p=substr($0,2) } /^t(PIPE|unix)$/ { print p }')
  mypid=$$
  myclaude=0
  while (( mypid > 1 )); do
    (( ${isclaude[$mypid]:-0} )) && { myclaude=$mypid; break; }
    mypid=${par[$mypid]:-0}
  done
  for p in ${(on)candidates}; do
    label=""
    if (( ${${(f)owned}[(Ie)$p]} )); then
      :
    elif (( myclaude && ${par[$p]} == myclaude )) && (( ${${(f)piped}[(Ie)$p]} )); then
      label=monitor
    else
      continue
    fi
    s=$(secs_of ${et[$p]})
    (( s >= 5 )) || continue                     # a parallel foreground tool call
    (( s / 60 >= older )) || continue
    seen[$p]=1
    for c in $(descendants $p); do seen[$c]=1; done
    cmd=${cmdof[$p]}
    cmd=${cmd#*eval }; cmd=${cmd%% < /dev/null*}
    cmd=${cmd#\'}; cmd=${cmd%\'}
    cmdof[$p]=$cmd
    print_block $p $label
  done
fi

# Orphans: still writing to this session's task files, no claude above them.
tasks_dirs=(/tmp/claude-$(id -u)/*/$session/tasks(N/))
if (( ${#tasks_dirs} )); then
  for p in $(lsof -Fp +D $tasks_dirs 2>/dev/null | awk '/^p/ { print substr($0,2) }' | sort -un); do
    (( ${seen[$p]:-0} )) && continue
    (( ${ancestor[$p]:-0} )) && continue
    [[ -n ${par[$p]:-} ]] || continue
    has_claude_ancestor $p && continue
    # The age limit holds here too: a subagent's shell is reparented to pid 1
    # while it runs, so without it a minute-old test run reads as stale.
    (( $(secs_of ${et[$p]}) / 60 >= older )) || continue
    seen[$p]=1
    for c in $(descendants $p); do seen[$c]=1; done
    print_block $p orphan
  done
fi
