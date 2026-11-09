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
exit 0
EOF
cat > "$stub/claude" <<EOF
#!/bin/zsh
print -r -- "claude \$*" >> "$calls"
EOF
# iTerm's tmux prefs unset: defaults read fails, as it does for a missing key.
cat > "$stub/defaults" <<EOF
#!/bin/zsh
exit 1
EOF
chmod +x "$stub"/tmux "$stub"/claude "$stub"/defaults

fails=0 n=0
check() {  # check NAME EXPECTED-RC PATTERN... -- ENV... -- ARGS...
    local name="$1" want_rc="$2"; shift 2
    local -a pats envs args
    while [[ "$1" != -- ]]; do pats+=("$1"); shift; done; shift
    while [[ "$1" != -- ]]; do envs+=("$1"); shift; done; shift
    args=("$@")
    : > "$calls"
    (cd "$stub" && env -u TMUX -u CLAUDE_CONFIG_DIR PATH="$stub:$PATH" "${envs[@]}" "$clo" "${args[@]}") >/dev/null 2>&1
    local rc=$? got="$(<"$calls")" p ok=1
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

print "clo launch tests: $n cases, $fails failed"
(( fails == 0 ))
