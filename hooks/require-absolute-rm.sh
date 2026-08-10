#!/bin/bash
# PreToolUse hook: every deletion must name its targets by absolute path
#
# The failure this exists to prevent is a wrong cwd assumption. `rm -rf build`
# is correct in one directory and catastrophic one level up, and the agent
# issuing it cannot see which directory it is actually in. An absolute path
# carries its own context, so a stale mental model of the cwd cannot redirect
# the delete at something else.
#
# Enforced for rm, rmdir, unlink and trash:
#   - every operand must start with /, ~/ or $HOME/
#   - no glob metacharacters — an unenumerated set is exactly how the wrong
#     file gets caught in the fire; list the directory, then delete by name
#   - no unresolved variables or command substitution (cannot be verified)
#   - never / itself or a single-component path like /Users
# Also covered, because they are the obvious ways around the above:
#   - find ... -delete / -exec rm, whose starting points must be absolute
#   - xargs rm, whose operands arrive on stdin and cannot be checked at all
#   - `sh -c "…"`, `eval "…"`, and shells nested inside xargs/find -exec, whose
#     command text sits right there on the command line and is re-checked
#
# Not covered: deletions inside a script file, a make target, or an npm script.
# Those are committed code whose relative paths are relative to a root the script
# establishes itself, and scanning them would block nearly every clean and build
# path.
#
# Bash, not zsh, to match block-tree-discard.sh beside it and to keep working
# on Linux boxes that sync agents-shared without /bin/zsh.
#
# There is deliberately no override: run unverifiable deletes in your own shell.

set -e

INPUT=$(cat)

COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')

if [ -z "$COMMAND" ]; then
    exit 0
fi

SUGGESTION=""

deny() {
    echo "BLOCKED: $1" >&2
    echo >&2
    echo "Deletions must name every target by absolute path." >&2
    if [ -n "$SUGGESTION" ]; then
        echo "Resolved against this session's cwd, you probably meant:" >&2
        echo "    $SUGGESTION" >&2
        echo "Confirm that is the intended target before re-issuing it." >&2
    else
        echo "Run pwd, resolve the target yourself, then re-issue with the full path." >&2
    fi
    echo "Globs are not accepted: list the directory and delete named paths," >&2
    echo "or delete the whole absolute directory in one go." >&2
    exit 2
}

# Drop heredoc bodies before anything is parsed. A heredoc body is data — a
# commit message, a generated file, documentation — and prose there routinely
# mentions rm in backticks, which the splitter would otherwise read as command
# substitution and judge as a bare `rm`. Same carve-out as a script file: text
# fed to a shell on stdin is script content, not an improvised command.
strip_heredocs() {
    awk '
    {
        if (skipping) {
            probe = $0
            sub(/^[ \t]*/, "", probe)
            if (probe == delim) skipping = 0
            next
        }
        if (match($0, /(^|[ \t;&|])<<-?[ \t]*("[A-Za-z_][A-Za-z0-9_]*"|'\''[A-Za-z_][A-Za-z0-9_]*'\''|[A-Za-z_][A-Za-z0-9_]*)/)) {
            delim = substr($0, RSTART, RLENGTH)
            sub(/^[^<]*<<-?[ \t]*/, "", delim)
            gsub(/["'\'']/, "", delim)
            skipping = 1
        }
        print
    }
    '
}

# Split a segment into tokens, one per line, honouring quotes so that a path
# containing spaces stays a single operand and quote characters are stripped.
tokenize() {
    awk '
    {
        n = length($0); quote = ""; tokseen = 0; tok = ""
        for (i = 1; i <= n; i++) {
            c = substr($0, i, 1)
            if (quote != "") {
                if (quote == "\"" && c == "\\") {
                    i++; tok = tok substr($0, i, 1); continue
                }
                if (c == quote) { quote = ""; continue }
                tok = tok c; continue
            }
            if (c == "\"" || c == "'\''") { quote = c; tokseen = 1; continue }
            if (c == "\\") { i++; tok = tok substr($0, i, 1); tokseen = 1; continue }
            if (c == " " || c == "\t") {
                if (tokseen) { print tok; tok = ""; tokseen = 0 }
                continue
            }
            tok = tok c; tokseen = 1
        }
        if (tokseen) print tok
    }
    '
}

# An operand is acceptable only if it is unambiguously absolute, free of globs,
# free of unresolved expansions, and deeper than a top-level system directory.
check_operand() {
    local p=$1
    local verb=$2

    SUGGESTION=""

    case "$p" in
        *'*'*|*'?'*|*'['*)
            deny "$verb $p — glob in a deletion target"
            ;;
        '$HOME/'*|'${HOME}/'*|'~/'*)
            ;;
        *'$'*|*'`'*)
            deny "$verb $p — unresolved expansion, the real target cannot be verified"
            ;;
        /*)
            ;;
        *)
            if [ -n "$CWD" ]; then
                SUGGESTION="$verb ${CWD%/}/${p#./}"
            fi
            deny "$verb $p — relative path"
            ;;
    esac

    # Root and single-component absolute paths are never a legitimate target.
    # Trailing slashes are stripped first so /Users/ is judged as /Users.
    local np=$p
    while :; do
        case "$np" in
            /) break ;;
            */) np=${np%/} ;;
            *) break ;;
        esac
    done
    case "$np" in
        /) deny "$verb $p — filesystem root" ;;
        /*/*) ;;
        /*) deny "$verb $p — top-level directory" ;;
    esac
}

check_deletion() {
    local verb=$1
    shift

    local endopts=0
    local operands=0
    local a
    for a in "$@"; do
        if [ "$endopts" = "0" ]; then
            case "$a" in
                --) endopts=1; continue ;;
                -*) continue ;;
            esac
        fi
        operands=$((operands + 1))
        check_operand "$a" "$verb"
    done

    if [ "$operands" = "0" ]; then
        deny "$verb with no explicit path operands"
    fi
}

# find's starting points are everything before its first -expression.
check_find() {
    local -a args=("$@")
    local deletes=0
    local a
    for a in ${args[@]+"${args[@]}"}; do
        case "$a" in
            -delete|-exec|-execdir|-ok|-okdir) deletes=1 ;;
        esac
    done
    if [ "$deletes" = "0" ]; then
        return 0
    fi
    case " ${args[*]} " in
        *" -delete "*|*" rm "*|*" rmdir "*|*" unlink "*|*" trash "*) ;;
        *) return 0 ;;
    esac

    local starts=0
    for a in ${args[@]+"${args[@]}"}; do
        case "$a" in
            -*) break ;;
        esac
        starts=$((starts + 1))
        check_operand "$a" "find"
    done
    if [ "$starts" = "0" ]; then
        deny "find with a delete action and no explicit starting path"
    fi
}

# Walk a token list and re-check the command string of any shell invoked with
# -c. One pass covers `bash -c "…"`, `xargs -I{} sh -c '…'` and
# `find … -exec sh -c '…' \;`, since all three put the text in an operand.
scan_nested_shells() {
    local depth=$1
    shift
    local -a a=("$@")
    local n=${#a[@]}
    local j=0
    local k

    while [ $j -lt $n ]; do
        case "${a[$j]##*/}" in
            sh|bash|zsh|dash|ksh|ash|fish)
                k=$((j + 1))
                while [ $k -lt $n ]; do
                    case "${a[$k]}" in
                        # find's own actions end in "c" too; not shell flags.
                        -exec|-execdir)
                            k=$((k + 1))
                            ;;
                        -*c)
                            if [ $((k + 1)) -lt $n ]; then
                                check_command "${a[$((k + 1))]}" "$((depth + 1))"
                            fi
                            break
                            ;;
                        -*)
                            k=$((k + 1))
                            ;;
                        *)
                            break
                            ;;
                    esac
                done
                ;;
        esac
        j=$((j + 1))
    done
}

