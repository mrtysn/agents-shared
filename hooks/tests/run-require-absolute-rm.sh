#!/bin/bash
# DESC: Run the require-absolute-rm PreToolUse hook against its case file
#
# Bash, not zsh, to match the hook under test and to keep working on Linux
# machines that sync agents-shared without /bin/zsh.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../require-absolute-rm.sh"
CASES="$HERE/require-absolute-rm-cases.tsv"
CWD_FIXTURE="/Users/example/project"

usage() {
    cat <<'USAGE'
usage: run-require-absolute-rm.sh [-v] [case-file]

Feeds each case to the hook as a PreToolUse payload and compares the exit
status against the expected verdict (pass = 0, block = 2).

  -v   print every case, not just failures
USAGE
}

VERBOSE=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) CASES=$1; shift ;;
    esac
done

for f in "$HOOK" "$CASES"; do
    if [ ! -r "$f" ]; then
        echo "missing: $f" >&2
        exit 1
    fi
done

total=0
failed=0

while IFS=$'\t' read -r verdict command; do
    case "${verdict-}" in
        ''|'#'*) continue ;;
    esac
    if [ -z "${command-}" ]; then
        continue
    fi

    case "$verdict" in
        pass) want=0 ;;
        block) want=2 ;;
        *) echo "unknown verdict '$verdict'" >&2; exit 1 ;;
    esac

    decoded=$(printf '%b' "$command")
    payload=$(jq -Rn --arg c "$decoded" --arg cwd "$CWD_FIXTURE" \
        '{tool_name: "Bash", cwd: $cwd, tool_input: {command: $c}}')

    got=0
    reason=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?

    total=$((total + 1))
    oneline=$(printf '%s' "$command" | tr '\n' ' ')

    if [ "$got" = "$want" ]; then
        if [ "$VERBOSE" = "1" ]; then
            printf 'ok    %-6s %s\n' "$verdict" "$oneline"
        fi
    else
        failed=$((failed + 1))
        printf 'FAIL  want %s, got %s: %s\n' "$want" "$got" "$oneline"
        printf '      %s\n' "$(printf '%s' "$reason" | head -1)"
    fi
done < "$CASES"

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = "0" ]
