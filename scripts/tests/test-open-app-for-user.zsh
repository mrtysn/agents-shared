#!/bin/zsh
# Launches a throwaway background-only app (LSBackgroundOnly: no window, no Dock icon, never
# active) through open-app-for-user with agent session and tmux variables set, and checks the
# environment the app received.
set -u
here="${0:A:h}"
tool="$here/../open-app-for-user"
dir="$(mktemp -d "${TMPDIR:-/tmp}/open-app-for-user-test.XXXXXX")"
trap 'rm -rf -- "$dir"' EXIT
app="$dir/EnvProbe.app"
mkdir -p "$app/Contents/MacOS"
cat > "$app/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>probe</string>
<key>CFBundleIdentifier</key><string>local.test.open-app-for-user-probe</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSBackgroundOnly</key><true/>
</dict></plist>
EOF
print -r -- '#!/bin/zsh' > "$app/Contents/MacOS/probe"
print -r -- "env > '$dir/env.tmp' && mv '$dir/env.tmp' '$dir/env'" >> "$app/Contents/MacOS/probe"
chmod +x "$app/Contents/MacOS/probe"

fails=0 n=0
fail() { (( fails++ )); print -r -- "FAIL $1"; }

(( n++ ))
"$tool" >/dev/null 2>&1; [[ $? == 2 ]] || fail "no arguments should exit 2"

(( n++ ))
CLAUDECODE=1 CLAUDE_CODE_CHILD_SESSION=1 CLAUDE_PID=1 TMUX=/tmp/s,1,0 TMUX_PANE=%1 PROBE_LEAK=yes \
    "$tool" -n "$app" || fail "open-app-for-user exited $?"
repeat 50 { [[ -e "$dir/env" ]] && break; sleep 0.1 }
if [[ ! -e "$dir/env" ]]; then
    fail "the probe app never ran"
else
    got="$(<"$dir/env")"
    [[ "$got" != *CLAUDE* ]] || fail "CLAUDE variables reached the app"
    [[ "$got" != *TMUX* ]] || fail "TMUX variables reached the app"
    [[ "$got" != *PROBE_LEAK* ]] || fail "an arbitrary caller variable reached the app"
    [[ "$got" == *"HOME=$HOME"* ]] || fail "HOME did not reach the app"
fi

rm -f -- "$dir/env"
(( n++ ))
CLAUDECODE=1 "$tool" --env PROBE_WANTED=1 -n "$app" || fail "open-app-for-user --env exited $?"
repeat 50 { [[ -e "$dir/env" ]] && break; sleep 0.1 }
got="$(<"$dir/env" 2>/dev/null || true)"
[[ "$got" == *PROBE_WANTED=1* && "$got" != *CLAUDECODE* ]] || fail "--env did not pass exactly the named variable"

print "open-app-for-user tests: $n cases, $fails failed"
(( fails == 0 ))
