#!/bin/bash
# SessionStart hook: bring up the system-one decision-model server.
#
# `system-one start` itself returns at once (it detaches laya-serve and its idle
# watchdog into their own session and does not wait for the model, which loads
# in about 4 s; hooks that ask before then fail open), so it is run in the
# foreground here: a backgrounded wrapper could be cut off mid-start when the
# hook's process group ends, and `start` holds a lock so two sessions starting
# in the same second cannot both launch a server. Reports one line to the user
# and exits 0 in every case: an unconfigured or broken system-one must never
# cost a session. The wrapper is found next to this hook (scripts/system-one);
# paths.local.sh's AGENTS_SHARED_DIR is the fallback, matching the other hooks.
#
# Bash 3.2, like the hooks beside it.

set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WRAPPER="$HERE/../scripts/system-one"
if [ ! -x "$WRAPPER" ]; then
    f="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/paths.local.sh"
    [ -r "$f" ] && . "$f"
    WRAPPER="${AGENTS_SHARED_DIR:-}/scripts/system-one"
fi

say() {
    jq -cn --arg m "$1" '{systemMessage: $m}'
    exit 0
}

CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-one.local.sh"
[ -r "$CONFIG" ] || say "system-one: not configured (no system-one.local.sh)"
[ -x "$WRAPPER" ] || say "system-one: wrapper not found (scripts/system-one)"

# One line from the wrapper: "system-one: running (...)", "starting on ...",
# "another start is in progress", or its error; all become the session note.
OUT=$("$WRAPPER" start 2>&1 </dev/null) || true
OUT=$(printf '%s\n' "$OUT" | tail -n 1)
say "${OUT:-system-one: start returned nothing}"
