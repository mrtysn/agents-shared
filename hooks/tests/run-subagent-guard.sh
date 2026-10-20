#!/bin/bash
# DESC: Run the subagent-guard PreToolUse hook through its budget, nesting and bypass cases
#
# Bash, not zsh, to match the hook under test.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../subagent-guard.sh"
CFG=$(mktemp -d)
SID="subagent-guard-test-$$"
trap 'rm -rf "$CFG"; rm -f "/tmp/claude-spawn-count-$SID" "/tmp/claude-spawn-asked-$SID"' EXIT

total=0 fail=0
# check WANT TRANSCRIPT: one spawn, its verdict (pass = no output) against the expected one
check() {
    local want=$1 transcript=$2 out got=pass
    total=$((total + 1))
    out=$(jq -n --arg s "$SID" --arg t "$transcript" '{session_id: $s, transcript_path: $t}' | CLAUDE_CONFIG_DIR=$CFG "$HOOK")
    [ -n "$out" ] && got=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.permissionDecision')
    if [ "$got" != "$want" ]; then fail=$((fail + 1)); printf 'FAIL  spawn %s: want %s got %s\n' "$total" "$want" "$got"; fi
}

# a spawn from inside a subagent is refused whatever the budget or bypass
check deny /p/x/subagents/agent-1.jsonl
rm -f "/tmp/claude-spawn-count-$SID"
# the budget passes, the first spawn past it asks, the rest of the session passes
for _ in 1 2 3 4 5 6 7 8; do check pass /p/x.jsonl; done
check ask /p/x.jsonl
check pass /p/x.jsonl
# with bypass-all-sessions, a fresh session past its budget passes; nesting is still refused
rm -f "/tmp/claude-spawn-count-$SID" "/tmp/claude-spawn-asked-$SID"
mkdir -p "$CFG/subagent-guard" && touch "$CFG/subagent-guard/bypass-all-sessions"
for _ in 1 2 3 4 5 6 7 8 9 10; do check pass /p/x.jsonl; done
check deny /p/x/subagents/agent-1.jsonl
# removed, the next spawn past the budget asks again
rm -f "$CFG/subagent-guard/bypass-all-sessions"
check ask /p/x.jsonl

echo "$((total - fail))/$total passed"
[ "$fail" = 0 ]
