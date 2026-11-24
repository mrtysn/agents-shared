#!/bin/zsh
# Tests for scripts/new-repo-gh-account: no file, *, longest folder wins, ~ expansion, bad line.
emulate -L zsh
script="${0:A:h:h}/new-repo-gh-account"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/dev/work/repo" "$tmp/dev/personal/repo" "$tmp/other"
export NEW_REPO_GH_ACCOUNT_FILE="$tmp/config"
fail=0

check() {  # check NAME EXPECTED ACTUAL
    if [[ "$2" == "$3" ]]; then print "ok   $1"; else print "FAIL $1: expected '$2', got '$3'"; fail=1; fi
}

check "no file prints nothing" "" "$("$script" "$tmp/other")"

cat > "$NEW_REPO_GH_ACCOUNT_FILE" <<EOF
# comment
*                 home-handle
$tmp/dev          dev-handle   # trailing comment
$tmp/dev/work     work-handle
EOF
check "star covers other folders" "home-handle" "$("$script" "$tmp/other")"
check "folder line covers subfolders" "dev-handle" "$("$script" "$tmp/dev/personal/repo")"
check "longest folder wins" "work-handle" "$("$script" "$tmp/dev/work/repo")"
check "exact folder matches" "work-handle" "$("$script" "$tmp/dev/work")"
check "prefix of a name is not a match" "dev-handle" "$(mkdir -p "$tmp/dev/workshop"; "$script" "$tmp/dev/workshop")"
check "defaults to current folder" "work-handle" "$(cd "$tmp/dev/work/repo" && "$script")"

print -r -- "$tmp/dev/personal  personal-handle" > "$NEW_REPO_GH_ACCOUNT_FILE"
check "no star and no match prints nothing" "" "$("$script" "$tmp/other")"

print -r -- '~/dev  tilde-handle' > "$NEW_REPO_GH_ACCOUNT_FILE"
check "tilde expands to HOME" "tilde-handle" "$(HOME="$tmp" "$script" "$tmp/dev/work")"

print -r -- "* one two" > "$NEW_REPO_GH_ACCOUNT_FILE"
"$script" "$tmp/other" 2>/dev/null; check "three columns exits 2" "2" "$?"

exit $fail
