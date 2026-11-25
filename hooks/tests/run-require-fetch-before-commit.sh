#!/bin/bash
# DESC: Run the require-fetch-before-commit PreToolUse hook against its case file
#
# Each case builds a throwaway remote and clone, so no real repository or network is touched.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../require-fetch-before-commit.sh"
CASES="$HERE/require-fetch-before-commit-cases.tsv"

WORK=$(mktemp -d)
export XDG_CACHE_HOME="$WORK/cache"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
trap '[ -n "${WORK:-}" ] && rm -rf "$WORK"' EXIT

VERBOSE=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) echo "usage: run-require-fetch-before-commit.sh [-v] [case-file]"; exit 0 ;;
        *) CASES=$1; shift ;;
    esac
done

# build SCENARIO DIR: leaves DIR as the folder the commit runs in
build() {
    local scenario=$1 dir=$2
    if [ "$scenario" = notgit ]; then mkdir -p "$dir"; return; fi
    git init -q --bare "$dir.remote"
    git init -q -b main "$dir"
    git -C "$dir" remote add origin "$dir.remote"
    echo 1 > "$dir/a.txt"; git -C "$dir" add a.txt; git -C "$dir" commit -q -m first
    [ "$scenario" = no-upstream ] || git -C "$dir" push -q -u origin main
    case "$scenario" in
        behind|behind-ahead|offline|detached)
            git clone -q "$dir.remote" "$dir.other"
            echo 2 > "$dir.other/b.txt"; git -C "$dir.other" add b.txt; git -C "$dir.other" commit -q -m "other session"
            git -C "$dir.other" push -q origin main ;;
    esac
    if [ "$scenario" = behind-ahead ]; then
        echo 3 > "$dir/c.txt"; git -C "$dir" add c.txt; git -C "$dir" commit -q -m mine
    fi
    if [ "$scenario" = offline ]; then git -C "$dir" remote set-url origin "$dir.nowhere"; fi
    if [ "$scenario" = detached ]; then git -C "$dir" update-ref --no-deref HEAD "$(git -C "$dir" rev-parse HEAD)"; fi
    return 0
}

total=0
failed=0
n=0
while IFS=$'\t' read -r verdict scenario command; do
    case "${verdict-}" in ''|'#'*) continue ;; esac
    n=$((n + 1))
    dir="$WORK/case$n/repo"
    mkdir -p "$WORK/case$n"
    # A scenario ending in /elsewhere runs with the session folder outside the repo, as a
    # session started in another repo that cds into this one does.
    cwd=$dir
    case "$scenario" in */elsewhere) scenario=${scenario%/elsewhere}; cwd="$WORK/case$n" ;; esac
    build "$scenario" "$dir"
    cmd=${command//@REPO@/$dir}
    payload=$(jq -cn --arg c "$cmd" --arg cwd "$cwd" --arg s "case$n" '{tool_name: "Bash", session_id: $s, cwd: $cwd, tool_input: {command: $c}}')
    first=0; reason=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || first=$?
    second=0; printf '%s' "$payload" | "$HOOK" >/dev/null 2>&1 || second=$?
    case "$verdict" in
        pass) want_first=0 ;;
        block) want_first=2 ;;
        *) echo "unknown verdict '$verdict'" >&2; exit 1 ;;
    esac
    total=$((total + 1))
    extra_ok=1
    # The advice names the remote commit and the pull that applies to the branch.
    if [ "$verdict" = block ]; then
        case "$scenario" in
            behind-ahead) printf '%s' "$reason" | grep -q 'pull --rebase' || extra_ok=0 ;;
            behind) printf '%s' "$reason" | grep -q 'pull --ff-only' || extra_ok=0 ;;
        esac
        printf '%s' "$reason" | grep -q 'other session' || extra_ok=0
    fi
    if [ "$first" = "$want_first" ] && [ "$second" = 0 ] && [ "$extra_ok" = 1 ]; then
        if [ "$VERBOSE" = 1 ]; then printf 'ok    %-6s %-12s %s\n' "$verdict" "$scenario" "$command"; fi
    else
        failed=$((failed + 1))
        printf 'FAIL  want %s then 0, got %s then %s (advice ok=%s): %s %s\n' "$want_first" "$first" "$second" "$extra_ok" "$scenario" "$command"
    fi
done < "$CASES"

# A fetch past the time limit fails open: a remote that hangs costs the limit and no more.
total=$((total + 1))
dir="$WORK/slow/repo"; mkdir -p "$WORK/slow"; build behind "$dir"
printf '#!/bin/sh\nsleep 30\n' > "$WORK/slow/ssh"; chmod +x "$WORK/slow/ssh"
git -C "$dir" remote set-url origin "ssh://host/nowhere"
payload=$(jq -cn --arg cwd "$dir" '{tool_name: "Bash", session_id: "slow", cwd: $cwd, tool_input: {command: "git commit -m x"}}')
start=$SECONDS; got=0
printf '%s' "$payload" | GIT_SSH_COMMAND="$WORK/slow/ssh" FETCH_BEFORE_COMMIT_LIMIT=1 "$HOOK" >/dev/null 2>&1 || got=$?
if [ "$got" = 0 ] && [ $((SECONDS - start)) -le 4 ]; then
    if [ "$VERBOSE" = 1 ]; then echo "ok    a hanging remote passes within the limit"; fi
else
    failed=$((failed + 1)); echo "FAIL  hanging remote: exit $got after $((SECONDS - start))s"
fi

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = 0 ]
