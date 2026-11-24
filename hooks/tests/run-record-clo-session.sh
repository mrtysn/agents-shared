#!/bin/zsh
# Cases for hooks/record-clo-session.zsh, against a stand-in tmux.
set -u
here="${0:A:h}"
hook="$here/../record-clo-session.zsh"
stub="$(mktemp -d "${TMPDIR:-/tmp}/record-clo-session.XXXXXX")"
trap 'rm -rf -- "$stub"' EXIT
mkdir -p "$stub/bin"
cat > "$stub/bin/tmux" <<'EOF'
#!/bin/zsh
[[ $1 == display ]] || exit 1
# Real tmux prints nothing for "-t %1" passed as one word.
for a in "$@"; do [[ $a == "-t "* ]] && exit 0; done
[[ -n "${STUB_NAME:-}" ]] || exit 1
print -r -- "$STUB_NAME"
EOF
chmod +x "$stub/bin/tmux"

fails=0 n=0
run() {  # run JSON ENV...
    local json="$1"; shift
    print -r -- "$json" | env -u TMUX -u TMUX_PANE PATH="$stub/bin:$PATH" CLO_SESSION_RECORDS="$stub/rec" "$@" "$hook"
}
expect() {  # expect NAME FILE WANT
    (( n++ ))
    local got=""; [[ -r "$2" ]] && got="$(<"$2")"
    [[ "$got" == "$3" ]] || { (( fails++ )); print -r -- "FAIL $1: got '${got}', want '$3'"; }
}

run '{"session_id":"abc","cwd":"/work/x"}' TMUX=/tmp/s,1,0 TMUX_PANE=%1 STUB_NAME=notebook-7f
expect "start writes id and folder under the tmux name" "$stub/rec/notebook-7f" $'abc\t/work/x'

run '{"session_id":"def","cwd":"/work/x"}' TMUX=/tmp/s,1,0 STUB_NAME=notebook-7f
expect "a later event (a /clear) replaces the id" "$stub/rec/notebook-7f" $'def\t/work/x'

(cd "${stub:A}" && run '{"session_id":"ghi"}' TMUX=/tmp/s,1,0 STUB_NAME=no-cwd)
expect "no cwd in the payload takes the hook's folder" "$stub/rec/no-cwd" $'ghi\t'"${stub:A}"

run '{"session_id":"jkl","cwd":"/w"}' TMUX=/tmp/s,1,0 STUB_NAME=a/b
expect "a slash in the tmux name stays inside the folder" "$stub/rec/a_b" $'jkl\t/w'

run '{"session_id":"mno","cwd":"/w"}' STUB_NAME=outside
expect "outside tmux nothing is written" "$stub/rec/outside" ""

run '{"cwd":"/w"}' TMUX=/tmp/s,1,0 STUB_NAME=no-id
expect "no session id writes nothing" "$stub/rec/no-id" ""

out="$(run 'not json' TMUX=/tmp/s,1,0 STUB_NAME=bad 2>&1)"; rc=$?
(( n++ ))
[[ $rc == 0 && -z "$out" ]] || { (( fails++ )); print -r -- "FAIL bad input: rc=$rc out='$out'"; }

print "record-clo-session: $n cases, $fails failed"
(( fails == 0 ))
