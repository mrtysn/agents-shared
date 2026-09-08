#!/bin/bash
# DESC: Run the memory-lint PreToolUse hook against its case file
#
# Bash, not zsh, to match the hook under test and to keep working on Linux
# machines that sync agents-shared without /bin/zsh.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../memory-lint.sh"
CASES="$HERE/memory-lint-cases.tsv"

usage() {
    cat <<'USAGE'
usage: run-memory-lint.sh [-v] [case-file]

Builds a throwaway Claude config dir with a fixture memory bucket and rules
dir, feeds each case to the hook as a PreToolUse payload, and compares the
exit status against the expected verdict (pass = 0, block = 2).

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
    [ -r "$f" ] || { echo "missing: $f" >&2; exit 1; }
done

CFG=$(mktemp -d)
trap 'rm -rf "$CFG"' EXIT
MEM="$CFG/projects/-Users-example-project/memory"
mkdir -p "$MEM" "$CFG/rules" "$CFG/elsewhere"
: > "$CFG/rules/no-hardcoded-paths.md"
printf -- '- [Old offender](old-offender.md) — 2,020,000 TL at 40.5%% gross\n' > "$MEM/MEMORY.md"
printf -- '---\nname: no-curl-pipe\ntype: feedback\n---\nbody\n' > "$MEM/no-curl-pipe.md"
printf -- '---\nname: finances\ntype: project\n---\nbody\n' > "$MEM/finances.md"
export CLAUDE_CONFIG_DIR="$CFG"

total=0
failed=0

while IFS=$'\t' read -r verdict tool file text; do
    case "${verdict-}" in ''|'#'*) continue ;; esac
    [ -n "${file-}" ] || continue

    case "$verdict" in
        pass) want=0 ;;
        block) want=2 ;;
        *) echo "unknown verdict '$verdict'" >&2; exit 1 ;;
    esac

    case "$file" in
        rule-dup:*) path="$MEM/${file#rule-dup:}.md" ;;
        *) path="$MEM/$file" ;;
    esac
    decoded=$(printf '%b' "$text")
    field=content
    [ "$tool" = "Edit" ] && field=new_string
    payload=$(jq -n --arg t "$tool" --arg p "$path" --arg c "$decoded" --arg f "$field" \
        '{tool_name: $t, tool_input: ({file_path: $p} + {($f): $c})}')

    got=0
    reason=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?

    total=$((total + 1))
    oneline=$(printf '%s %s %s' "$tool" "$file" "$text" | tr '\n' ' ' | cut -c1-90)

    if [ "$got" = "$want" ]; then
        [ "$VERBOSE" = "1" ] && printf 'ok    %-6s %s\n' "$verdict" "$oneline"
    else
        failed=$((failed + 1))
        printf 'FAIL  want %s, got %s: %s\n' "$want" "$got" "$oneline"
        printf '      %s\n' "$(printf '%s' "$reason" | head -1)"
    fi
done < "$CASES"

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = "0" ]
