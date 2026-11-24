#!/bin/bash
# PreToolUse hook (Bash): refuse a plain `open` that launches an app from an agent's shell.
#
# `open` hands the app it launches the caller's whole environment (measured Nov 2026: all 13
# CLAUDE_* variables and TMUX reached a test app through `open -g`, with or without -n), and the
# app hands it to everything it starts later. In Nov 2026 an agent reopened the terminal app with
# `open -g -a iTerm` after editing its preferences. Every tab opened after that carried the
# agent's session: each new Claude Code session there took CLAUDE_CODE_CHILD_SESSION=1, believed
# it was that agent's child and saved no transcript, and the leaked TMUX sent clo past its tmux
# launch. Five other apps launched the same way carried the same variables.
#
# Refused: `open` (or /usr/bin/open) at a command boundary with -a, -b, or an argument ending in
# .app. Passes: open-app-for-user, which launches through `env -i`; quiet-open, for windows only
# an agent looks at; `env -i … open`; `open` of a file, folder or URL with no app named.
#
# Bash, not zsh, to match the other hooks and to keep working on Linux boxes that sync
# agents-shared without /bin/zsh.

set -e

COMMAND=$(jq -r '.tool_input.command // empty')
[ -n "$COMMAND" ] || exit 0

# A command boundary, optional VAR=value prefixes, then open by name or path. `env -i … open`
# does not start at a boundary, so it passes.
START='(^|[;&|(`]|&&|\|\|)[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(/usr/bin/)?open[[:space:]]'
APP="${START}"'([^;&|]*[[:space:]])?(-[A-Za-z]*[ab][A-Za-z]*([[:space:]]|$)|[^[:space:];&|]*\.app/?['"'"'"]?([[:space:];&|)]|$))'

if printf '%s' "$COMMAND" | grep -Eq "$APP"; then
    cat >&2 <<'EOF'
BLOCKED: `open` would hand this shell's environment to the app it launches.
The app keeps it and passes it to everything it starts: a terminal launched this way gives every
new tab this session's CLAUDE_* variables (new Claude Code sessions there stop saving their
transcripts) and its TMUX pane.

- An app the user will use: run `open-app-for-user <the same open arguments>`. It runs
  `open -g` with the environment the Dock gives an app. A variable the app really needs goes
  in as `--env NAME=VALUE`.
- A window only you look at (a screenshot, a test run): `quiet-open <App.app>`.
EOF
    exit 2
fi
exit 0
