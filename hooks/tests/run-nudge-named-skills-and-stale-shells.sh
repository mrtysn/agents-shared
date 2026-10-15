#!/bin/bash
# DESC: Run the nudge-named-skills-and-stale-shells UserPromptSubmit hook against its case file
#
# Bash, not zsh, to match the hook under test and to keep working on Linux machines that sync
# agents-shared without /bin/zsh.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../nudge-named-skills-and-stale-shells.sh"
CASES="$HERE/nudge-named-skills-and-stale-shells-cases.tsv"

if [ "${1:-}" = -h ] || [ "${1:-}" = --help ]; then
    cat <<'USAGE'
usage: run-nudge-named-skills-and-stale-shells.sh [-v] [case-file]

Feeds each case to the hook as a UserPromptSubmit payload and checks the skill line (none, or the
skills named). Then checks the old-shells line with a stub lister: present when the lister prints a
shell, absent when it prints nothing, present beside a skill line, and present for relayed text.
USAGE
    exit 0
fi
VERBOSE=0
[ "${1:-}" = -v ] && { VERBOSE=1; shift; }
[ -n "${1:-}" ] && CASES=$1

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
export CLAUDE_CONFIG_DIR="$WORK/config" TMPDIR="$WORK/tmp"
mkdir -p "$TMPDIR"
for s in stg-msg-cmt search-history new-repo archify humanizer outstanding; do
    mkdir -p "$CLAUDE_CONFIG_DIR/skills/$s"
    : > "$CLAUDE_CONFIG_DIR/skills/$s/SKILL.md"
done

cat > "$WORK/lister-shell" <<'STUB'
#!/bin/bash
echo "bash 4242 elapsed 90m: sleep 9999"
STUB
cat > "$WORK/lister-none" <<'STUB'
#!/bin/bash
exit 0
STUB
chmod +x "$WORK/lister-shell" "$WORK/lister-none"

run() { # lister session prompt
    jq -n --arg s "$2" --arg p "$3" '{session_id: $s, prompt: $p}' | SESSION_SHELLS_LISTER="$1" bash "$HOOK"
}
context() { jq -r '.hookSpecificOutput.additionalContext // empty' 2>/dev/null; }

fail=0 n=0
check() { # name ok
    n=$((n + 1))
    if [ "$2" = 1 ]; then
        [ "$VERBOSE" = 1 ] && echo "ok    $1"
    else
        echo "FAIL  $1"; fail=$((fail + 1))
    fi
}

while IFS=$'\t' read -r expected prompt; do
    case "$expected" in ''|'#'*) continue ;; esac
    out=$(run "$WORK/lister-none" "case-$n" "$prompt" | context)
    ok=1
    if [ "$expected" = none ]; then
        [ -z "$out" ] || ok=0
    else
        IFS=, read -ra names <<<"${expected#skill:}"
        for nm in "${names[@]}"; do
            case "$out" in *"/$nm"*) ;; *) ok=0 ;; esac
        done
        case "$out" in *"names the skill"*) ;; *) ok=0 ;; esac
        case "$out" in *"background shell"*) ok=0 ;; esac
    fi
    check "$expected <- $prompt" "$ok"
done < "$CASES"

out=$(run "$WORK/lister-shell" shells-a "hello there how are you doing today" | context)
case "$out" in *"1 background shell(s) running over 60 minutes"*) check "shells line alone" 1 ;; *) check "shells line alone" 0 ;; esac
out=$(run "$WORK/lister-shell" shells-b "please use search-history to find that" | context)
case "$out" in *"/search-history"*"background shell"*) check "skill line then shells line" 1 ;; *) check "skill line then shells line" 0 ;; esac
out=$(run "$WORK/lister-shell" shells-c "<agent-message from=\"x\"> done </agent-message>" | context)
case "$out" in *"background shell"*) check "shells line on relayed text" 1 ;; *) check "shells line on relayed text" 0 ;; esac
out=$(run "$WORK/lister-none" shells-d "hello there how are you doing today" | context)
[ -z "$out" ] && check "no shells, no skill, no output" 1 || check "no shells, no skill, no output" 0
out=$(run "$WORK/does-not-exist" shells-e "hello there how are you doing today" | context)
[ -z "$out" ] && check "missing lister fails open" 1 || check "missing lister fails open" 0
out=$(printf '{"session_id":"x"}' | bash "$HOOK"; echo "rc=$?")
[ "$out" = "rc=0" ] && check "empty prompt exits 0 silently" 1 || check "empty prompt exits 0 silently" 0

echo "nudge-named-skills-and-stale-shells cases failed: $fail of $n"
[ "$fail" = 0 ]
