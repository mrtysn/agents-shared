#!/bin/zsh
# Runs scripts/clo as a program (so its set -euo pipefail applies) against stand-in tmux,
# defaults and claude, and checks how a launch reaches tmux.
set -u
here="${0:A:h}"
clo="$here/../clo"
stub="$(mktemp -d "${TMPDIR:-/tmp}/clo-test.XXXXXX")"
trap 'rm -rf -- "$stub"' EXIT
calls="$stub/calls"

export CLO_SESSION_RECORDS="$stub/rec"
# has-session finds a session only while $stub/alive-NAME exists. new-session and attach-session
# play a session that ends (or, with STUB_DETACH, a client that detaches and leaves it alive);
# STUB_RECORD is what record-clo-session.zsh would have written; STUB_RC is tmux's exit code.
cat > "$stub/tmux" <<EOF
#!/bin/zsh
print -r -- "tmux \$*" >> "$calls"
a=("\$@"); [[ \$a[1] == -CC ]] && shift a
[[ \$a[1] == has-session ]] && { [[ -e "$stub/alive-\${a[3]#=}" ]] && exit 0; exit 1; }
if [[ \$a[1] == (new|attach)-session ]]; then
    n="\${a[3]#=}"
    [[ -n "\${STUB_RECORD:-}" ]] && { mkdir -p "\$CLO_SESSION_RECORDS"; print -r -- "\$STUB_RECORD" > "\$CLO_SESSION_RECORDS/\$n"; }
    if [[ -n "\${STUB_DETACH:-}" ]]; then : > "$stub/alive-\$n"; else rm -f -- "$stub/alive-\$n"; fi
    exit \${STUB_RC:-0}
fi
# Real tmux prints nothing for "-t %41" passed as one word.
for x in "\$@"; do [[ \$x == "-t "* ]] && exit 0; done
# A pane clo is running in: its shell is the test script, an ancestor of clo.
[[ \$1 == display && \$* == *pane_pid* ]] && { print -r -- "\${STUB_PANE_PID-$$}"; exit 0; }
[[ \$1 == display ]] && { print -r -- "\${STUB_PANES:-11} work-7f"; exit 0; }
exit 0
EOF
cat > "$stub/claude" <<EOF
#!/bin/zsh
print -r -- "claude \$* name=\${CLAUDE_CODE_SESSION_NAME:-} child=\${CLAUDE_CODE_CHILD_SESSION:-} cc=\${CLAUDECODE:-} cfg=\${CLAUDE_CONFIG_DIR:-} tmux=\${TMUX:-} run=\${CLO_RUN:-}" >> "$calls"
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
    (cd "${check_cwd:-$stub}" && env -u TMUX -u CLAUDE_CONFIG_DIR -u ITERM_SESSION_ID HOME="$stub" PATH="$stub:$PATH" \
        "${envs[@]}" "$clo" "${args[@]}") >"$stub/out" 2>&1
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

# A terminal an agent reopened carries that agent's session: CLAUDE_PID names a process that is
# not an ancestor of clo, so its variables are dropped; CLAUDE_CONFIG_DIR is clo's own and stays.
stale=(CLO_TMUX=0 CLAUDE_PID=999999 CLAUDECODE=1 CLAUDE_CODE_CHILD_SESSION=1 CLAUDE_CODE_SESSION_ID=old
       CLAUDE_CONFIG_DIR=/cfg/k CLO_RUN=/tmp/old-run)
check "another session's variables are dropped" 0 \
    "claude --model s name= child= cc= cfg=/cfg/k tmux= run=" -- "${stale[@]}" -- --run-claude --model s
check "the variables of the claude clo runs under are kept" 0 \
    "claude --model s * child=1 cc=1 *" -- "${stale[@]/CLAUDE_PID=999999/CLAUDE_PID=$$}" -- --run-claude --model s
check "a marker with no CLAUDE_PID is dropped" 0 \
    "claude --model s * child= cc= *" -- CLO_TMUX=0 CLAUDE_PID= CLAUDECODE=1 CLAUDE_CODE_CHILD_SESSION=1 -- --run-claude --model s
# A leaked TMUX names a pane this terminal is not in: clo then starts its own tmux session.
check "TMUX from a pane clo is not in is dropped" 0 \
    "tmux new-session -s *" -- TERM_PROGRAM=Apple_Terminal TMUX=/tmp/s,1,0 TMUX_PANE=%41 STUB_PANE_PID=999999 -- --run-claude
