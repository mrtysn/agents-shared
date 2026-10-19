#!/bin/bash
# PreToolUse hook: Block commands that kill or restart the adb server
#
# The adb server is shared by everything on the machine: every phone, watch and
# projector the user holds over wireless adb hangs off it, and a restart drops
# them all. Nothing redials them until ADB Reconnect's next poll or the user's
# next click. On Oct 19 2026 a session starting a headless emulator ran
# `adb kill-server` twice in four minutes, and the user's screenshot of a
# projector failed in between with "device not found".
#
# An agent never needs it. A new emulator registers with the running server by
# itself, and the server is kept by launchd (local.adb-reconnect.server), which
# respawns it, so a "stuck" server is a report to the user, not a restart.
#
# Blocked: `adb [flags] kill-server` by any path to adb, `killall`/`pkill` naming
# adb, and launchctl stop/kill/bootout/kickstart of the server's agent.
# There is deliberately no override: the user restarts it from ADB Reconnect.
#
# Bash, not zsh, to match the other hooks and to keep working on Linux boxes
# that sync agents-shared without /bin/zsh.

set -e

INPUT=$(cat)

COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
    exit 0
fi

deny() {
    echo "BLOCKED: $1" >&2
    echo "Restarting the adb server drops every device the user holds over wireless adb" >&2
    echo "(phones, watches, a projector), and nothing redials them at once." >&2
    echo "A new emulator attaches to the running server by itself: just wait for it in 'adb devices'." >&2
    echo "If the server really is stuck, tell the user; ADB Reconnect has a Restart server action." >&2
    exit 2
}

# A command boundary, then the word: so `grep "adb kill-server" notes.md` passes.
START='(^|[;&|(`]|&&|\|\|)[[:space:]]*([^[:space:];&|]*/)?'

if printf '%s' "$COMMAND" | grep -Eq "${START}adb([[:space:]]+[^;&|]*)?[[:space:]]+kill-server"; then
    deny "adb kill-server"
fi

if printf '%s' "$COMMAND" | grep -Eq "${START}(killall|pkill)([[:space:]]+[^[:space:];&|]+)*[[:space:]]+['\"]?([^[:space:];&|]*/)?adb['\"]?($|[[:space:];&|])"; then
    deny "killing adb processes"
fi

if printf '%s' "$COMMAND" | grep -Eq "${START}launchctl[[:space:]]+(stop|kill|bootout|kickstart|unload|remove)[[:space:]][^;&|]*local\.adb-reconnect\.server"; then
    deny "stopping the adb server's launchd agent"
fi

exit 0
