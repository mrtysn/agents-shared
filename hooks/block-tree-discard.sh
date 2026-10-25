#!/bin/bash
# PreToolUse hook: Block git commands that discard uncommitted work
#
# The single permitted case is reverting explicitly named, individually
# tracked files:  git checkout -- server/src/Foo.cs
#
# Everything wider is blocked: whole-tree and whole-directory discards,
# pathspec magic, globs, reset --hard, clean -f, stash (push, save, bare)
# and stash drop/clear. A stash lifts other sessions' uncommitted work out of
# a shared tree; a failed pop leaves it stranded.
#
# A branch switch carries every session sharing the tree onto the new branch,
# uncommitted edits included, so `git switch <branch>` and
# `git checkout <branch>` pass only from a clean tree (empty
# `git status --porcelain`), to an existing local branch, with no flags.
# Anything else (-f, --discard-changes, -m, -c, a dirty tree, a directory
# the hook cannot resolve) is blocked.
#
# To undo an edit, rewrite the file — git is not needed for that.
# There is deliberately no override: run these yourself in your own shell.

set -e

INPUT=$(cat)

COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')

if [ -z "$COMMAND" ]; then
    exit 0
fi

if [ -n "$CWD" ] && [ -d "$CWD" ]; then
    cd "$CWD"
fi

deny() {
    echo "BLOCKED: $1" >&2
    echo "This command discards uncommitted work and is not available to you." >&2
    echo "To undo an edit you made, rewrite the file instead." >&2
    echo "If a discard is genuinely required, ask the user to run it themselves." >&2
    exit 2
}

