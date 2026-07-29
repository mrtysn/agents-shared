#!/bin/bash
# Decides whether an agent on THIS machine may open a window that steals focus.
#
# Some machines are shared with real work happening on the same screen — a
# Godot capture or a browser launch that grabs focus mid-sentence is a genuine
# interruption there. Others are personal and nobody cares. The difference is
# the machine, not the task, so the answer belongs in the environment rather
# than in each agent's judgement.
#
# Fails closed: an unknown machine is DENY. Adding a machine is a deliberate
# act; forgetting to add one costs a little convenience, forgetting to deny one
# costs the user their attention.
#
# Usage:
#   focus-policy.sh            # SessionStart hook — emits JSON additionalContext
#   focus-policy.sh --check    # exit 0 = allowed, 1 = denied (for scripts)
#   focus-policy.sh --verdict  # prints "allow" or "deny"
#
# Override the built-in list per machine with ~/.claude/focus-allow — one
# hostname or glob per line, '#' comments ignored. The file REPLACES the
# built-in list, so an empty file means deny everywhere.

set -uo pipefail

HOST="$(scutil --get ComputerName 2>/dev/null || hostname -s)"
HOST="${HOST%%.*}"

# Machines where a window may take focus. Globs, matched case-insensitively.
DEFAULT_ALLOW=(
	"*m2max*"   # home machine — nobody else is looking at this screen
)

OVERRIDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/focus-allow"

allow_list() {
	if [ -f "$OVERRIDE" ]; then
		grep -vE '^\s*(#|$)' "$OVERRIDE" 2>/dev/null
		return
	fi
	printf '%s\n' "${DEFAULT_ALLOW[@]}"
}

verdict() {
	local host_lc pattern_lc
	host_lc="$(printf '%s' "$HOST" | tr '[:upper:]' '[:lower:]')"
	while IFS= read -r pattern; do
		[ -z "$pattern" ] && continue
		pattern_lc="$(printf '%s' "$pattern" | tr '[:upper:]' '[:lower:]')"
		# shellcheck disable=SC2053 — glob match is the point
		if [[ "$host_lc" == $pattern_lc ]]; then
			echo "allow"
			return
		fi
	done < <(allow_list)
	echo "deny"
}

VERDICT="$(verdict)"

case "${1:-}" in
	--check)
		[ "$VERDICT" = "allow" ] && exit 0 || exit 1
		;;
	--verdict)
		echo "$VERDICT"
		exit 0
		;;
esac

if [ "$VERDICT" = "allow" ]; then
	CONTEXT="Focus policy: ALLOW (host ${HOST}). Opening a GUI window is fine here."
else
	# Not `CONTEXT=$(cat <<EOF ...)` — macOS ships bash 3.2, whose parser
	# mishandles a heredoc inside command substitution and dies at EOF.
	IFS= read -r -d '' CONTEXT <<EOF || true
Focus policy: DENY (host ${HOST}). Do NOT run anything that opens a window and
takes keyboard focus — the user is working on this screen and a window stealing
focus interrupts them mid-sentence.

- Use the headless/offscreen mode of whatever you are running. For Godot that is
  \`--headless\`, which covers parse checks, the test suite, and any probe whose
  output is printed rather than drawn.
- When the task genuinely needs rendered pixels (a frame capture, a browser
  screenshot), say so and ask first. Then do it in ONE batched run rather than
  iterating, and push the window off the working display with the tool's own
  flags (Godot: \`--screen N\` / \`--position X,Y\`).
- Never re-run a windowed command "just to check". Print the state instead.
EOF
fi

jq -n --arg ctx "$CONTEXT" \
	'{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
