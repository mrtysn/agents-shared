#!/bin/bash
# DESC: Test the system-one on/off switch: wrapper enable/disable/start/status/ask and every hook, no server, no model
#
# Bash, to match the hooks and the runners beside it. Needs no server and loads
# no model: everything runs against a temporary CLAUDE_CONFIG_DIR holding a
# copied config, a temporary state dir and an unused port, so the real
# ~/.claude, the real shadow log and any running server are never touched.
# `enable` is exercised against a venv that does not exist, so its `start`
# half dies in the config check before launching anything.

set -uo pipefail   # no -e: every check reports and the tally decides the exit

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOKS="$HERE/.."
WRAPPER="$HERE/../../scripts/system-one"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/system-one-disabled-test.XXXXXX")
trap 'rm -rf -- "$TMP"' EXIT

# A clean slate: no SYSTEM_ONE_* from the caller, everything pointed into TMP.
for v in $(compgen -v SYSTEM_ONE_); do unset "$v"; done
export CLAUDE_CONFIG_DIR="$TMP/cfg"
export SYSTEM_ONE_STATE_DIR="$TMP/state"
export SYSTEM_ONE_PORT=17999
export XDG_STATE_HOME="$TMP/xdg"
export SESSION_SHELLS_LISTER=/nonexistent
mkdir -p "$CLAUDE_CONFIG_DIR" "$SYSTEM_ONE_STATE_DIR"
CONFIG="$CLAUDE_CONFIG_DIR/system-one.local.sh"

fail=0
check() { # label, condition-exit-code
    if [ "$2" = 0 ]; then printf 'ok    %s\n' "$1"; else printf 'FAIL  %s\n' "$1"; fail=$((fail + 1)); fi
}
# eq label got want
eq() { if [ "$2" = "$3" ]; then check "$1" 0; else check "$1 (got: $2 / want: $3)" 1; fi; }

fresh_config() {   # the example's shape: comments, blank lines, a required value, a mode
    cat > "$CONFIG" <<EOF
# machine-local test config
SYSTEM_ONE_VENV="$TMP/no-such-venv"

# trailing comment mentioning SYSTEM_ONE_ENABLED=1 does not count
SYSTEM_ONE_MODE=shadow
EOF
}

# ---- wrapper: disable appends, preserves, is idempotent --------------------
fresh_config
cp "$CONFIG" "$TMP/orig"
out=$("$WRAPPER" disable 2>&1); rc=$?
eq "disable exits 0" "$rc" 0
case "$out" in *"disabled in $CONFIG"*"server was not running"*) r=0 ;; *) r=1 ;; esac
check "disable says so and stops (nothing to stop)" "$r"
eq "disable appends exactly one line" "$(diff "$TMP/orig" "$CONFIG" | grep -c '^>')" 1
eq "disable leaves every other line" "$(diff "$TMP/orig" "$CONFIG" | grep -c '^<')" 0
eq "the appended line" "$(tail -n 1 "$CONFIG")" "SYSTEM_ONE_ENABLED=0"
cp "$CONFIG" "$TMP/once"
"$WRAPPER" disable >/dev/null 2>&1
cmp -s "$TMP/once" "$CONFIG"; check "disable twice leaves the file unchanged" "$?"

chmod 640 "$CONFIG"
"$WRAPPER" enable >/dev/null 2>&1
eq "the file's mode survives an edit" "$(ls -l "$CONFIG" | cut -c1-10)" "-rw-r-----"
"$WRAPPER" disable >/dev/null 2>&1

# a file with no trailing newline still gets a clean appended line
printf 'SYSTEM_ONE_MODE=shadow' > "$CONFIG"
"$WRAPPER" disable >/dev/null 2>&1
eq "no-trailing-newline file: two lines" "$(grep -c '' "$CONFIG")" 2
eq "no-trailing-newline file: mode line kept" "$(head -n 1 "$CONFIG")" "SYSTEM_ONE_MODE=shadow"

# ---- wrapper: an existing line is edited in place --------------------------
cat > "$CONFIG" <<EOF
# top
SYSTEM_ONE_VENV="$TMP/no-such-venv"
#SYSTEM_ONE_ENABLED=1
SYSTEM_ONE_ENABLED=1
SYSTEM_ONE_MODE=shadow
EOF
"$WRAPPER" disable >/dev/null 2>&1
eq "in-place: line count unchanged" "$(grep -c '' "$CONFIG")" 5
eq "in-place: active line rewritten in its position" "$(sed -n 4p "$CONFIG")" "SYSTEM_ONE_ENABLED=0"
eq "in-place: commented line untouched" "$(sed -n 3p "$CONFIG")" "#SYSTEM_ONE_ENABLED=1"
eq "in-place: mode line kept" "$(sed -n 5p "$CONFIG")" "SYSTEM_ONE_MODE=shadow"

