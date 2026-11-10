#!/bin/zsh
# Runs scripts/clo as a program (so its set -euo pipefail applies) against stand-in tmux,
# defaults and claude, and checks how a launch reaches tmux.
set -u
here="${0:A:h}"
clo="$here/../clo"
stub="$(mktemp -d "${TMPDIR:-/tmp}/clo-test.XXXXXX")"
trap 'rm -rf -- "$stub"' EXIT
calls="$stub/calls"

cat > "$stub/tmux" <<EOF
#!/bin/zsh
print -r -- "tmux \$*" >> "$calls"
[[ \$1 == has-session ]] && exit 1
[[ \$1 == display ]] && { print -r -- "\${STUB_PANES:-11} work-7f"; exit 0; }
exit 0
EOF
cat > "$stub/claude" <<EOF
#!/bin/zsh
print -r -- "claude \$* name=\${CLAUDE_CODE_SESSION_NAME:-}" >> "$calls"
EOF
# STUB_OPEN sets OpenTmuxWindowsIn; every other key reads as missing (defaults fails).
cat > "$stub/defaults" <<EOF
#!/bin/zsh
[[ \$3 == OpenTmuxWindowsIn && -n "\${STUB_OPEN:-}" ]] && { print -r -- "\$STUB_OPEN"; exit 0; }
exit 1
EOF
# uv runs iterm-place-tmux-tab.py through its shebang.
cat > "$stub/uv" <<EOF
#!/bin/zsh
print -r -- "uv \$*" >> "$calls"
EOF
chmod +x "$stub"/tmux "$stub"/claude "$stub"/defaults "$stub"/uv
mkdir -p "$stub/Library/Logs"

fails=0 n=0
check() {  # check NAME EXPECTED-RC PATTERN... -- ENV... -- ARGS...
    local name="$1" want_rc="$2"; shift 2
    local -a pats envs args
    while [[ "$1" != -- ]]; do pats+=("$1"); shift; done; shift
    while [[ "$1" != -- ]]; do envs+=("$1"); shift; done; shift
    args=("$@")
    : > "$calls"
    (cd "$stub" && env -u TMUX -u CLAUDE_CONFIG_DIR -u ITERM_SESSION_ID HOME="$stub" PATH="$stub:$PATH" \
        "${envs[@]}" "$clo" "${args[@]}") >/dev/null 2>&1
    local rc=$?
    sleep 0.3  # the tab placer runs in the background
    local got="$(<"$calls")" p ok=1
    (( n++ ))
    [[ $rc == $want_rc ]] || ok=0
    for p in "${pats[@]}"; do [[ "$got" == *$~p* ]] || ok=0; done
    if (( ! ok )); then
        (( fails++ ))
        print -r -- "FAIL $name: rc=$rc (want $want_rc)"; print -r -- "$got" | sed 's/^/    /'
    fi
}

check "iTerm launch survives unset prefs and attaches with -CC" 0 \
    "tmux has-session -t =*" "tmux -CC new-session -s * claude --resume abc" -- \
    TERM_PROGRAM=iTerm.app -- --run-claude --resume abc
check "has-session never carries -CC" 0 \
    "tmux has-session*" -- TERM_PROGRAM=iTerm.app -- --run-claude
[[ "$(grep -c -- '-CC has-session' "$calls")" == 0 ]] || { (( fails++ )); print "FAIL -CC on has-session"; }
check "outside iTerm no -CC" 0 \
    "tmux new-session -s * claude --model x" -- TERM_PROGRAM=Apple_Terminal -- --run-claude --model x
[[ "$(<"$calls")" != *-CC* ]] || { (( fails++ )); print "FAIL -CC outside iTerm"; }
check "config dir is handed to the tmux session" 0 \
    "tmux new-session * -e CLAUDE_CONFIG_DIR=/cfg/x claude" -- \
    TERM_PROGRAM=Apple_Terminal CLAUDE_CONFIG_DIR=/cfg/x -- --run-claude
check "CLO_TMUX=0 runs claude directly" 0 \
    "claude --model y" -- CLO_TMUX=0 -- --run-claude --model y

check "tab placer starts when tmux tabs open in the attaching window" 0 \
    "uv run --quiet --script */iterm-place-tmux-tab.py --gateway ABC-1 --ready *" -- \
    TERM_PROGRAM=iTerm.app STUB_OPEN=2 ITERM_SESSION_ID=w0t13p0:ABC-1 -- --run-claude
check "no tab placer when tmux opens native windows" 0 \
    "tmux -CC new-session*" -- TERM_PROGRAM=iTerm.app STUB_OPEN=0 ITERM_SESSION_ID=w0t13p0:ABC-1 -- --run-claude
[[ "$(<"$calls")" != *uv* ]] || { (( fails++ )); print "FAIL tab placer ran with native windows"; }

base="${${stub:t}//[^A-Za-z0-9_-]/-}"  # clo names a session after the folder, which is $stub
check "the tmux name is handed to claude as its peer name" 0 \
    "tmux new-session -s $base-?? -c * -e CLAUDE_CODE_SESSION_NAME=$base-?? claude" -- \
    TERM_PROGRAM=Apple_Terminal -- --run-claude
[[ "$(<"$calls")" =~ "new-session -s ([^ ]+) .*CLAUDE_CODE_SESSION_NAME=([^ ]+)" && $match[1] == $match[2] ]] \
    || { (( fails++ )); print "FAIL tmux and peer names differ"; }
mkdir -p "$stub/.claude/sessions"
for h in {0..255}; do printf '{"name": "%s-%02x"}\n' "$base" $h; done > "$stub/.claude/sessions/1.json"
check "a name a running session already has as its peer name is skipped" 0 \
    "tmux new-session*" -- TERM_PROGRAM=Apple_Terminal -- --run-claude
[[ "$(grep -c 'tmux has-session' "$calls")" == 20 ]] || { (( fails++ )); print "FAIL taken peer names were not skipped"; }
rm -f -- "$stub/.claude/sessions/1.json"
check "alone in a tmux session, claude takes the session's name" 0 \
    "claude --model z name=work-7f" -- TMUX=/tmp/s,1,0 -- --run-claude --model z
check "with several panes, claude names itself" 0 \
    "claude --model z name=" -- TMUX=/tmp/s,1,0 STUB_PANES=12 -- --run-claude --model z
[[ "$(<"$calls")" != *name=work-7f* ]] || { (( fails++ )); print "FAIL shared pane name"; }
: > "$stub/cd"
check "tmux mode marks the client tab for closing" 0 \
    "tmux -CC new-session*" -- TERM_PROGRAM=iTerm.app CLO_CD_FILE="$stub/cd" -- --run-claude
[[ -e "$stub/cd.close" ]] || { (( fails++ )); print "FAIL no close marker in tmux mode"; }
rm -f -- "$stub/cd.close"
check "no close marker outside tmux mode" 0 \
    "tmux new-session*" -- TERM_PROGRAM=Apple_Terminal CLO_CD_FILE="$stub/cd" -- --run-claude
[[ ! -e "$stub/cd.close" ]] || { (( fails++ )); print "FAIL close marker outside tmux mode"; }

print "clo launch tests: $n cases, $fails failed"
(( fails == 0 ))
