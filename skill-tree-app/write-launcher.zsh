#!/bin/zsh
# DESC: Write the Skill Tree app's launcher script to skill-tree-app/build/skill-tree
#
# The launcher is the bundle's executable. It finds the agents-shared checkout from the
# AgentsSharedDir key of its own Info.plist, opens the page when skill-tree.py already answers
# on its port, and otherwise starts it, which exits on its own after twenty idle minutes.
set -euo pipefail

HERE=${0:A:h}
PORT=8797
OUT="$HERE/build/skill-tree"

mkdir -p "${OUT:h}"

cat > "$OUT" <<RUNNER
#!/bin/zsh
# Spotlight launches with a bare environment; put the shims back so python3 and claude resolve.
export PATH="\$HOME/.local/bin:\$HOME/.asdf/shims:/opt/homebrew/bin:/usr/local/bin:\$HOME/bin:/usr/bin:/bin"
[[ -r "\${XDG_CONFIG_HOME:-\$HOME/.config}/agents-shared/env.zsh" ]] && source "\${XDG_CONFIG_HOME:-\$HOME/.config}/agents-shared/env.zsh"
checkout=\$(plutil -extract AgentsSharedDir raw "\${0:A:h:h}/Info.plist")
url="http://127.0.0.1:$PORT/"
if curl -fsS --max-time 1 "\$url" >/dev/null 2>&1; then
    open "\$url"
else
    exec python3 "\$checkout/scripts/skill-tree.py" --port $PORT --idle-exit 20 >> "\$HOME/Library/Logs/skill-tree.log" 2>&1
fi
RUNNER
chmod +x "$OUT"
