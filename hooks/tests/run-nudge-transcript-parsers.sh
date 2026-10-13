#!/bin/bash
# DESC: Run the nudge-transcript-parsers PreToolUse hook against its case file
#
# Bash, not zsh, to match the hook under test and to keep working on Linux
# machines that sync agents-shared without /bin/zsh.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../nudge-transcript-parsers.sh"
CASES="$HERE/nudge-transcript-parsers-cases.tsv"

usage() {
    cat <<'USAGE'
usage: run-nudge-transcript-parsers.sh [-v] [case-file]

Feeds each case to the hook as a PreToolUse payload, each in a session of its
own, and compares its verdict (pass = no output, nudge = additionalContext and
no permission decision) with the expected one. Then checks that a second
matching call in the same session passes, and that a new session is nudged again.

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

CLAUDE_CONFIG_DIR=$(mktemp -d)
export CLAUDE_CONFIG_DIR
trap 'rm -rf "$CLAUDE_CONFIG_DIR"' EXIT

payload() { # session tool text
    if [ "$2" = Write ]; then
        jq -n --arg s "$1" --arg t "$3" '{session_id: $s, tool_name: "Write", tool_input: {file_path: "/x/f", content: $t}}'
    elif [ "$2" = Bash ]; then
        jq -n --arg s "$1" --arg t "$3" '{session_id: $s, tool_name: "Bash", tool_input: {command: $t}}'
    else
        jq -n --arg s "$1" --arg n "$2" --arg t "$3" '{session_id: $s, tool_name: $n, tool_input: {new_string: $t}}'
    fi
}

verdict() { # hook output -> pass | nudge | BAD
    if [ -z "$1" ]; then echo pass; return; fi
    if printf '%s' "$1" | jq -e '.hookSpecificOutput.additionalContext and (.hookSpecificOutput.permissionDecision | not)' >/dev/null 2>&1; then
        echo nudge
    else
        echo BAD
    fi
}

fail=0
total=0
while IFS=$'\t' read -r want tool text; do
    case "$want" in ''|\#*) continue ;; esac
    total=$((total + 1))
    out=$(payload "case-$total" "$tool" "$(printf '%b' "$text")" | "$HOOK")
    got=$(verdict "$out")
    if [ "$got" != "$want" ]; then
        fail=$((fail + 1))
        printf 'FAIL  want %s got %s  [%s] %s\n' "$want" "$got" "$tool" "$text"
    elif [ "$VERBOSE" = 1 ]; then
        printf 'ok    %s  [%s] %s\n' "$got" "$tool" "$text"
    fi
done < "$CASES"

# once per session: a repeat in the same session passes, another session is nudged
RE='python3 -c "import json" ~/.claude/projects'
first=$(verdict "$(payload once Bash "$RE" | "$HOOK")")
again=$(verdict "$(payload once Bash "$RE" | "$HOOK")")
other=$(verdict "$(payload other Bash "$RE" | "$HOOK")")
total=$((total + 3))
[ "$first" = nudge ] || { fail=$((fail + 1)); echo "FAIL  first call in a session: got $first"; }
[ "$again" = pass ] || { fail=$((fail + 1)); echo "FAIL  repeat in the same session: got $again"; }
[ "$other" = nudge ] || { fail=$((fail + 1)); echo "FAIL  a different session: got $other"; }

if [ "$fail" -ne 0 ]; then
    echo "$fail of $total cases failed"
    exit 1
fi
echo "all $total cases passed"
