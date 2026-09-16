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
# The session-start line also says whether `quiet-open` is on PATH — the command
# that launches a windowed app without it ever becoming active (open -g plus an
# injected AppKit shim; see the window-focus rule). The verdict is a tolerance
# for the interruption, not a licence: under either verdict a windowed launch
# goes through quiet-open first, and only an app it cannot quiet becomes an ask.
# --check and --verdict are consumed by scripts and stay exactly as they were.
#
# The allow-list lives outside this repository, as `focus-allow` in the Claude
# config dir ($CLAUDE_CONFIG_DIR, else ~/.claude): one hostname or glob per line,
# '#' comments ignored. Machine names are local configuration, not shared source.
# Absent or empty file means deny everywhere.
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

QUIET_OPEN="$(command -v quiet-open 2>/dev/null || true)"
if [ -n "$QUIET_OPEN" ]; then
	QUIET_NOTE=" · quiet-open: $QUIET_OPEN"
else
	QUIET_NOTE=" · quiet-open: not installed"
fi

if [ "$VERDICT" = "allow" ]; then
	CONTEXT="Focus policy: ALLOW${QUIET_NOTE}. The interruption is tolerated here, but a window that activates still hides a hotkey terminal: launch windowed apps through quiet-open (exit 0 + 'quiet: loaded' = focus untouched); an app it cannot quiet needs one ask per batch, stating the process count."
else
	# Assigned via `read`, not `$(cat <<EOF)`: bash 3.2, which macOS ships,
	# mishandles a heredoc inside command substitution.
	IFS= read -r -d '' CONTEXT <<-EOF || true
Focus policy: DENY${QUIET_NOTE}. Do NOT run anything that opens a window and
becomes the active app — the user is working on this screen, and a window
stealing focus interrupts them mid-sentence.

- Use the headless or offscreen mode of whatever you are running. For Godot that
  is \`--headless\`, which covers parse checks, the test suite, and any probe
  whose output is printed rather than drawn.
- When the task genuinely needs rendered pixels (a frame capture, a screenshot),
  launch through \`quiet-open <App.app> [args…]\`: exit 0 with 'quiet: loaded'
  in its output means the app never activated and no ask is needed. Off-screen
  \`--position\` and a small \`--resolution\` are not stealth; they do not stop
  activation.
- If quiet-open is not installed or cannot quiet that app, say so and ask first
  — one ask per batch, stating the process count. Then do it in ONE batched run
  rather than iterating.
- Never re-run a windowed command "just to check". Print the state instead.
EOF
fi

jq -n --arg ctx "$CONTEXT" \
	'{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