# a symlinked config is edited at its target; the link survives
mkdir -p "$TMP/real"
cp "$CONFIG" "$TMP/real/target.sh"
rm -f -- "$CONFIG"
ln -s "$TMP/real/target.sh" "$CONFIG"
sed -i.bak 's/^SYSTEM_ONE_ENABLED=0$/SYSTEM_ONE_ENABLED=1/' "$TMP/real/target.sh"
"$WRAPPER" disable >/dev/null 2>&1
[ -L "$CONFIG" ]; check "symlinked config: link survives" "$?"
eq "symlinked config: target edited" "$(grep -c '^SYSTEM_ONE_ENABLED=0$' "$TMP/real/target.sh")" 1
rm -f -- "$CONFIG"

# ---- wrapper: disabled behaviour -------------------------------------------
fresh_config
"$WRAPPER" disable >/dev/null 2>&1

out=$("$WRAPPER" start 2>&1); rc=$?
eq "start refuses with one line" "$out" "system-one: disabled (system-one enable to turn it on)"
[ "$rc" != 0 ]; check "start exits non-zero when disabled" "$?"

out=$("$WRAPPER" status 2>&1)
case "$(printf '%s\n' "$out" | head -n 1)" in disabled*) r=0 ;; *) r=1 ;; esac
check "status prints disabled first" "$r"
printf '%s\n' "$out" | grep -q '^server: *not running'; check "status still reports the server" "$?"

out=$(printf '%s' '{"state":"x","questions":{"q":{"type":"noul","instructions":"y"}}}' | "$WRAPPER" ask --fail-open --hook t --session s 2>&1); rc=$?
eq "ask --fail-open: no output" "$out" ""
eq "ask --fail-open: exit 0" "$rc" 0
out=$(printf '%s' '{"state":"x","questions":{"q":{"type":"noul","instructions":"y"}}}' | "$WRAPPER" ask 2>&1); rc=$?
case "$out" in *"disabled (system-one enable to turn it on)"*) r=0 ;; *) r=1 ;; esac
check "ask without --fail-open: a clear line" "$r"
[ "$rc" != 0 ]; check "ask without --fail-open: non-zero" "$?"
[ ! -e "$SYSTEM_ONE_STATE_DIR/shadow" ]; check "ask writes no shadow row" "$?"
[ ! -e "$SYSTEM_ONE_STATE_DIR/last-request" ]; check "ask touches no last-request (no curl made)" "$?"

# an exported SYSTEM_ONE_ENABLED=0 disables without any file change, and
# enable refuses to pretend otherwise
fresh_config
cp "$CONFIG" "$TMP/orig"
out=$(SYSTEM_ONE_ENABLED=0 "$WRAPPER" start 2>&1)
eq "env 0 with a clean file: start refuses" "$out" "system-one: disabled (system-one enable to turn it on)"
out=$(SYSTEM_ONE_ENABLED=0 "$WRAPPER" enable 2>&1); rc=$?
[ "$rc" != 0 ]; check "enable under an exported 0: refuses" "$?"
cmp -s "$TMP/orig" "$CONFIG"; check "enable under an exported 0: file untouched" "$?"

# ---- wrapper: enable edits the file idempotently ---------------------------
# The venv named in the config does not exist, so the start half of enable
# dies in the config check; the file edit comes first and is what is tested.
fresh_config
"$WRAPPER" disable >/dev/null 2>&1
out=$("$WRAPPER" enable 2>&1); rc=$?
case "$out" in *"enabled in $CONFIG"*) r=0 ;; *) r=1 ;; esac
check "enable says so" "$r"
case "$out" in *"no python in $TMP/no-such-venv/bin"*) r=0 ;; *) r=1 ;; esac
check "enable then runs start (stopped here by the missing venv)" "$r"
eq "enable rewrote the line in place" "$(grep -c '^SYSTEM_ONE_ENABLED=1$' "$CONFIG")" 1
eq "enable leaves no 0 behind" "$(grep -c '^SYSTEM_ONE_ENABLED=0$' "$CONFIG")" 0
eq "enable keeps the other lines" "$(grep -c '^SYSTEM_ONE_MODE=shadow$' "$CONFIG")" 1
cp "$CONFIG" "$TMP/once"
"$WRAPPER" enable >/dev/null 2>&1
cmp -s "$TMP/once" "$CONFIG"; check "enable twice leaves the file unchanged" "$?"
out=$("$WRAPPER" status 2>&1)
case "$(printf '%s\n' "$out" | head -n 1)" in disabled*) r=1 ;; *) r=0 ;; esac
check "status is not 'disabled' once enabled" "$r"

