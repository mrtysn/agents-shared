#!/bin/bash
# PreToolUse guard for Agent/Task spawns:
#  - denies spawns coming from inside a subagent (no nesting)
#  - past BUDGET spawns per session, asks ONCE; after that the rest of the session is allowed
#    (a hook's "ask" overrides allow rules, so without this the prompt returns on every spawn)
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

# CC Sessions' Guards menu makes this file to skip the ask in every session, until removed
all_file="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/subagent-guard/bypass-all-sessions"

if (( n > BUDGET )) && [[ ! -e "$asked_file" ]] && [[ ! -e "$all_file" ]]; then
  : > "$asked_file"
  echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"ask\",\"permissionDecisionReason\":\"Spawn #$n this session (budget $BUDGET) — approve for the rest of this session?\"}}"
fi
exit 0
