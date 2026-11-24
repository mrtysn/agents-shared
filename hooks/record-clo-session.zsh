#!/bin/zsh
# record-clo-session.zsh — SessionStart and SessionEnd hook. Inside a tmux session, writes the
# Claude session id and folder under the tmux session's name, so clo can print them in the tab
# once the tmux session ends ("closed notebook-7f · <id> · ~/dev/notebook"). In iTerm's tmux mode
# the pane, and whatever Claude printed on exit, goes away with the session; this record is what
# is left. SessionEnd rewrites it, so a /clear leaves the new id.
#
# Never blocks and prints nothing; outside tmux it does nothing.
# The folder holding the records is CLO_SESSION_RECORDS, else
# ${XDG_STATE_HOME:-~/.local/state}/agents-shared/clo-sessions; scripts/clo reads the same one.
# Cases in hooks/tests/run-record-clo-session.sh.

[[ -n "${TMUX:-}" ]] || exit 0
input="$(cat)"
# An array: zsh keeps ${TMUX_PANE:+-t "$TMUX_PANE"} as the one word "-t %5", and tmux then
# prints nothing with status 0.
target=(); [[ -n "${TMUX_PANE:-}" ]] && target=(-t "$TMUX_PANE")
name="$(tmux display -p "${target[@]}" '#S' 2>/dev/null)" || exit 0
[[ -n "$name" ]] || exit 0
fields="$(jq -r '[.session_id // "", .cwd // ""] | @tsv' <<< "$input" 2>/dev/null)" || exit 0
id="${fields%%$'\t'*}" cwd="${fields#*$'\t'}"
[[ -n "$id" ]] || exit 0
dir="${CLO_SESSION_RECORDS:-${XDG_STATE_HOME:-$HOME/.local/state}/agents-shared/clo-sessions}"
mkdir -p -- "$dir" 2>/dev/null || exit 0
file="$dir/${name//\//_}"
print -r -- "$id"$'\t'"${cwd:-$PWD}" > "$file.$$" 2>/dev/null && mv -f -- "$file.$$" "$file" 2>/dev/null
exit 0
