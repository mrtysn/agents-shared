#!/bin/bash
# Decides whether an agent on this machine may open a window that steals focus.
#
# Some machines are shared with work happening on the same screen, where a game
# engine, browser, or simulator taking focus mid-keystroke is an interruption.
# Others are personal. The answer depends on the machine rather than the task,
# so it belongs in the environment instead of each session's judgement.
#
# Fails closed: an unlisted machine is DENY. Allowing one is a deliberate act.
#
# Usage:
#   focus-policy.sh            # SessionStart hook: emits JSON additionalContext
#   focus-policy.sh --check    # exit 0 = allowed, 1 = denied
#   focus-policy.sh --verdict  # prints "allow" or "deny"
#
# The allow-list lives outside this repository, in ~/.claude/focus-allow: one
# hostname or glob per line, '#' comments ignored. Machine names are local
# configuration, not shared source. Absent or empty file means deny everywhere.
#
# FOCUS_POLICY_HOST overrides the detected name, for testing the matching.

set -uo pipefail

# scutil first: `hostname -s` can return a DHCP-derived name that has nothing to
# do with the configured one. The fallback covers non-macOS hosts.
HOST="${FOCUS_POLICY_HOST:-$(scutil --get ComputerName 2>/dev/null || hostname -s)}"
HOST="${HOST%%.*}"

ALLOW_FILE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/focus-allow"

verdict() {
	[ -f "$ALLOW_FILE" ] || { echo "deny"; return; }
	local host_lc pattern pattern_lc
	host_lc="$(printf '%s' "$HOST" | tr '[:upper:]' '[:lower:]')"
	while IFS= read -r pattern; do
		pattern="${pattern%%#*}"
		pattern="$(printf '%s' "$pattern" | tr -d '[:space:]')"
		[ -z "$pattern" ] && continue
		pattern_lc="$(printf '%s' "$pattern" | tr '[:upper:]' '[:lower:]')"
		# shellcheck disable=SC2053
		if [[ "$host_lc" == $pattern_lc ]]; then
			echo "allow"
			return
		fi
	done < "$ALLOW_FILE"
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
	CONTEXT="Focus policy: ALLOW. Opening a GUI window is fine on this machine."
else
	# Assigned via `read`, not `$(cat <<EOF)`: bash 3.2, which macOS ships,
	# mishandles a heredoc inside command substitution.
	IFS= read -r -d '' CONTEXT <<-EOF || true
Focus policy: DENY. Do NOT run anything that opens a window and takes keyboard
focus — the user is working on this screen, and a window stealing focus
interrupts them mid-sentence.

- Use the headless or offscreen mode of whatever you are running. For Godot that
  is \`--headless\`, which covers parse checks, the test suite, and any probe
  whose output is printed rather than drawn.
- When the task genuinely needs rendered pixels (a frame capture, a screenshot),
  say so and ask first. Then do it in ONE batched run rather than iterating, and
  push the window off the working display with the tool's own flags (Godot:
  \`--screen N\` / \`--position X,Y\`).
- Never re-run a windowed command "just to check". Print the state instead.
EOF
fi

jq -n --arg ctx "$CONTEXT" \
	'{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
