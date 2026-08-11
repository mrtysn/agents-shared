#!/bin/bash
# Stamps a trial skill's last_used date when the Skill tool invokes it.
#
# Wired as a PostToolUse hook on Skill. Without it, a trial's age can only mean
# "days since install", which says nothing about whether the skill earns its
# place — the one thing worth knowing before removing it. With it, age means
# "days unused", so a trial in regular use never goes stale and one installed on
# an impulse ages exactly as fast as the impulse did.
#
# Silent and always successful. This runs inside a tool call, and bookkeeping
# must never turn into a visible failure of the user's actual work: a missing
# jq, an unreadable .trial.json, or a name that belongs to a managed skill all
# exit 0 having done nothing.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIAL="$SCRIPT_DIR/../scripts/trial-skill.sh"
[ -x "$TRIAL" ] || exit 0

# The hook payload arrives on stdin; a Skill call carries the name in
# tool_input.skill. Anything else (no payload, another tool, a plugin skill with
# a namespaced name that matches no local directory) resolves to nothing and the
# touch below no-ops.
SKILL_NAME="$(jq -r '.tool_input.skill // empty' 2>/dev/null | head -1)"
[ -n "$SKILL_NAME" ] || exit 0

"$TRIAL" touch "$SKILL_NAME" >/dev/null 2>&1 || true
exit 0
