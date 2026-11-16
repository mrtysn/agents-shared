#!/bin/zsh
# DESC: Reopen the sessions iterm-revive.py lists as ended, as tabs of the hotkey window
# Runs each `cd <cwd> && claude --resume <uuid>` line from `iterm-revive.py resume` in a
# new iTerm window, then moves its tabs into the hotkey window.
set -euo pipefail
here=${0:A:h}
lines=("${(@f)$(python3 $here/iterm-revive.py resume)}")
lines=(${(M)lines:#*claude --resume *})
(( ${#lines} )) || { echo "no ended sessions to reopen"; exit 0; }
script='tell application "iTerm2"
create window with default profile'
first=1
for cmd in $lines; do
  cmd=${cmd//\\/\\\\}; cmd=${cmd//\"/\\\"}
  if (( first )); then
    script+="
tell current session of current window to write text \"$cmd\""
    first=0
  else
    script+="
tell current window
create tab with default profile
tell current session to write text \"$cmd\"
end tell"
  fi
done
script+="
end tell"
osascript -e "$script"
sleep 2
$here/iterm-move-tabs-to-hotkey.py
