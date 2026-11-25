#!/bin/zsh
# Runs scripts/check-hooks-wired.py against a made-up README, hooks folder and settings.json,
# and checks what it reports for each kind of gap.
set -u
here="${0:A:h}"
check="$here/../check-hooks-wired.py"
dir="$(mktemp -d "${TMPDIR:-/tmp}/hooks-wired-test.XXXXXX")"
trap 'rm -rf -- "$dir"' EXIT
fail=0 n=0

mkdir -p "$dir/hooks"
for h in guard.sh start.zsh probe.sh personal.sh; do : > "$dir/hooks/$h"; done
cat > "$dir/README.md" <<'EOF'
| Hook | Event | What it does |
|---|---|---|
| `hooks/guard.sh` | PreToolUse (`Bash\|Edit`) | Refuses something |
| `hooks/start.zsh` | SessionStart, SessionEnd | Records something |
| `hooks/probe.sh` | any | Probe |
| `hooks/personal.sh` (forwards to `hooks/personal/`; personal profile only) | PostToolUse (`Edit`) | Notes something |
EOF

# settings JSON for the given (event, command) pairs
settings() {
    python3 -c '
import json, sys
a = sys.argv[1:]; out = {"hooks": {}}
for ev, cmd in zip(a[::2], a[1::2]):
    out["hooks"].setdefault(ev, []).append({"hooks": [{"type": "command", "command": cmd}]})
print(json.dumps(out))' "$@" > "$dir/settings.json"
}
own() { print -r -- "f=x; [ -x \"\$AGENTS_SHARED_DIR/hooks/$1\" ] && exec \"\$AGENTS_SHARED_DIR/hooks/$1\"; exit 0" }
link() { print -r -- "\${CLAUDE_CONFIG_DIR:-\$HOME/.claude}/hooks/$1" }

# expect NAME WANT_EXIT PROFILE [GREP...]: every GREP must be in the output, and a "!GREP" must not
expect() {
    local name=$1 want=$2 profile=$3; shift 3
    n=$((n + 1))
    local out rc
    out="$(python3 "$check" --settings "$dir/settings.json" --readme "$dir/README.md" \
        --hooks-dir "$dir/hooks" --profile "$profile" 2>&1)"; rc=$?
    local ok=1 g
    [[ $rc == $want ]] || ok=0
    for g in "$@"; do
        if [[ $g == '!'* ]]; then [[ $out == *"${g#!}"* ]] && ok=0
        else [[ $out == *"$g"* ]] || ok=0; fi
    done
    if (( ok )); then print -r -- "ok   $name"
    else print -r -- "FAIL $name (exit $rc, want $want)"; print -r -- "$out" | sed 's/^/     /'; fail=$((fail + 1)); fi
}

settings PreToolUse "$(own guard.sh)" SessionStart "$(own start.zsh)" SessionEnd "$(link start.zsh)"
expect "every documented event wired, by repo path or by link" 0 work

settings PreToolUse "$(own guard.sh)" SessionStart "$(own start.zsh)"
expect "a hook wired on one of its two events" 1 work "not wired: hooks/start.zsh under SessionEnd" '!under SessionStart' "built from"

settings SessionStart "$(own start.zsh)" SessionEnd "$(own start.zsh)" PostToolUse "$(own guard.sh)"
expect "a hook wired under the wrong event" 1 work "not wired: hooks/guard.sh under PreToolUse"

settings PreToolUse "$(own guard.sh)" SessionStart "$(own start.zsh)" SessionEnd "$(own start.zsh)"
expect "a personal-only hook is not required on the work profile" 0 work
expect "a personal-only hook is required on the personal profile" 1 personal "not wired: hooks/personal.sh under PostToolUse"

settings PreToolUse "$(own guard.sh)" SessionStart "$(own start.zsh)" SessionEnd "$(own start.zsh)" Stop "$(own gone.sh)" Stop "$(link elsewhere.zsh)"
expect "settings run a repo hook that no longer exists, and a foreign link is ignored" 1 work \
    "missing script: Stop runs hooks/gone.sh" '!elsewhere.zsh'

print -r -- '{not json' > "$dir/settings.json"
expect "an unreadable settings file is a read error" 2 work "check-hooks-wired:"

print -r -- "check-hooks-wired: $n cases, $fail failed"
(( fail == 0 ))
