#!/bin/bash
# DESC: Test block-tree-discard.sh's branch-switch rule against real fixture repos
#
# The switch rule reads the repo (local branches, git status), so these cases
# need a real tree; the static case file cannot express them. Bash, not zsh,
# to match the hook under test.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../block-tree-discard.sh"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

make_repo() {
    local dir=$1
    git init -q -b main "$dir"
    git -C "$dir" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
    printf 'a\n' > "$dir/file.txt"
    git -C "$dir" add file.txt
    git -C "$dir" -c user.name=t -c user.email=t@t commit -q -m file
    git -C "$dir" branch other
}

CLEAN="$TMP/clean"; make_repo "$CLEAN"
DIRTY="$TMP/dirty"; make_repo "$DIRTY"; printf 'b\n' >> "$DIRTY/file.txt"
UNTRACKED="$TMP/untracked"; make_repo "$UNTRACKED"; printf 'x\n' > "$UNTRACKED/new.txt"
ELSEWHERE="$TMP/elsewhere"; mkdir "$ELSEWHERE"

total=0
failed=0

# check <want: pass|block> <cwd> <command>
check() {
    local verdict=$1 cwd=$2 command=$3 want got=0 reason payload
    case "$verdict" in pass) want=0 ;; block) want=2 ;; esac
    payload=$(jq -n --arg c "$command" --arg cwd "$cwd" \
        '{tool_name: "Bash", cwd: $cwd, tool_input: {command: $c}}')
    reason=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?
    total=$((total + 1))
    if [ "$got" != "$want" ]; then
        failed=$((failed + 1))
        printf 'FAIL  want %s, got %s: [%s] %s\n      %s\n' "$want" "$got" "${cwd#$TMP/}" "$command" "$(printf '%s' "$reason" | head -1)"
    fi
}

# Clean tree, existing local branch, no flags: allowed.
check pass  "$CLEAN" "git switch other"
check pass  "$CLEAN" "git checkout other"
check pass  "$ELSEWHERE" "cd $CLEAN && git switch other"

# Flags that force, merge or create.
check block "$CLEAN" "git switch -f other"
check block "$CLEAN" "git switch --discard-changes other"
check block "$CLEAN" "git switch -m other"
check block "$CLEAN" "git switch -c newbranch"
check block "$CLEAN" "git checkout -f other"
check block "$CLEAN" "git checkout -b newbranch"

# Not a local branch, or nothing named.
check block "$CLEAN" "git switch nosuch"
check block "$CLEAN" "git switch"
check block "$CLEAN" "git switch -"
check block "$CLEAN" "git checkout file.txt"
check block "$CLEAN" "git checkout ."

# A tree the hook cannot see.
check block "$CLEAN" "git -C $DIRTY switch other"
check block "$ELSEWHERE" "cd \$REPO && git switch other"
check block "$ELSEWHERE" "git switch other"

# Uncommitted or untracked work present.
check block "$DIRTY" "git switch other"
check block "$DIRTY" "git checkout other"
check block "$ELSEWHERE" "cd $DIRTY && git switch other"
check block "$UNTRACKED" "git switch other"

# The single-file revert still works.
check pass  "$DIRTY" "git checkout -- file.txt"

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = "0" ]
