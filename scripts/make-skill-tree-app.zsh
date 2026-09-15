#!/bin/zsh
# DESC: Build "Skill Tree.app" in ~/Applications so ⌘-space opens the skill board.
#
# The bundle is a plist and a runner script, nothing else. The runner starts skill-tree.py on its
# usual port (or just opens the page when one is already serving) and lets it exit on its own after
# twenty idle minutes, so nothing lingers. Re-run after moving this checkout.
#
# Usage:
#   scripts/make-skill-tree-app.zsh              # → ~/Applications/Skill Tree.app
#   scripts/make-skill-tree-app.zsh /some/dir    # → /some/dir/Skill Tree.app

set -euo pipefail

here=${0:A:h}
dest=${1:-$HOME/Applications}
app="$dest/Skill Tree.app"
port=8797

[[ -d $dest ]] || mkdir -p "$dest"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>skill-tree</string>
    <key>CFBundleIdentifier</key>
    <string>local.skill-tree</string>
    <key>CFBundleName</key>
    <string>Skill Tree</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST

cat > "$app/Contents/MacOS/skill-tree" <<RUNNER
#!/bin/zsh
# Spotlight launches with a bare environment; put the shims back so python3 and claude resolve.
export PATH="\$HOME/.local/bin:\$HOME/.asdf/shims:/opt/homebrew/bin:/usr/local/bin:\$HOME/bin:/usr/bin:/bin"
[[ -r "\${XDG_CONFIG_HOME:-\$HOME/.config}/agents-shared/env.zsh" ]] && source "\${XDG_CONFIG_HOME:-\$HOME/.config}/agents-shared/env.zsh"
url="http://127.0.0.1:$port/"
if curl -fsS --max-time 1 "\$url" >/dev/null 2>&1; then
    open "\$url"
else
    exec python3 "$here/skill-tree.py" --port $port --idle-exit 20 >> "\$HOME/Library/Logs/skill-tree.log" 2>&1
fi
RUNNER
chmod +x "$app/Contents/MacOS/skill-tree"

if command -v make-icon >/dev/null 2>&1; then
    make-icon tree "#199e70" "$app/Contents/Resources/AppIcon.icns" >/dev/null 2>&1 \
        && /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$app/Contents/Info.plist" || true
fi

touch "$app"
print "built: ${app/#$HOME/~}"
print "Spotlight: ⌘-space → \"skill tree\""
