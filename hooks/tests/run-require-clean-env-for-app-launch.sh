#!/bin/bash
# DESC: Run the require-clean-env-for-app-launch PreToolUse hook against its case file
#
# Bash, not zsh, to match the hook under test and to keep working on Linux
# machines that sync agents-shared without /bin/zsh.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../require-clean-env-for-app-launch.sh"
CASES="$HERE/require-clean-env-for-app-launch-cases.tsv"
CWD_FIXTURE="/Users/example/project"

usage() {
    cat <<'USAGE'
usage: run-require-clean-env-for-app-launch.sh [-v] [case-file]

Feeds each case to the hook as a PreToolUse payload (Bash, or Write, Edit
and a Bash run of a script, by the case's second column) and compares the exit
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

SCRIPTS=$(mktemp -d)
trap 'rm -rf "$SCRIPTS"' EXIT

while IFS=$'\t' read -r verdict command text; do
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

    body=$(printf '%b' "${text-}")
    case "$command" in
        Write:*)
            payload=$(jq -n --arg f "${command#Write:}" --arg t "$body" --arg cwd "$CWD_FIXTURE" \
                '{tool_name: "Write", cwd: $cwd, tool_input: {file_path: $f, content: $t}}') ;;
        Edit:*)
            payload=$(jq -n --arg f "${command#Edit:}" --arg t "$body" --arg cwd "$CWD_FIXTURE" \
                '{tool_name: "Edit", cwd: $cwd, tool_input: {file_path: $f, old_string: "x", new_string: $t}}') ;;
        Run:*)
            # The script text goes into a file named by the case; {} in the command is its folder.
            spec=${command#Run:}
            name=${spec%%|*}
            printf '%s\n' "$body" > "$SCRIPTS/$name"
            decoded=$(printf '%s' "${spec#*|}" | sed "s|{}|$SCRIPTS|g")
            payload=$(jq -n --arg c "$decoded" --arg cwd "$SCRIPTS" \
                '{tool_name: "Bash", cwd: $cwd, tool_input: {command: $c}}') ;;
        *)
            decoded=$(printf '%b' "$command")
            payload=$(jq -Rn --arg c "$decoded" --arg cwd "$CWD_FIXTURE" \
                '{tool_name: "Bash", cwd: $cwd, tool_input: {command: $c}}') ;;
    esac

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