# Strip one layer of surrounding quotes from a token
unquote() {
    local s=$1
    s=${s#\"}; s=${s%\"}
    s=${s#\'}; s=${s%\'}
    printf '%s' "$s"
}

# A path is safe to revert only if it names exactly one tracked file.
# Rejects ".", "..", trailing-slash dirs, real dirs, pathspec magic (":/"),
# and glob characters. Uses ls-files so a tracked-but-deleted file still
# passes, while a directory expands to many entries and fails.
is_single_tracked_file() {
    local p=$1

    case "$p" in
        ""|"."|".."|"./"|"/"|:*|*"*"*|*"?"*|*"["*|*/)
            return 1
            ;;
    esac

    if [ -d "$p" ]; then
        return 1
    fi

    local count
    count=$(git ls-files --error-unmatch -- "$p" 2>/dev/null | wc -l | tr -d ' ')
    [ "$count" = "1" ]
}

# Set to 0 once a `cd` in the command goes somewhere the hook cannot follow;
# a switch after it is then judged against an unknown tree and blocked.
CWD_KNOWN=1

# A switch is safe when it can neither lose work nor move anyone else's: one
# argument naming an existing local branch, no flags, a clean tree.
switch_is_safe() {
    local relocated=$1
    shift
    [ "$relocated" = "0" ] && [ "$CWD_KNOWN" = "1" ] || return 1
    [ $# -eq 1 ] || return 1
    local target
    target=$(unquote "$1")
    case "$target" in
        ""|-*) return 1 ;;
    esac
    git rev-parse --git-dir >/dev/null 2>&1 || return 1
    git show-ref --verify --quiet "refs/heads/$target" || return 1
    [ -z "$(git status --porcelain 2>/dev/null)" ]
}

check_segment() {
    local seg=$1
    local -a tok=()
    read -ra tok <<< "$seg"

    if [ ${#tok[@]} -eq 0 ]; then
        return 0
    fi

    # Follow `cd` so a later switch is checked in the directory it runs in.
    if [ "$(unquote "${tok[0]}")" = "cd" ]; then
        local dir
        dir=$(unquote "${tok[1]-}")
        case "$dir" in
            "~") dir=$HOME ;;
            "~/"*) dir="$HOME/${dir#\~/}" ;;
        esac
        if [ ${#tok[@]} -eq 2 ] && [ -n "$dir" ] && [[ "$dir" != *'$'* ]] && cd "$dir" 2>/dev/null; then
            :
        else
            CWD_KNOWN=0
        fi
        return 0
    fi

    # Skip leading environment assignments (FOO=1 git ...)
    local i=0
    while [ $i -lt ${#tok[@]} ]; do
        case "${tok[$i]}" in
            *=*) i=$((i + 1)) ;;
            *) break ;;
        esac
    done

    if [ $i -ge ${#tok[@]} ]; then
        return 0
    fi

    # Only git commands are of interest
    case "$(unquote "${tok[$i]}")" in
        git|*/git) ;;
        *) return 0 ;;
    esac
    i=$((i + 1))

    # Skip git-level options. A -C/--git-dir/--work-tree relocation means path
    # arguments cannot be resolved from here, so remember it and fail closed.
    local relocated=0
    while [ $i -lt ${#tok[@]} ]; do
        case "${tok[$i]}" in
            -C|--git-dir|--work-tree)
                relocated=1
                i=$((i + 2))
                ;;
            --git-dir=*|--work-tree=*)
                relocated=1
                i=$((i + 1))
                ;;
            -c)
                i=$((i + 2))
                ;;
            -*)
                i=$((i + 1))
                ;;
            *)
                break
                ;;
        esac
    done

    if [ $i -ge ${#tok[@]} ]; then
        return 0
    fi

    local sub
    sub=$(unquote "${tok[$i]}")
    i=$((i + 1))

    local -a rest=()
    if [ $i -lt ${#tok[@]} ]; then
        rest=("${tok[@]:$i}")
    fi

    local a
    case "$sub" in
        switch)
            switch_is_safe "$relocated" ${rest[@]+"${rest[@]}"} \
                || deny "git switch — allowed only to an existing local branch, with no flags, from a clean tree (git status --porcelain empty)"
            ;;
        reset)
            for a in ${rest[@]+"${rest[@]}"}; do
                case "$(unquote "$a")" in
                    --hard|--merge|--keep)
                        deny "git reset $(unquote "$a")"
                        ;;
                esac
            done
            ;;
        clean)
            for a in ${rest[@]+"${rest[@]}"}; do
                case "$(unquote "$a")" in
                    --force|-[a-eg-zA-Z]*f*|-f*)
                        deny "git clean with --force"
                        ;;
                esac
            done
            ;;
        stash)
            case "$(unquote "${rest[0]-}")" in
                drop|clear)
                    deny "git stash $(unquote "${rest[0]}") — stashed work is unrecoverable once dropped"
                    ;;
                ""|push|save|-*)
                    deny "git stash — it lifts every uncommitted change out of the tree, other sessions' included. For a clean baseline use a worktree: git worktree add <scratch dir> HEAD"
                    ;;
            esac
            ;;
        checkout|restore)
            if [ "$sub" = "checkout" ] && switch_is_safe "$relocated" ${rest[@]+"${rest[@]}"}; then
                return 0
            fi
            local dashdash=-1
            local idx=0
            for a in ${rest[@]+"${rest[@]}"}; do
                case "$(unquote "$a")" in
                    --)
                        dashdash=$idx
                        ;;
                    -f|--force)
                        deny "git $sub --force"
                        ;;
                esac
                idx=$((idx + 1))
            done

            if [ "$relocated" = "1" ]; then
                deny "git $sub with -C/--git-dir — paths cannot be verified"
            fi

            # checkout must name its paths after an explicit --, otherwise it
            # is a branch switch or an ambiguous pathspec.
            if [ "$sub" = "checkout" ] && [ "$dashdash" -lt 0 ]; then
                deny "git checkout without an explicit -- <file>"
            fi

            # Collect candidate paths
            local -a paths=()
            idx=0
            for a in ${rest[@]+"${rest[@]}"}; do
                if [ "$dashdash" -ge 0 ]; then
                    if [ $idx -gt "$dashdash" ]; then
                        paths+=("$(unquote "$a")")
                    fi
                else
                    case "$(unquote "$a")" in
                        -*) ;;
                        *) paths+=("$(unquote "$a")") ;;
                    esac
                fi
                idx=$((idx + 1))
            done

            if [ ${#paths[@]} -eq 0 ]; then
                deny "git $sub with no explicit file paths"
            fi

            local p
            for p in "${paths[@]}"; do
                if ! is_single_tracked_file "$p"; then
                    deny "git $sub -- $p (not a single tracked file)"
                fi
            done
            ;;
    esac

    return 0
}

# Split the command on shell separators so `cd foo && git reset --hard` is
# inspected segment by segment rather than by leading prefix. Separators inside
# quotes are literal text, not separators — otherwise any command that merely
# mentions one of these git invocations gets blocked.
split_command() {
    awk '
    {
        n = length($0); quote = ""; seg = ""
        for (i = 1; i <= n; i++) {
            c = substr($0, i, 1)
            if (quote != "") {
                if (quote == "\"" && c == "\\") {
                    seg = seg c; i++; seg = seg substr($0, i, 1); continue
                }
                seg = seg c
                if (c == quote) quote = ""
                continue
            }
            if (c == "\"" || c == "'\''") { quote = c; seg = seg c; continue }
            if (c == "\\") { seg = seg c; i++; seg = seg substr($0, i, 1); continue }
            if (c == ";" || c == "|" || c == "&" || c == "(" || c == ")" || c == "`") {
                print seg; seg = ""; continue
            }
            seg = seg c
        }
        print seg
    }
    '
}

# Process substitution, not a pipe: a pipe would run the loop in a subshell and
# deny()'s exit 2 would not reach the hook's exit status.
while IFS= read -r segment; do
    check_segment "$segment"
done < <(printf '%s\n' "$COMMAND" | split_command)

exit 0