check "in its own pane, named by TMUX_PANE, clo keeps TMUX and runs claude there" 0 \
    "tmux display -p -t %41 *" "claude --model p * tmux=/tmp/s,1,0" -- TMUX=/tmp/s,1,0 TMUX_PANE=%41 -- --run-claude --model p
check "TMUX naming a dead server is dropped" 0 \
    "tmux new-session -s *" -- TERM_PROGRAM=Apple_Terminal TMUX=/tmp/s,1,0 STUB_PANE_PID= -- --run-claude

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
# 20 names tried, then one has-session after tmux returns.
[[ "$(grep -c 'tmux has-session' "$calls")" == 21 ]] || { (( fails++ )); print "FAIL taken peer names were not skipped"; }
rm -f -- "$stub/.claude/sessions/1.json"
check "alone in a tmux session, claude takes the session's name" 0 \
    "claude --model z name=work-7f" -- TMUX=/tmp/s,1,0 -- --run-claude --model z
check "with several panes, claude names itself" 0 \
    "claude --model z name=" -- TMUX=/tmp/s,1,0 STUB_PANES=12 -- --run-claude --model z
[[ "$(<"$calls")" != *name=work-7f* ]] || { (( fails++ )); print "FAIL shared pane name"; }
check "CLO_LAUNCHED_BY marks the new tmux session in the same command" 0 \
    "tmux new-session -s $base-?? * claude ; set-option -t =$base-??: @launched_by orch-1f" -- \
    TERM_PROGRAM=Apple_Terminal CLO_LAUNCHED_BY=orch-1f -- --run-claude
