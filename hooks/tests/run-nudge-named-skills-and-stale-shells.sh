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

mkdir -p "$CLAUDE_CONFIG_DIR/commands"
printf -- '---\ndescription: x\ndisable-model-invocation: true\n---\nbody\n' > "$CLAUDE_CONFIG_DIR/commands/refocus.md"
printf -- '---\ndescription: x\n---\ndisable-model-invocation: true\n' > "$CLAUDE_CONFIG_DIR/commands/bodyonly.md"

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
        if [ "$VERBOSE" = 1 ]; then echo "ok    $1"; fi
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

# User-only commands, ordinary-match clause, and names the roster lacks.
hook_out() { run "$WORK/lister-none" "x-$n" "$1" | context; }
out=$(hook_out "please run /refocus on this thing")
case "$out" in *"/refocus, a user-only command ("*"commands/refocus.md, disable-model-invocation)"*"never call it uninstalled."*) check "user-only command line" 1 ;; *) check "user-only command line" 0 ;; esac
case "$out" in *"invoke it with the Skill tool"*) check "user-only command is not told to use the Skill tool" 0 ;; *) check "user-only command is not told to use the Skill tool" 1 ;; esac
out=$(hook_out "please run /bodyonly on this thing")
case "$out" in *"a user-only command"*) check "marker in the body is not frontmatter" 0 ;; *) check "marker in the body is not frontmatter" 1 ;; esac
out=$(hook_out "please use search-history to find that")
case "$out" in *"absence from your skill list does not mean it is missing"*) check "ordinary match carries the absence clause" 1 ;; *) check "ordinary match carries the absence clause" 0 ;; esac
out=$(hook_out "please run /nosuchthing on this now")
case "$out" in *"/nosuchthing, which the hook's roster does not hold"*) check "unknown /name line" 1 ;; *) check "unknown /name line" 0 ;; esac
for p in "look in /usr/bin for the binary" "see https://example.com/foo/bar for the docs" "check /usr please and /tmp too" "open /Users/x/dev/repo now please" "use and/or whichever works"; do
    out=$(hook_out "$p")
    [ -z "$out" ] && check "no unknown-name line for: $p" 1 || check "no unknown-name line for: $p" 0
done
# A roster cache from before the mark existed (bare names) is not read.
mkdir -p "$CLAUDE_CONFIG_DIR/nudge-named-skills"
printf 'refocus\n' > "$CLAUDE_CONFIG_DIR/nudge-named-skills/roster.cache"
out=$(hook_out "please run /refocus on this thing")
case "$out" in *"a user-only command"*) check "old roster cache is rebuilt" 1 ;; *) check "old roster cache is rebuilt" 0 ;; esac

# The shells line is refreshed in a detached process, so a session's first prompt carries none: prime
# the session with one prompt, wait for its cache, and the next prompt carries the line.
prime() { # lister session
    run "$1" "$2" "hello there how are you doing today" >/dev/null
    local i
    for i in $(seq 1 50); do [ -e "$TMPDIR/session-shells-warn-$2" ] && return 0; sleep 0.1; done
    return 1
}
out=$(run "$WORK/lister-shell" shells-first "hello there how are you doing today" | context)
[ -z "$out" ] && check "first prompt carries no shells line" 1 || check "first prompt carries no shells line" 0
prime "$WORK/lister-shell" shells-a
out=$(run "$WORK/lister-shell" shells-a "hello there how are you doing today" | context)
case "$out" in *"1 background shell(s) running over 60 minutes"*) check "shells line alone" 1 ;; *) check "shells line alone" 0 ;; esac
prime "$WORK/lister-shell" shells-b
out=$(run "$WORK/lister-shell" shells-b "please use search-history to find that" | context)
case "$out" in *"/search-history"*"background shell"*) check "skill line then shells line" 1 ;; *) check "skill line then shells line" 0 ;; esac
prime "$WORK/lister-shell" shells-c
out=$(run "$WORK/lister-shell" shells-c "<agent-message from=\"x\"> done </agent-message>" | context)
case "$out" in *"background shell"*) check "shells line on relayed text" 1 ;; *) check "shells line on relayed text" 0 ;; esac

# A slow lister never delays a prompt: cold cache, and a stale cache that is used as it stands.
cat > "$WORK/lister-slow" <<'STUB'
#!/bin/bash
sleep 5
echo "bash 4242 elapsed 90m: sleep 9999"
STUB
chmod +x "$WORK/lister-slow"
start=$(date +%s)
run "$WORK/lister-slow" slow-cold "hello there how are you doing today" >/dev/null
[ $(( $(date +%s) - start )) -lt 3 ] && check "cold cache does not wait on the lister" 1 || check "cold cache does not wait on the lister" 0
printf '%s' "This session has 2 background shell(s) running over 60 minutes (first: old). Check." > "$TMPDIR/session-shells-warn-slow-stale"
touch -t 202001010000 "$TMPDIR/session-shells-warn-slow-stale"
start=$(date +%s)
out=$(run "$WORK/lister-slow" slow-stale "hello there how are you doing today" | context)
[ $(( $(date +%s) - start )) -lt 3 ] && check "stale cache does not wait on the lister" 1 || check "stale cache does not wait on the lister" 0
case "$out" in *"2 background shell(s)"*) check "stale cache is still used" 1 ;; *) check "stale cache is still used" 0 ;; esac
out=$(run "$WORK/lister-none" shells-d "hello there how are you doing today" | context)
[ -z "$out" ] && check "no shells, no skill, no output" 1 || check "no shells, no skill, no output" 0
out=$(run "$WORK/does-not-exist" shells-e "hello there how are you doing today" | context)
[ -z "$out" ] && check "missing lister fails open" 1 || check "missing lister fails open" 0
out=$(printf '{"session_id":"x"}' | bash "$HOOK"; echo "rc=$?")
[ "$out" = "rc=0" ] && check "empty prompt exits 0 silently" 1 || check "empty prompt exits 0 silently" 0

echo "nudge-named-skills-and-stale-shells cases failed: $fail of $n"
[ "$fail" = 0 ]
