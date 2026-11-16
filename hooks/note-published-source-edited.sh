#!/bin/bash
# PostToolUse hook (Edit, Write, MultiEdit): forwards to hooks/personal/note-published-source-edited.sh
#
# The hook it forwards to serves only the personal profile (the owner's own publishing tool), so its
# text lives under hooks/personal/. This stub keeps the name that a shared settings.json already
# calls: on the personal profile (scripts/agent-profile) it hands the PostToolUse payload to that
# script; on any other profile, or none, it does nothing and exits 0.
#
# Bash, not zsh, to match the hooks beside it. Written for bash 3.2 (macOS /bin/bash).

HERE=$(cd "$(dirname "$(readlink "${BASH_SOURCE[0]}" 2>/dev/null || printf '%s' "${BASH_SOURCE[0]}")")" && pwd)
TARGET="$HERE/personal/note-published-source-edited.sh"
[ -x "$TARGET" ] || exit 0
[ "$("$HERE/../scripts/agent-profile" 2>/dev/null)" = personal ] || exit 0
exec "$TARGET"
