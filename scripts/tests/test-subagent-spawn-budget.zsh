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

print -r -- "* 08" > "$local_dir/subagent-spawn-budget"
check "leading zero reads as base 10" "8" "$("$script" "$tmp/work")"
print -r -- "* 010" > "$local_dir/subagent-spawn-budget"
check "010 is ten, not octal eight" "10" "$("$script" "$tmp/work")"
print -r -- "* 000" > "$local_dir/subagent-spawn-budget"
check "all zeros is 0" "0" "$("$script" "$tmp/work")"
print -r -- "* 999999999" > "$local_dir/subagent-spawn-budget"
check "nine digits is taken" "999999999" "$("$script" "$tmp/work")"
printf '* 12\r\n' > "$local_dir/subagent-spawn-budget"
check "a CRLF line reads" "12" "$("$script" "$tmp/work")"

print -r -- "* 1000000000" > "$local_dir/subagent-spawn-budget"
"$script" "$tmp/work" 2>/dev/null; check "ten digits exits 2" "2" "$?"
print -r -- "* lots" > "$local_dir/subagent-spawn-budget"
"$script" "$tmp/work" 2>/dev/null; check "non-number exits 2" "2" "$?"
print -r -- "* 3 4" > "$local_dir/subagent-spawn-budget"
"$script" "$tmp/work" 2>/dev/null; check "three columns exits 2" "2" "$?"
print -r -- "*" > "$local_dir/subagent-spawn-budget"
"$script" "$tmp/work" 2>/dev/null; check "missing value exits 2" "2" "$?"

# --list and --set: the Guards menu in CC Sessions reads and writes only through these.
T=$'\t'
budget="$local_dir/subagent-spawn-budget"
rm -f -- "$budget"
print -r -- "work $tmp/work
personal $tmp/personal" > "$local_dir/claude-accounts"
check "list with no file is all default" "*${T}8${T}default
work${T}8${T}default
personal${T}8${T}default" "$("$script" --list)"

"$script" --set personal 07
check "set makes the file with its header" "# account   budget (shape: agents-shared/scripts/subagent-spawn-budget.example)
personal     7" "$(<"$budget")"
"$script" --set "*" 20
check "list shows own, all and where each comes from" "*${T}20${T}own
work${T}20${T}all
personal${T}7${T}own" "$("$script" --list)"
check "reader agrees with the list" "7" "$("$script" "$tmp/personal")"

print -r -- "# kept comment
personal 3   # first
work     5
personal 4" > "$budget"
"$script" --set personal UNLIMITED
check "set replaces every line for the name, where the first stood" "# kept comment
personal     unlimited
work     5" "$(<"$budget")"
"$script" --set work ""
check "empty value removes the line" "# kept comment
personal     unlimited" "$(<"$budget")"

print -r -- "* lots
work 5" > "$budget"
"$script" --list >/dev/null 2>&1; check "list exits 2 on a bad line" "2" "$?"
check "list names the bad line" "subagent-spawn-budget: $budget line 1 needs a whole number or unlimited: * lots" \
    "$("$script" --list 2>&1 >/dev/null)"
"$script" --set "*" 30
check "set replaces a bad line for its own name" "*            30
work 5" "$(<"$budget")"

"$script" --set work 1000000000 2>/dev/null; check "set refuses ten digits" "2" "$?"
"$script" --set work lots 2>/dev/null; check "set refuses a non-number" "2" "$?"
"$script" --set "two words" 5 2>/dev/null; check "set refuses a name with a space" "2" "$?"
check "refused sets leave the file" "*            30
work 5" "$(<"$budget")"

chmod 000 "$budget"
"$script" --set work 9 2>/dev/null; check "set refuses a file it cannot read" "2" "$?"
chmod 600 "$budget"
check "an unreadable file is left as it was" "*            30
work 5" "$(<"$budget")"

exit $fail
