#!/bin/bash
# DESC: Run the note-published-source-edited PostToolUse hook against a fake published.json and notes-publish
#
# Bash, not zsh, to match the hook under test.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../note-published-source-edited.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export CLAUDE_CONFIG_DIR="$TMP/config"
export XDG_STATE_HOME="$TMP/state"
mkdir -p "$XDG_STATE_HOME/notes-publish" "$TMP/bin"

SRC="$TMP/report.html"
OTHER="$TMP/unrelated.html"
printf '{"report.html": {"sha": "abc", "source": "%s"}}\n' "$SRC" > "$XDG_STATE_HOME/notes-publish/published.json"

# a stand-in for notes-publish: answers --where for the one recorded source, exits 1 for anything else
cat > "$TMP/bin/notes-publish" <<STUB
#!/bin/bash
[ "\$1" = --where ] && [ "\$2" = "$SRC" ] && { echo "\$2 is published as report.html (local edited)"; exit 0; }
exit 1
STUB
chmod +x "$TMP/bin/notes-publish"

fail=0
check() { # label expected(nudge|pass) session tool file
    local out
    out=$(jq -n --arg s "$3" --arg t "$4" --arg f "$5" '{session_id:$s, tool_name:$t, tool_input:{file_path:$f}}' |
        PATH="$TMP/bin:$PATH" "$HOOK")
    local got=pass
    [ -n "$out" ] && printf '%s' "$out" | jq -e '.hookSpecificOutput.additionalContext | test("published as report.html")' >/dev/null && got=nudge
    if [ "$got" = "$2" ]; then echo "ok   $1"; else echo "FAIL $1: got $got, want $2"; fail=1; fi
}

check "recorded source is noted"          nudge s1 Edit  "$SRC"
check "same file again, same session"     pass  s1 Write "$SRC"
check "new session is noted again"        nudge s2 Write "$SRC"
check "unrelated file passes"             pass  s3 Edit  "$OTHER"
check "no file_path passes"               pass  s4 Edit  ""

rm -f "$XDG_STATE_HOME/notes-publish/published.json"
check "no published.json passes"          pass  s5 Edit  "$SRC"

[ "$fail" = 0 ] && echo "all passed"
exit "$fail"
