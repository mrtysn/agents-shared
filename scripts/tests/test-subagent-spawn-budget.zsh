#!/bin/zsh
# Tests for scripts/subagent-spawn-budget: no file, *, account line wins, account by config folder,
# ~ in claude-accounts, unlimited, bad lines.
emulate -L zsh
script="${0:A:h:h}/subagent-spawn-budget"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
export XDG_CONFIG_HOME="$tmp/xdg"
local_dir="$XDG_CONFIG_HOME/agents-shared"
mkdir -p "$local_dir" "$tmp/work" "$tmp/personal" "$tmp/stray"
fail=0

check() {  # check NAME EXPECTED ACTUAL
    if [[ "$2" == "$3" ]]; then print "ok   $1"; else print "FAIL $1: expected '$2', got '$3'"; fail=1; fi
}

check "no file prints nothing" "" "$("$script" "$tmp/work")"

print -r -- "work $tmp/work
personal ~/personal  # tilde" > "$local_dir/claude-accounts"
cat > "$local_dir/subagent-spawn-budget" <<EOF
# comment
*          20
personal   unlimited   # trailing comment
EOF
check "star covers an account without a line" "20" "$("$script" "$tmp/work")"
check "account line wins over star" "unlimited" "$(HOME="$tmp" "$script" "$tmp/personal")"
check "folder in no account gets star" "20" "$("$script" "$tmp/stray")"
check "defaults to CLAUDE_CONFIG_DIR" "unlimited" "$(HOME="$tmp" CLAUDE_CONFIG_DIR="$tmp/personal" "$script")"

print -r -- "personal 42" > "$local_dir/subagent-spawn-budget"
check "no star and no match prints nothing" "" "$("$script" "$tmp/work")"

rm -f "$local_dir/claude-accounts"
print -r -- "* 42" > "$local_dir/subagent-spawn-budget"
check "no accounts file still reads star" "42" "$("$script" "$tmp/work")"

print -r -- "* lots" > "$local_dir/subagent-spawn-budget"
"$script" "$tmp/work" 2>/dev/null; check "non-number exits 2" "2" "$?"
print -r -- "* 3 4" > "$local_dir/subagent-spawn-budget"
"$script" "$tmp/work" 2>/dev/null; check "three columns exits 2" "2" "$?"
print -r -- "*" > "$local_dir/subagent-spawn-budget"
"$script" "$tmp/work" 2>/dev/null; check "missing value exits 2" "2" "$?"

exit $fail
