#!/bin/bash
# DESC: Probe hook — write the JSON a hook event receives to a file, then allow the call
#
# Point any hook event at this to see exactly what it is handed: which
# tool_input fields exist, what cwd and permission_mode look like, whether
# content is present. Writes to $HOOK_STDIN_OUT if set, else
# <config dir>/hook-stdin.json. Always exits 0 — it observes, never blocks.

set -uo pipefail
out="${HOOK_STDIN_OUT:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hook-stdin.json}"
cat > "$out"
exit 0