check_segment() {
    local seg=$1
    local depth=$2
    local -a tok=()
    local t
    while IFS= read -r t; do
        tok+=("$t")
    done < <(printf '%s\n' "$seg" | tokenize)

    if [ ${#tok[@]} -eq 0 ]; then
        return 0
    fi

    # Skip leading environment assignments and transparent wrappers.
    local i=0
    while [ $i -lt ${#tok[@]} ]; do
        case "${tok[$i]}" in
            *=*|sudo|command|nohup|time|env|builtin|exec)
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

    local cmd=${tok[$i]}
    i=$((i + 1))

    local -a rest=()
    if [ $i -lt ${#tok[@]} ]; then
        rest=("${tok[@]:$i}")
    fi

    case "${cmd##*/}" in
        rm|rmdir|unlink|trash)
            check_deletion "${cmd##*/}" ${rest[@]+"${rest[@]}"}
            ;;
        find)
            check_find ${rest[@]+"${rest[@]}"}
            scan_nested_shells "$depth" ${rest[@]+"${rest[@]}"}
            ;;
        xargs)
            local a
            for a in ${rest[@]+"${rest[@]}"}; do
                case "${a##*/}" in
                    rm|rmdir|unlink|trash)
                        deny "xargs $a — operands arrive on stdin and cannot be verified"
                        ;;
                esac
            done
            scan_nested_shells "$depth" ${rest[@]+"${rest[@]}"}
            ;;
        sh|bash|zsh|dash|ksh|ash|fish)
            scan_nested_shells "$depth" "${cmd##*/}" ${rest[@]+"${rest[@]}"}
            ;;
        eval)
            # eval's operands ARE the command text; the tokenizer already
            # stripped one layer of quoting, so rejoin and re-check.
            if [ ${#rest[@]} -gt 0 ]; then
                check_command "${rest[*]}" "$((depth + 1))"
            fi
            ;;
    esac

    return 0
}

# Split on shell separators so `cd /tmp && rm -rf build` is inspected segment by
# segment. Separators inside quotes are literal text, not separators.
split_command() {
    awk '
    # quote persists across records: a quoted string in a real command may span
    # lines, and resetting per line makes a | inside one look like a pipe.
    BEGIN { quote = "" }
    {
        n = length($0); seg = ""
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
# deny()'s exit 2 would not reach the hook's exit status. Recursion re-enters
# here for each nested -c string, so the depth guard fails closed rather than
# letting a deeply wrapped command through unread.
check_command() {
    local cmdstr=$1
    local depth=${2:-0}
    local segment

    if [ "$depth" -gt 4 ]; then
        deny "shell nested more than 4 deep — the real target cannot be verified"
    fi

    while IFS= read -r segment; do
        check_segment "$segment" "$depth"
    done < <(printf '%s\n' "$cmdstr" | strip_heredocs | split_command)
}

check_command "$COMMAND" 0

exit 0
