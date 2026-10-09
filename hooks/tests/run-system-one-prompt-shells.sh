#!/bin/bash
# DESC: Test the stale-background-shell warning in system-one-prompt.sh with a fake lister
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../system-one-prompt.sh"
TMP=$(mktemp -d); export TMPDIR=$TMP
trap 'rm -rf "$TMP"' EXIT
fail=0

now_ms() { perl -MTime::HiRes=time -e 'printf "%d\n", time * 1000'; }
check() { # name, condition result
    if [ "$2" = ok ]; then echo "ok     $1"; else echo "FAIL   $1"; fail=$((fail + 1)); fi
}

printf '#!/bin/sh\nprintf "4242  02:10:00  until grep done log; do sleep 30; done\\n"\n' > "$TMP/stale"
printf '#!/bin/sh\nexit 0\n' > "$TMP/none"
chmod +x "$TMP/stale" "$TMP/none"
payload=$(jq -n '{session_id: "shells-test", prompt: "hello there friend", transcript_path: "/nonexistent"}')

out=$(printf '%s' "$payload" | SESSION_SHELLS_LISTER="$TMP/stale" "$HOOK")
ctx=$(printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext // empty')
case "$ctx" in *"1 background shell(s) running over 60 minutes"*"4242"*) r=ok ;; *) r=no ;; esac
check "stale shell produces additionalContext" "$r"
[ "$(printf '%s' "$out" | jq -r '.decision // "none"')" = none ] && r=ok || r=no
check "no block decision" "$r"

rm -f "$TMP"/session-shells-warn-*
out=$(printf '%s' "$payload" | SESSION_SHELLS_LISTER="$TMP/none" "$HOOK")
[ -z "$out" ] && r=ok || r=no
check "no shells: silent" "$r"

rm -f "$TMP"/session-shells-warn-*
printf '%s' "$payload" | SESSION_SHELLS_LISTER="$TMP/none" "$HOOK" >/dev/null
t0=$(now_ms)
printf '%s' "$payload" | SESSION_SHELLS_LISTER="$TMP/none" "$HOOK" >/dev/null
ms=$(( $(now_ms) - t0 ))
[ "$ms" -lt 1000 ] && r=ok || r=no
check "no shells: ${ms}ms under 1000ms" "$r"

echo "shell-warning cases failed: $fail"
[ "$fail" = 0 ]