# The stub accepts any target; replay the recorded command, detached, on a real tmux server of its
# own, since `set-option -t` resolves a pane target, where a bare "=name" is not found.
real_tmux="$(PATH="${PATH//$stub:/}" whence -p tmux 2>/dev/null)"
if [[ -n "$real_tmux" ]]; then
    sock="clo-test-$$"
    recorded=(${=${"$(grep 'new-session' "$calls")"#tmux }})
    recorded[1]=(new-session -d)
    recorded[$recorded[(i)claude]]=cat
    "$real_tmux" -L "$sock" -f /dev/null "${recorded[@]}" 2>/dev/null
    got="$("$real_tmux" -L "$sock" list-panes -a -F '#{@launched_by}' 2>/dev/null)"
    "$real_tmux" -L "$sock" kill-server 2>/dev/null
    (( n++ ))
    [[ "$got" == orch-1f ]] || { (( fails++ )); print -r -- "FAIL a real tmux did not take the marker (got: ${got:-nothing})"; }
fi
check "clo launch --launched-by marks the session" 0 \
    "tmux new-session * claude --model m* ; set-option -t =* @launched_by orch-2a" -- \
    TERM_PROGRAM=Apple_Terminal -- launch --dir "$stub" --model m --launched-by orch-2a
check "clo launch --launched-by with no name exits 2" 2 -- \
    TERM_PROGRAM=Apple_Terminal -- launch --dir "$stub" --model m --launched-by ""
check "no marker without CLO_LAUNCHED_BY" 0 \
    "tmux new-session*" -- TERM_PROGRAM=Apple_Terminal -- --run-claude
[[ "$(<"$calls")" != *@launched_by* ]] || { (( fails++ )); print "FAIL marker set without a launcher"; }
check "inside tmux the marker goes on the current session" 0 \
    "tmux set-option @launched_by orch-3c" "claude --model z" -- \
    TMUX=/tmp/s,1,0 CLO_LAUNCHED_BY=orch-3c -- --run-claude --model z
: > "$stub/cd"
check "tmux mode leaves the client tab open: no close marker" 0 \
    "tmux -CC new-session*" -- TERM_PROGRAM=iTerm.app CLO_CD_FILE="$stub/cd" -- --run-claude
[[ ! -e "$stub/cd.close" ]] || { (( fails++ )); print "FAIL close marker written"; }

# When the session ends, clo prints the Claude session it held.
check "an ended session prints its tmux name, id and folder" 0 \
    "tmux -CC new-session -s $base-?? *" -- TERM_PROGRAM=iTerm.app STUB_RECORD=$'sid-1\t'"$stub/x" -- --run-claude
[[ "$(<"$stub/out")" =~ "closed $base-[0-9a-f]{2} · sid-1 · ~/x" ]] \
    || { (( fails++ )); print -r -- "FAIL closed line: $(<"$stub/out")"; }
[[ -z "$(ls "$stub/rec" 2>/dev/null)" ]] || { (( fails++ )); print "FAIL record kept after printing"; }
check "a detached client prints nothing and keeps the record" 0 \
    "tmux -CC new-session*" -- TERM_PROGRAM=iTerm.app STUB_DETACH=1 STUB_RECORD=$'sid-2\t/y' -- --run-claude
[[ "$(<"$stub/out")" != *closed* && -n "$(ls "$stub/rec" 2>/dev/null)" ]] \
    || { (( fails++ )); print -r -- "FAIL detach: $(<"$stub/out")"; }
rm -rf -- "$stub/rec" "$stub"/alive-*(N)
mkdir -p "$stub/rec"
for h in {0..255}; do printf 'stale\t/old\n' > "$stub/rec/$(printf '%s-%02x' "$base" $h)"; done
check "a record left by an earlier session of the same name is not printed" 0 \
    "tmux new-session*" -- TERM_PROGRAM=Apple_Terminal -- --run-claude
[[ "$(<"$stub/out")" == *"no Claude session id was recorded"* && "$(<"$stub/out")" != *stale* ]] \
    || { (( fails++ )); print -r -- "FAIL stale record: $(<"$stub/out")"; }
rm -rf -- "$stub/rec"
check "tmux's exit code passes through, after the line" 3 \
    "tmux new-session*" -- TERM_PROGRAM=Apple_Terminal STUB_RC=3 STUB_RECORD=$'sid-3\t/z' -- --run-claude
[[ "$(<"$stub/out")" == *"· sid-3 · /z"* ]] || { (( fails++ )); print -r -- "FAIL line after a tmux error: $(<"$stub/out")"; }

# --attach NAME: CC Sessions' attach and restore tabs.
: > "$stub/alive-work-1"
check "--attach attaches in control mode and prints the ended session" 0 \
    "tmux has-session -t =work-1" "tmux -CC attach-session -t =work-1" -- \
    TERM_PROGRAM=iTerm.app STUB_RECORD=$'sid-4\t'"$stub/y" -- --attach work-1
[[ "$(<"$stub/out")" == *"closed work-1 · sid-4 · ~/y"* ]] || { (( fails++ )); print -r -- "FAIL attach line: $(<"$stub/out")"; }
check "--attach to a missing session exits 1 without attaching" 1 -- TERM_PROGRAM=iTerm.app -- --attach gone-1
[[ "$(<"$calls")" != *attach-session* ]] || { (( fails++ )); print "FAIL attached to a missing session"; }
check "--attach with no name exits 2" 2 -- -- --attach
rm -rf -- "$stub/rec" "$stub"/alive-*(N)

# -a NAME: the accounts file maps a name to a config folder.
mkdir -p "$stub/xdg/agents-shared" "$stub/cfg-alt" "$stub/.claude"
print -r -- $'# name folder\nhome ~/.claude\nalt ~/cfg-alt  # the second account' > "$stub/xdg/agents-shared/claude-accounts"
check "-a NAME hands that account's folder to the tmux session" 0 \
    "tmux new-session * -e CLAUDE_CONFIG_DIR=${stub:A}/cfg-alt claude" -- \
    TERM_PROGRAM=Apple_Terminal XDG_CONFIG_HOME="$stub/xdg" -- -a alt --run-claude
check "an account at ~/.claude launches with CLAUDE_CONFIG_DIR unset" 0 \
    "tmux new-session * claude" -- \
    TERM_PROGRAM=Apple_Terminal XDG_CONFIG_HOME="$stub/xdg" -- --account home --run-claude
[[ "$(<"$calls")" != *CLAUDE_CONFIG_DIR* ]] || { (( fails++ )); print "FAIL ~/.claude account set CLAUDE_CONFIG_DIR"; }
check "an unknown account exits 2" 2 -- XDG_CONFIG_HOME="$stub/xdg" -- -a nope --run-claude
check "no accounts file exits 2" 2 -- XDG_CONFIG_HOME="$stub/none" -- -a alt --run-claude

# clo f: the account's line in the fast-folders file is where it launches.
mkdir -p "$stub/fastdir"
print -r -- $'alt\t~/fastdir\nhome\t~/nowhere-at-all' > "$stub/xdg/agents-shared/clo-fast-folders"
check "clo f launches in the account's fast folder" 0 \
    "tmux new-session * -c */fastdir *" -- \
    TERM_PROGRAM=Apple_Terminal XDG_CONFIG_HOME="$stub/xdg" -- -a alt f
check "a missing fast folder falls through to the no-terminal refusal, not a crash" 1 -- \
    TERM_PROGRAM=Apple_Terminal XDG_CONFIG_HOME="$stub/xdg" DEV_ROOT="$stub/no-dev-root" -- -a home f

# Without -a, the folder you stand in picks the account (roots after the fast folder).
mkdir -p "$stub/roots/one/deep" "$stub/roots/two"
print -r -- $'alt\t~/fastdir\t~/roots/one\nhome\t~/fastdir\t~/roots/two ~/roots/one/deep' > "$stub/xdg/agents-shared/clo-fast-folders"
check_cwd="$stub/roots/one/sub"; mkdir -p "$check_cwd"
check "clo f under an account's root uses that account" 0 \
    "tmux new-session * -e CLAUDE_CONFIG_DIR=${stub:A}/cfg-alt claude *" -- \
    TERM_PROGRAM=Apple_Terminal XDG_CONFIG_HOME="$stub/xdg" -- f
check_cwd="$stub/roots/one/deep"
check "the longest matching root wins" 0 "tmux new-session *" -- \
    TERM_PROGRAM=Apple_Terminal XDG_CONFIG_HOME="$stub/xdg" -- f
[[ "$(<"$calls")" != *CLAUDE_CONFIG_DIR* ]] || { (( fails++ )); print "FAIL longest root did not pick the default-folder account"; }
check "-a beats the folder" 0 \
    "tmux new-session * -e CLAUDE_CONFIG_DIR=${stub:A}/cfg-alt claude *" -- \
    TERM_PROGRAM=Apple_Terminal XDG_CONFIG_HOME="$stub/xdg" -- -a alt f
unset check_cwd

# Extra roots: folders outside DEV_ROOT, listed in the extra-roots file. A stand-in
# local-repos-list reports each root's immediate subfolders.
cat > "$stub/local-repos-list" <<'EOF'
#!/bin/zsh
root=""; while (( $# )); do [[ $1 == --root ]] && { root=$2; shift; }; shift; done
print -n '['; sep=""
for d in "$root"/*(N/); do print -n "$sep{\"name\":\"${d:t}\",\"path\":\"$d\",\"tags\":[\"my\"]}"; sep=","; done
print ']'
EOF
chmod +x "$stub/local-repos-list"
mkdir -p "$stub/dev/personal/notes" "$stub/dev/work/some-repo" "$stub/xdg2/agents-shared"
print -r -- $'# extra roots\n  ~/dev/work  \n~/dev/missing\n~/dev/personal' > "$stub/xdg2/agents-shared/clo-extra-roots"
roots_env=(HOME="$stub" PATH="$stub:$PATH" DEV_ROOT="$stub/dev/personal" XDG_CONFIG_HOME="$stub/xdg2")
names="$(cd "$stub" && env "${roots_env[@]}" "$clo" --repo-names 2>/dev/null)"
(( n++ ))
[[ "$names" == $'notes\nsome-repo\nwork\nwork/some-repo' ]] \
    || { (( fails++ )); print -r -- "FAIL --repo-names with an extra root: ${names//$'\n'/ | }"; }
json="$(cd "$stub" && env "${roots_env[@]}" "$clo" --folders-json 2>/dev/null)"
(( n++ ))
[[ "$(jq -r '[.[] | .name + "=" + (.tags | join(","))] | join(" ")' <<< "$json")" \
    == "personal=dev-root notes=my work=root work/some-repo=my" ]] \
    || { (( fails++ )); print -r -- "FAIL --folders-json with an extra root: $json"; }
err="$(cd "$stub" && env "${roots_env[@]}" "$clo" --folders-json 2>&1 >/dev/null)"
(( n++ ))
[[ "$err" == *"dev/missing, which is not a folder"* ]] \
    || { (( fails++ )); print -r -- "FAIL a missing extra root is not reported: ${err:-nothing}"; }
check "clo NAME finds a folder under an extra root" 0 \
    "tmux new-session * -c ${stub:A}/dev/work/some-repo * claude --model sonnet --effort medium" -- \
    TERM_PROGRAM=Apple_Terminal "${roots_env[@]}" -- some-repo 2
check "an unknown NAME off a terminal still exits 2" 2 -- "${roots_env[@]}" -- no-such-folder 2

print "clo launch tests: $n cases, $fails failed"
(( fails == 0 ))
