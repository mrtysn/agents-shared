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
STATE="$CFG/subagent-guard/sessions"
# The machine's own budget file never reaches the cases: they read an empty config folder.
export XDG_CONFIG_HOME="$CFG/xdg"
LOCAL="$XDG_CONFIG_HOME/agents-shared"
mkdir -p "$LOCAL"

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
rm -f "$STATE/$SID.count"
# the budget passes, the first spawn past it asks, the rest of the session passes
for _ in 1 2 3 4 5 6 7 8; do check pass /p/x.jsonl; done
check ask /p/x.jsonl
check pass /p/x.jsonl
# with bypass-all-sessions, a fresh session past its budget passes; nesting is still refused
rm -f "$STATE/$SID.count" "$STATE/$SID.asked"
mkdir -p "$CFG/subagent-guard" && touch "$CFG/subagent-guard/bypass-all-sessions"
for _ in 1 2 3 4 5 6 7 8 9 10; do check pass /p/x.jsonl; done
check deny /p/x/subagents/agent-1.jsonl
# removed, the next spawn past the budget asks again
rm -f "$CFG/subagent-guard/bypass-all-sessions"
check ask /p/x.jsonl
# launched with CLAUDE_SUBAGENT_GUARD_BYPASS=1, a fresh session past its budget passes; nesting is still refused
rm -f "$STATE/$SID.count" "$STATE/$SID.asked"
export CLAUDE_SUBAGENT_GUARD_BYPASS=1
for _ in 1 2 3 4 5 6 7 8 9 10; do check pass /p/x.jsonl; done
check deny /p/x/subagents/agent-1.jsonl
unset CLAUDE_SUBAGENT_GUARD_BYPASS
# unset again, a fresh session asks past its budget
rm -f "$STATE/$SID.count" "$STATE/$SID.asked"
for _ in 1 2 3 4 5 6 7 8; do check pass /p/x.jsonl; done
check ask /p/x.jsonl

# the count and the asked mark survive a reboot: a wiped /tmp neither restarts the count nor asks again
rm -f "$STATE/$SID.count" "$STATE/$SID.asked"
for _ in 1 2 3 4 5 6 7 8; do check pass /p/x.jsonl; done
check ask /p/x.jsonl
rm -f "/tmp/claude-spawn-count-$SID" "/tmp/claude-spawn-asked-$SID"
for _ in 1 2 3 4 5 6 7 8 9 10; do check pass /p/x.jsonl; done
# a session whose state is still in /tmp from before is carried over: an approved session is not asked again
rm -f "$STATE/$SID.count" "$STATE/$SID.asked"
printf '9\n' > "/tmp/claude-spawn-count-$SID"; : > "/tmp/claude-spawn-asked-$SID"
check pass /p/x.jsonl
rm -f "/tmp/claude-spawn-count-$SID" "/tmp/claude-spawn-asked-$SID"

fresh() { rm -f "$STATE/$SID.count" "$STATE/$SID.asked"; }
printf 'acct %s\n' "$CFG" > "$LOCAL/claude-accounts"
# a * line sets the budget for every account
fresh; printf '* 3\n' > "$LOCAL/subagent-spawn-budget"
for _ in 1 2 3; do check pass /p/x.jsonl; done
check ask /p/x.jsonl
# the account's own line wins over *
fresh; printf '* 3\nacct 5\n' > "$LOCAL/subagent-spawn-budget"
for _ in 1 2 3 4 5; do check pass /p/x.jsonl; done
check ask /p/x.jsonl
# unlimited never asks; nesting is still refused
fresh; printf '* 3\nacct unlimited\n' > "$LOCAL/subagent-spawn-budget"
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do check pass /p/x.jsonl; done
check deny /p/x/subagents/agent-1.jsonl
# another account's line does not apply
fresh; printf 'other unlimited\n' > "$LOCAL/subagent-spawn-budget"
for _ in 1 2 3 4 5 6 7 8; do check pass /p/x.jsonl; done
check ask /p/x.jsonl
# a bad line asks on every spawn instead of falling back
fresh; printf '* lots\n' > "$LOCAL/subagent-spawn-budget"
check ask /p/x.jsonl
check ask /p/x.jsonl
# a bad line does not stop a session launched with the bypass env var, or with bypass-all on
fresh; export CLAUDE_SUBAGENT_GUARD_BYPASS=1
for _ in 1 2 3; do check pass /p/x.jsonl; done
unset CLAUDE_SUBAGENT_GUARD_BYPASS
fresh; touch "$CFG/subagent-guard/bypass-all-sessions"
for _ in 1 2 3; do check pass /p/x.jsonl; done
rm -f "$CFG/subagent-guard/bypass-all-sessions"
# a leading zero is base 10: 08 lets eight spawns pass, then asks (bash would read 08 as bad octal)
fresh; printf '* 08\n' > "$LOCAL/subagent-spawn-budget"
for _ in 1 2 3 4 5 6 7 8; do check pass /p/x.jsonl; done
check ask /p/x.jsonl
# 010 is ten, not octal eight
fresh; printf '* 010\n' > "$LOCAL/subagent-spawn-budget"
for _ in 1 2 3 4 5 6 7 8 9 10; do check pass /p/x.jsonl; done
check ask /p/x.jsonl

echo "$((total - fail))/$total passed"
[ "$fail" = 0 ]
