#!/bin/bash
# PreToolUse hook (Bash, Write, Edit): refuse a plain `open` that launches an app from an agent's shell.
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
# The same line inside a script is refused too. The Nov 2026 relaunch above was in a scratch
# script (wait for iTerm to quit, run an import, then reopen it with open -g -a), which a check of
# the Bash command alone never saw.
#   Write, Edit  a script file (.sh, .zsh, .bash, .command, or a `#!` first line) whose new text
#                holds such a line. Docs and notes that quote the command pass.
#   Bash         a command that runs a script holding one: `zsh FILE`, `bash FILE`, `sh FILE`,
#                `source FILE`, `. FILE`, `nohup FILE`, `exec FILE`, or FILE alone at a command
#                boundary.
# Comment lines in a script are skipped.
#
# Bash, not zsh, to match the other hooks and to keep working on Linux boxes that sync
# agents-shared without /bin/zsh.

set -e

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // "Bash"')
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')

# A command boundary, optional VAR=value prefixes, then open by name or path. `env -i … open`
# does not start at a boundary, so it passes.
START='(^|[;&|(`]|&&|\|\|)[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*(/usr/bin/)?open[[:space:]]'
APP="${START}"'([^;&|]*[[:space:]])?(-[A-Za-z]*[ab][A-Za-z]*([[:space:]]|$)|[^[:space:];&|]*\.app/?['"'"'"]?([[:space:];&|)]|$))'

# Lines of script text that launch an app with `open`, comment lines left out.
script_hits() {
    grep -vE '^[[:space:]]*#' | grep -E "$APP" | head -3
}

# path [first line]: a shell script by its name or its first line.
is_script() {
    case "$1" in *.sh|*.zsh|*.bash|*.command) return 0 ;; esac
    first=${2-}
    if [ -z "$first" ] && [ -r "$1" ]; then first=$(head -1 "$1" 2>/dev/null); fi
    case "$first" in '#!'*sh*) return 0 ;; esac
    return 1
}

# A path from the command, resolved against the session's cwd.
resolve() {
    p=$1
    case "$p" in "~/"*) p="$HOME/${p#??}" ;; esac
    case "$p" in /*) ;; *) [ -n "$CWD" ] && p="$CWD/$p" ;; esac
    printf '%s' "$p"
}

# where, offending lines
refuse() {
    {
        printf 'BLOCKED: %s launches an app with a plain `open`:\n%s\n\n' "$1" "$2"
        cat <<'EOF'
`open` hands the caller's environment to the app it launches, and a script run from this session
has this session's environment. The app keeps it and passes it to everything it starts: a
terminal launched this way gives every new tab this session's CLAUDE_* variables (new Claude Code
sessions there stop saving their transcripts) and its TMUX pane.

- An app the user will use: `open-app-for-user <the same open arguments>`. It runs `open -g`
  with the environment the Dock gives an app. A variable the app really needs goes in as
  `--env NAME=VALUE`.
- A window only you look at (a screenshot, a test run): `quiet-open <App.app>`.
EOF
    } >&2
    exit 2
}

case "$TOOL" in
    Write|Edit)
        FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty')
        if [ "$TOOL" = Write ]; then
            TEXT=$(printf '%s' "$INPUT" | jq -r '.tool_input.content // empty')
            is_script "$FILE" "$(printf '%s\n' "$TEXT" | head -1)" || exit 0
        else
            TEXT=$(printf '%s' "$INPUT" | jq -r '.tool_input.new_string // empty')
            is_script "$FILE" || exit 0
        fi
        HITS=$(printf '%s\n' "$TEXT" | script_hits)
        [ -z "$HITS" ] || refuse "the script $FILE" "$HITS"
        exit 0
        ;;
esac

COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
[ -n "$COMMAND" ] || exit 0

HITS=$(printf '%s\n' "$COMMAND" | grep -E "$APP" | head -3 || true)
[ -z "$HITS" ] || refuse "this command" "$HITS"

# Scripts the command runs: after a shell, source, nohup or exec, or alone at a command boundary.
RUNS='(^|[;&|(`]|&&|\|\|)[[:space:]]*((/bin/|/usr/bin/)?(zsh|bash|sh|nohup|exec|source|\.)[[:space:]]+(-[A-Za-z]+[[:space:]]+)*)*[^[:space:];&|<>()`]+'
WORDS=$(printf '%s\n' "$COMMAND" | grep -oE "$RUNS" | sed -E 's/^[;&|(`[:space:]]*//; s/.*[[:space:]]//' || true)
for word in $WORDS; do
    path=$(resolve "$word")
    [ -f "$path" ] || continue
    is_script "$path" || continue
    HITS=$(script_hits < "$path" || true)
    [ -z "$HITS" ] || refuse "the script $path" "$HITS"
done
exit 0