# ---- hooks: every one exits 0 at once, silent, and writes nothing ----------
fresh_config
"$WRAPPER" disable >/dev/null 2>&1
rm -rf -- "$SYSTEM_ONE_STATE_DIR"; mkdir -p "$SYSTEM_ONE_STATE_DIR"

long=$(printf 'word %.0s' $(seq 1 700))
jq -cn --arg t "$long" '{type:"assistant", message:{content:[{type:"text", text:$t}]}}' > "$TMP/transcript.jsonl"
questions='[{"question":"Which one?","header":"Pick","multiSelect":false,"options":[{"label":"A","description":"a"},{"label":"B","description":"b"}]}]'
payload_bash=$(jq -cn '{session_id:"s1", cwd:"/tmp", tool_name:"Bash", tool_use_id:"t1", tool_input:{command:"rm -rf /tmp/some-dir"}}')
payload_prompt=$(jq -cn --arg tp "$TMP/transcript.jsonl" '{session_id:"s1", prompt:"should we delete the old build directory now", transcript_path:$tp}')
payload_stop=$(jq -cn --arg tp "$TMP/transcript.jsonl" '{session_id:"s1", transcript_path:$tp, stop_hook_active:false}')
payload_ask=$(jq -cn --argjson q "$questions" --arg tp "$TMP/transcript.jsonl" '{session_id:"s1", transcript_path:$tp, tool_name:"AskUserQuestion", tool_input:{questions:$q}}')
payload_post=$(jq -cn '{session_id:"s1", cwd:"/tmp", hook_event_name:"PostToolUse", tool_use_id:"t1", tool_input:{command:"rm -rf /tmp/some-dir"}, tool_response:{stdout:"", stderr:"", interrupted:false}}')

# a verdict row the post hook would receipt if it were enabled
mkdir -p "$SYSTEM_ONE_STATE_DIR/shadow/bash"
printf '%s\n' '{"ts":"2026-10-13T10:00:00+0300","ts_epoch":1,"id":"row-1","hook":"bash","session_id":"s1","tool_use_id":"t1","state_sha256":"abc","answers":{},"would_act":false,"fired":[]}' > "$SYSTEM_ONE_STATE_DIR/shadow/bash/s1.jsonl"
cp "$SYSTEM_ONE_STATE_DIR/shadow/bash/s1.jsonl" "$TMP/bash-log.before"

run_hook() { # name payload
    out=$(printf '%s' "$2" | "$HOOKS/$1" 2>&1); rc=$?
    eq "$1: exit 0" "$rc" 0
    eq "$1: no output" "$out" ""
}
run_hook system-one-bash.sh "$payload_bash"
run_hook system-one-prompt.sh "$payload_prompt"
run_hook system-one-stop.sh "$payload_stop"
run_hook system-one-ask.sh "$payload_ask"
run_hook system-one-bash-post.sh "$payload_post"

cmp -s "$TMP/bash-log.before" "$SYSTEM_ONE_STATE_DIR/shadow/bash/s1.jsonl"; check "bash-post wrote no receipt" "$?"
eq "no other file appeared in the state dir" "$(find "$SYSTEM_ONE_STATE_DIR" -type f | wc -l | tr -d ' ')" 1

# the control: the same post hook does write its receipt when enabled (an
# exported 1 beats the file), so the check above can tell the difference
printf '%s' "$payload_post" | SYSTEM_ONE_ENABLED=1 "$HOOKS/system-one-bash-post.sh" >/dev/null 2>&1
eq "control: enabled bash-post appends the receipt" "$(grep -c '"kind":"outcome"' "$SYSTEM_ONE_STATE_DIR/shadow/bash/s1.jsonl")" 1

# start hook: one systemMessage line, and nothing launched
out=$("$HOOKS/system-one-start.sh" </dev/null 2>&1); rc=$?
eq "system-one-start.sh: exit 0" "$rc" 0
eq "system-one-start.sh: says disabled" "$(printf '%s' "$out" | jq -r '.systemMessage // empty')" "system-one: disabled"
[ ! -e "$SYSTEM_ONE_STATE_DIR/server.pid" ]; check "system-one-start.sh: no server pid written" "$?"

# the stale-shell warning of the prompt hook does not depend on system-one
printf '#!/bin/sh\nprintf "4242  02:10:00  sleep 9999\\n"\n' > "$TMP/stale"
chmod +x "$TMP/stale"
out=$(printf '%s' "$payload_prompt" | TMPDIR="$TMP" SESSION_SHELLS_LISTER="$TMP/stale" "$HOOKS/system-one-prompt.sh" 2>&1)
case "$out" in *"background shell(s) running over 60 minutes"*) r=0 ;; *) r=1 ;; esac
check "prompt hook still warns about stale shells while disabled" "$r"

echo "disabled-switch checks failed: $fail"
[ "$fail" = 0 ]
