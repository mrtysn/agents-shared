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
count_file="/tmp/claude-spawn-count-$sid"
asked_file="/tmp/claude-spawn-asked-$sid"
n=$(cat "$count_file" 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > "$count_file"

# The machine-local budget for this account; a bad line asks with the error rather than guessing.
src="${BASH_SOURCE[0]}"
while [ -L "$src" ]; do t=$(readlink "$src"); [[ "$t" == /* ]] && src=$t || src="$(dirname "$src")/$t"; done
budget_script="$(cd "$(dirname "$src")/.." && pwd)/scripts/subagent-spawn-budget"
if [ -x "$budget_script" ]; then
  if local_budget=$("$budget_script" 2>&1); then
    [ -n "$local_budget" ] && BUDGET=$local_budget
  else
    reason=$(printf '%s Fix the file; until then every spawn asks.' "$local_budget" | jq -Rs .)
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":$reason}}"
    exit 0
  fi
fi
[ "$BUDGET" = unlimited ] && exit 0

# CC Sessions' Guards menu makes this file to skip the ask in every session, until removed
all_file="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/subagent-guard/bypass-all-sessions"
# A session launched with CLAUDE_SUBAGENT_GUARD_BYPASS=1 skips the ask: an orchestrator sets
# it on the sessions it starts, whose design, build, review and fix agents pass the budget.
if (( n > BUDGET )) && [[ ! -e "$asked_file" ]] && [[ ! -e "$all_file" ]] \
   && [[ "${CLAUDE_SUBAGENT_GUARD_BYPASS:-}" != 1 ]]; then
  : > "$asked_file"
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"Spawn #$n this session (budget $BUDGET) — approve for the rest of this session?\"}}"
fi
exit 0
