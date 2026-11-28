#!/bin/bash
# PreToolUse guard for Agent/Task spawns:
#  - denies spawns coming from inside a subagent (no nesting)
#  - past BUDGET spawns per session, asks ONCE; after that the rest of the session is allowed
#    (a hook's "ask" overrides allow rules, so without this the prompt returns on every spawn)
# BUDGET is 8 unless the machine-local file that scripts/subagent-spawn-budget reads (shape:
# scripts/subagent-spawn-budget.example) gives this account a number or "unlimited".
# Wired in settings.json as $CLAUDE_CONFIG_DIR/hooks/subagent-guard.sh, a symlink to this file.
BUDGET=8

input=$(cat)

transcript=$(echo "$input" | jq -r '.transcript_path // ""')
if [[ "$transcript" == */subagents/* ]]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Nested subagent spawning is disabled. Do the work yourself and return findings to the main loop."}}'
  exit 0
fi

sid=$(echo "$input" | jq -r '.session_id // "unknown"')
# The count and the "asked" mark live beside the config, not in /tmp: a session outlives a reboot
# (it is resumed), and a /tmp wiped by the reboot made the guard ask a session again that had
# already been approved, holding an unattended orchestrated run at the prompt for hours.
state_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/subagent-guard/sessions"
mkdir -p "$state_dir"
count_file="$state_dir/$sid.count"
asked_file="$state_dir/$sid.asked"
# A session whose state is still in /tmp from before this change carries it over once.
[[ ! -e "$count_file" && -e "/tmp/claude-spawn-count-$sid" ]] && cp "/tmp/claude-spawn-count-$sid" "$count_file"
[[ ! -e "$asked_file" && -e "/tmp/claude-spawn-asked-$sid" ]] && : > "$asked_file"
n=$(cat "$count_file" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$count_file"

# Bypassed sessions never ask, so they are let through before the budget is read: a bad budget
# line must not stop an unattended session that nobody is there to answer.
# CC Sessions' Guards menu makes this file to skip the ask in every session, until removed
all_file="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/subagent-guard/bypass-all-sessions"
# A session launched with CLAUDE_SUBAGENT_GUARD_BYPASS=1 skips the ask: an orchestrator sets
# it on the sessions it starts, whose design, build, review and fix agents pass the budget.
[[ -e "$all_file" || "${CLAUDE_SUBAGENT_GUARD_BYPASS:-}" == 1 ]] && exit 0

# The machine-local budget for this account. Anything but a plain number or "unlimited" (a bad
# line, or stray output) asks on every spawn with the reason, rather than guessing a budget.
src="${BASH_SOURCE[0]}"
while [ -L "$src" ]; do t=$(readlink "$src"); [[ "$t" == /* ]] && src=$t || src="$(dirname "$src")/$t"; done
budget_script="$(cd "$(dirname "$src")/.." && pwd)/scripts/subagent-spawn-budget"
if [ -x "$budget_script" ]; then
  errors=$(mktemp)
  local_budget=$("$budget_script" 2>"$errors")
  status=$?
  problem=$(cat "$errors"); rm -f "$errors"
  if [ "$status" = 0 ] && [[ -z "$local_budget" || "$local_budget" =~ ^([0-9]{1,9}|unlimited)$ ]]; then
    [ -n "$local_budget" ] && BUDGET=$local_budget
  else
    [ -n "$problem" ] || problem="subagent-spawn-budget printed '$local_budget', not a number or unlimited."
    reason=$(printf '%s Fix the file; until then every spawn asks.' "$problem" | jq -Rs .)
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":$reason}}"
    exit 0
  fi
fi
[ "$BUDGET" = unlimited ] && exit 0

if (( 10#$n > 10#$BUDGET )) && [[ ! -e "$asked_file" ]]; then
  : > "$asked_file"
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"Spawn #$n this session (budget $BUDGET) — approve for the rest of this session?\"}}"
fi
exit 0
