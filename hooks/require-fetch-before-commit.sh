#!/bin/bash
# DESC: PreToolUse hook on Bash: refuses a `git commit` once when the branch is behind its upstream
#
# Several sessions commit to one repo, so a push is refused when another session pushed
# first. The cheapest moment to notice is before the commit: this hook fetches the
# branch's remote (a few seconds at most) and, when the remote holds commits the branch
# lacks, refuses the commit once and names them.
#
# Matches `git commit` and `git -C DIR commit` (also with -c options) anywhere in the
# command; the repo is DIR, else the folder of a leading `cd DIR`, else the call's cwd.
#
# Refused (exit 2), once per session, repo and upstream tip:
#   - the branch has an upstream and `HEAD..@{u}` is not empty after the fetch.
#     The same commit repeated passes, so a deliberate commit is never stuck.
#     The reason lists up to five remote commits and says which pull applies:
#     `git pull --ff-only` when the branch has no unpushed commits, `git pull --rebase`
#     when it has.
# Always allowed, silently:
#   - not a git commit, not a repository, a detached HEAD, a branch with no upstream
#   - a fetch that fails or exceeds the time limit (offline, no credentials, a slow
#     remote): the check fails open and costs at most that limit
#
# Bash, not zsh, to match the hooks beside it. The time limit uses perl's alarm because
# macOS ships no `timeout`.

set -e

LIMIT=${FETCH_BEFORE_COMMIT_LIMIT:-4}

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

# git [-C DIR | -c KEY=VAL | --flag]... commit, at the start of the command or after ; & | ( or a space.
COMMIT_RE='(^|[;&|(]|[[:space:]])git(([[:space:]]+-C[[:space:]]+[^[:space:]]+)|([[:space:]]+-c[[:space:]]+[^[:space:]]+)|([[:space:]]+--[a-z-]+(=[^[:space:]]+)?))*[[:space:]]+commit([[:space:]]|$|;|&|\))'
[[ "$COMMAND" =~ $COMMIT_RE ]] || exit 0
# A quoted sentence that merely mentions the command (echo "git commit ...") is not one.
case "$COMMAND" in
    echo\ *|printf\ *|grep\ *|rg\ *) exit 0 ;;
esac

CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')
DIR=$CWD
C_RE='git([[:space:]]+-c[[:space:]]+[^[:space:]]+)*[[:space:]]+-C[[:space:]]+([^[:space:]]+)'
# A command that starts with `cd DIR` commits in DIR: a session started in one repo that cds
# into another was checked against its start folder (Nov 2026, a dev-env commit refused for
# agents-shared being behind).
CD_RE='^[[:space:]]*cd[[:space:]]+("[^"]+"|'"'"'[^'"'"']+'"'"'|[^[:space:];&|]+)'
FOUND=
if [[ "$COMMAND" =~ $C_RE ]]; then
    FOUND=${BASH_REMATCH[2]}
elif [[ "$COMMAND" =~ $CD_RE ]]; then
    FOUND=${BASH_REMATCH[1]}
fi
if [ -n "$FOUND" ]; then
    DIR=$FOUND
    DIR=${DIR#[\"\']}; DIR=${DIR%[\"\']}
    case "$DIR" in "~"/*) DIR="$HOME/${DIR#\~/}" ;; esac
    [ "${DIR#/}" = "$DIR" ] && DIR="${CWD:-.}/$DIR"
fi
[ -z "$DIR" ] && DIR=.
[ -d "$DIR" ] || exit 0

g() { git -C "$DIR" "$@"; }

g rev-parse --git-dir >/dev/null 2>&1 || exit 0
BRANCH=$(g symbolic-ref --quiet --short HEAD 2>/dev/null) || exit 0
UPSTREAM=$(g rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || exit 0
REMOTE=$(g config "branch.$BRANCH.remote" 2>/dev/null) || exit 0
{ [ -z "$REMOTE" ] || [ "$REMOTE" = . ]; } && exit 0

# Fetch only the upstream's remote, never prompting, killed after $LIMIT seconds.
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh} -o BatchMode=yes -o ConnectTimeout=$LIMIT" \
    perl -e 'alarm shift; exec @ARGV' "$LIMIT" git -C "$DIR" fetch --quiet "$REMOTE" >/dev/null 2>&1 || exit 0

BEHIND=$(g rev-list --count 'HEAD..@{u}' 2>/dev/null) || exit 0
[ "${BEHIND:-0}" -gt 0 ] || exit 0

# Once per session, repo and upstream tip: the same commit repeated passes.
TIP=$(g rev-parse '@{u}')
TOP=$(g rev-parse --show-toplevel)
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // "nosession"')
SEEN_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/fetch-before-commit"
MARK="$SEEN_DIR/$SESSION-$(printf '%s' "$TOP" | cksum | cut -d' ' -f1)-$TIP"
if mkdir -p "$SEEN_DIR" 2>/dev/null && [ ! -e "$MARK" ] && : > "$MARK" 2>/dev/null; then
    find "$SEEN_DIR" -type f -mtime +14 -delete 2>/dev/null || true
else
    exit 0
fi

AHEAD=$(g rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
{
    echo "BLOCKED: $BRANCH is $BEHIND commit(s) behind $UPSTREAM; another session or machine pushed first."
    echo
    echo "Remote commits this branch lacks:"
    g log --format='  %h %s (%an)' -5 'HEAD..@{u}'
    [ "$BEHIND" -gt 5 ] && echo "  ... and $((BEHIND - 5)) more"
    echo
    if [ "$AHEAD" -eq 0 ]; then
        echo "Run \`git -C $TOP pull --ff-only\`, then commit, so the new work builds on theirs."
    else
        echo "This branch also has $AHEAD unpushed commit(s). Run \`git -C $TOP pull --rebase\` to replay them on the remote,"
        echo "run the repo's tests, then commit and push. A conflict, a branch others share, or a failing test goes to the owner;"
        echo "never force-push. A pull that refuses on uncommitted changes: repeat this commit, then rebase before pushing."
    fi
    echo
    echo "To commit as is, repeat the same call: this check refuses once."
} >&2
exit 2
