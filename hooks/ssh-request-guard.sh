#!/bin/bash
# PreToolUse hook: code that can reach the network, run on a remote host over ssh, needs the user's yes
#
# The failure this exists to prevent: testing a scraper by running it on a server. Every request it
# makes leaves from that server's IP — outside this machine's agent-request-limiter, uncounted — and
# a rate limit or ban lands on a production box. On 2026-09-22 an agent sent ~45 requests to Google
# from node01 this way, via `ssh node01 'docker exec funds-poller python …'`, while debugging code
# that could have been tested locally against one saved response.
#
# For every ssh, autossh or mosh command (also by path, e.g. /usr/bin/ssh), asks (never blocks) when:
#   - the remote command mentions a network-capable program anywhere in its text: curl, wget, nc,
#     socat, openssl s_client, /dev/tcp, http(ie), interpreters and package managers (python, node,
#     ruby, perl, php, uv, uvx, pip, npm, yarn, cargo, go run…), git clone|fetch|pull, apt/apk/dnf,
#     and code run inside a container (docker|podman|nerdctl … exec|run, docker-compose, kubectl
#     exec|run|debug). Whole-text on purpose: wrappers (timeout, sudo, xargs, eval, sh -c) stay covered.
#   - a remote shell reads its script from stdin: a heredoc fed to ssh is checked like a remote
#     command; a script from `< file` or a pipe cannot be read, so it asks.
#   - a tunnel would carry traffic out from the remote host: -D / DynamicForward, or -L /
#     LocalForward to anything but localhost.
# Only ssh's own arguments are checked: `ssh host 'cat x' | python3 …` runs python locally and passes.
# Plain inspection (ls, cat, docker ps, docker logs, journalctl) passes, as do scp and rsync.
#
# Inspection inside a container passes too, when the hook can see that it cannot reach the network:
#   - `docker|podman|nerdctl [compose] exec [opts] CONTAINER PROG …` where PROG is a file tool with no
#     network ability (sqlite3, cat, grep, jq, sed, ls, tail …) and its arguments carry no network word;
#   - the same with PROG `fetch-anything` and a read-only verb (status, incidents, incident, events,
#     credential, consumer, rules, response): the gateway's own client, talking to the gateway;
#   - the same with PROG python and inline code — `-c CODE`, or `-` fed by a heredoc the hook can
#     read — that names no network, process or import machinery (urllib, requests, http, socket,
#     subprocess, os.system, importlib, __import__, eval, exec, a URL …). Code from a file or a pipe
#     cannot be read, so it asks: feed a script as a heredoc instead.
#   Every other command in the same remote text must itself be free of network words.
#
# Known false positive, kept deliberately: a network word inside an argument asks too — e.g. `https`
# in a grep pattern. Not covered: a remote script file (`ssh host ./fetch.sh`), which the hook cannot
# read, and ssh inside a local script file (same carve-out as require-absolute-rm.sh).
#
# Bash, not zsh, to match the hooks beside it and to keep working on Linux boxes that sync
# agents-shared without /bin/zsh. Written for bash 3.2 (macOS /bin/bash): no mapfile, no assoc arrays.

set -e

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

SSH_WORD_RE='(^|[;&|({`[:space:]])([^[:space:];&|]*/)?(ssh|autossh|mosh)[[:space:]]'
MARK=$'\001'

WORD_RE='(^|[^[:alnum:]_.-])(curl|wget|nc|ncat|socat|telnet|https?|httpie|aria2c|lynx|w3m|ftp|sftp|python[0-9.]*|node|deno|bun|ruby|perl|php|uv|uvx|pipx|pip[0-9.]*|npm|npx|yarn|pnpm|poetry|gem|bundle|cargo|docker-compose)([^[:alnum:]_.-]|$)'
SUB_RE='(^|[^[:alnum:]_.-])((docker|podman|nerdctl)([[:space:]][^;&|]*)?[[:space:]](exec|run)|kubectl([[:space:]][^;&|]*)?[[:space:]](exec|run|debug)|git([[:space:]][^;&|]*)?[[:space:]](clone|fetch|pull|ls-remote|submodule)|(apt|apt-get)([[:space:]][^;&|]*)?[[:space:]](update|install|upgrade|full-upgrade|dist-upgrade)|apk([[:space:]][^;&|]*)?[[:space:]](add|update|upgrade)|(dnf|yum)([[:space:]][^;&|]*)?[[:space:]](install|update|upgrade|makecache)|go[[:space:]]+(run|get|install|mod)|openssl([[:space:]][^;&|]*)?[[:space:]]s_client)([^[:alnum:]_.-]|$)'
# bash's network redirection; followed by a host, so it has no word boundary after it
DEV_RE='/dev/(tcp|udp)/'

ask() {
    jq -n --arg r "$1" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $r}}'
    exit 0
}

NET_REASON="Whatever it fetches leaves from that host's IP, outside this machine's agent-request-limiter and uncounted, and a rate limit or ban lands on that server. To test code that makes requests: fetch once locally, save the response, and test against the saved copy. Run network code on a server only when the user asked for exactly that."

# The first network-capable word in a text, or nothing.
net_hit() {
    printf '%s\n' "$1" | { grep -Eo "$SUB_RE|$WORD_RE|$DEV_RE" || true; } | head -1 | sed -E 's/^[^[:alnum:]\/]+//; s/[^[:alnum:]]+$//'
}

# Heredoc bodies are data — commit messages, generated files — and routinely mention ssh and curl, so
# they are removed. The exception is a heredoc opened on an ssh line: that body is the remote shell's
# script. Its lines are kept, prefixed with MARK, for the caller to separate.
split_heredocs() {
    awk -v mark="$MARK" '
    {
        if (skipping) {
            probe = $0
            sub(/^[ \t]*/, "", probe)
            if (probe == delim) { skipping = 0; next }
            if (tossh) print mark $0
            next
        }
        if (match($0, /(^|[ \t;&|])<<-?[ \t]*("[A-Za-z_][A-Za-z0-9_]*"|'\''[A-Za-z_][A-Za-z0-9_]*'\''|[A-Za-z_][A-Za-z0-9_]*)/)) {
            delim = substr($0, RSTART, RLENGTH)
            sub(/^[^<]*<<-?[ \t]*/, "", delim)
            gsub(/["'\'']/, "", delim)
            skipping = 1
            tossh = ($0 ~ /(^|[;&|({` \t])([^ \t;&|]*\/)?(ssh|autossh|mosh)[ \t]/)
        }
        print
    }
    '
}

# Simple commands, one per line as "<separator before it><TAB><command>", quote-aware. The separator
# tells a pipe into ssh apart from a sequence; a newline counts as ;. Same splitting as
# require-absolute-rm.sh, which also cuts at ( ) and backticks so $(ssh …) is a command of its own.
split_segments() {
    awk '
    BEGIN { quote = ""; sep = ";" }
    {
        n = length($0); seg = ""
        for (i = 1; i <= n; i++) {
            c = substr($0, i, 1)
            if (quote != "") {
                if (quote == "\"" && c == "\\") { seg = seg c; i++; seg = seg substr($0, i, 1); continue }
                seg = seg c
                if (c == quote) quote = ""
                continue
            }
            if (c == "\"" || c == "'\''") { quote = c; seg = seg c; continue }
            if (c == "\\") { seg = seg c; i++; seg = seg substr($0, i, 1); continue }
            if (c == ";" || c == "|" || c == "&" || c == "(" || c == ")" || c == "`") {
                print sep "\t" seg; seg = ""; sep = c; continue
            }
            seg = seg c
        }
        if (quote == "") { print sep "\t" seg; sep = ";" } else seg = seg "\n"
    }
    '
}

# Words of one command, one per line, with one layer of quoting removed — what ssh receives.
tokenize() {
    awk '
    {
        n = length($0); quote = ""; tokseen = 0; tok = ""
        for (i = 1; i <= n; i++) {
            c = substr($0, i, 1)
            if (quote != "") {
                if (quote == "\"" && c == "\\") { i++; tok = tok substr($0, i, 1); continue }
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

BODY=""

# Programs that read files and print, and cannot open a socket.
RO_PROG_RE='^(sqlite3|cat|ls|grep|egrep|fgrep|zgrep|head|tail|wc|sed|awk|jq|sort|uniq|stat|du|df|echo|printf|printenv|env|date|cut|tr|test|true|file|md5sum|sha256sum|readlink|realpath|find|tree|diff|cmp|od|xxd|strings|column|nl|tac|rev|basename|dirname|pwd|id|whoami|uptime|free|ps|top|hostname|uname|sleep)$'
# The gateway's client verbs that only read.
FA_RO_VERB_RE='^(status|incidents|incident|events|credential|consumer|rules|response)$'
# Python that can leave the host, start a process, or hide an import.
PY_NET_RE='(^|[^[:alnum:]_])(urllib[0-9]?|requests|http|httplib[0-9]?|socket|socketserver|aiohttp|httpx|ftplib|smtplib|telnetlib|websockets?|subprocess|os\.system|os\.popen|os\.exec[a-z]*|os\.spawn[a-z]*|os\.fork|multiprocessing|importlib|__import__|pycurl|paramiko|fabric|boto3?|botocore|grpc|xmlrpc|nntplib|poplib|imaplib|asyncio|ssl|pexpect|ctypes|eval|exec|compile|pip|curl|wget|nc|ncat|socat)([^[:alnum:]_]|$)|https?://'

# Standard modules that read, compute and print; nothing here opens a socket or starts a process.
PY_SAFE_MOD_RE='^(sqlite3|json|time|datetime|collections|re|sys|math|itertools|functools|statistics|csv|pathlib|textwrap|string|bisect|heapq|decimal|fractions|pprint|dataclasses|typing|enum|operator|glob|io|zlib|gzip|bz2|lzma|base64|hashlib|uuid|random|struct|array|copy|contextlib|argparse|warnings|traceback|calendar|locale|unicodedata|difflib|fnmatch|shlex|html|xml|configparser|tomllib|zoneinfo|os)$'

# 0 when one remote command, given as its tokens, is inspection inside a container that cannot
# reach the network; 1 otherwise. $1 is 1 when a heredoc body is available for a stdin script.
safe_container_exec() {
    local heredoc=$1; shift
    local -a tok=("$@")
    local n=${#tok[@]} i=0 t b
    while [ $i -lt $n ]; do                         # shell keywords a command may follow
        case "${tok[$i]}" in do|then|else|elif|if|while|until|'{'|'!'|time) i=$((i + 1)) ;; *) break ;; esac
    done
    [ $((n - i)) -lt 4 ] && return 1
    b=${tok[$i]##*/}
    case "$b" in docker|podman|nerdctl) ;; *) return 1 ;; esac
    i=$((i + 1))
    [ "${tok[$i]:-}" = compose ] && i=$((i + 1))
    [ "${tok[$i]:-}" = exec ] || return 1
    i=$((i + 1))
    # exec's options; the ones that take a value swallow the next token unless written as -eX / --env=X
    while [ $i -lt $n ]; do
        t=${tok[$i]}
        case "$t" in
            -e|--env|-w|--workdir|-u|--user|--env-file|--detach-keys) i=$((i + 2)); continue ;;
            --*=*|-e?*|-w?*|-u?*) i=$((i + 1)); continue ;;
            -*) i=$((i + 1)); continue ;;
        esac
        break
    done
    i=$((i + 1))                                    # the container
    [ $i -lt $n ] || return 1
    b=${tok[$i]##*/}
    i=$((i + 1))
    local rest="${tok[*]:$i}"
    if printf '%s\n' "$b" | grep -Eq "$RO_PROG_RE"; then
        [ -z "$(net_hit "$rest")" ] && return 0
        return 1
    fi
    case "$b" in
        fetch-anything)
            printf '%s\n' "${tok[$i]:-}" | grep -Eq "$FA_RO_VERB_RE" && return 0
            return 1 ;;
        python|python[0-9]*)
            local code=""
            if [ "${tok[$i]:-}" = -c ]; then
                code=${tok[$((i + 1))]:-}
                [ -z "$code" ] && return 1
            elif [ $i -ge $n ] || { [ "${tok[$i]}" = - ] && [ $((i + 1)) -ge $n ]; }; then
                [ $heredoc = 1 ] && [ -n "$BODY" ] || return 1
                code=$BODY
            else
                return 1
            fi
            printf '%s\n' "$code" | grep -Eq "$PY_NET_RE" && return 1
            # every module it imports must be one that cannot reach the network
            local mod
            while IFS= read -r mod; do
                [ -z "$mod" ] && continue
                printf '%s\n' "${mod%%.*}" | grep -Eq "$PY_SAFE_MOD_RE" || return 1
            done < <(printf '%s\n' "$code" \
                | sed -E 's/from[[:space:]]+([A-Za-z_][A-Za-z0-9_.]*)[[:space:]]+import[[:space:]]+[^;]*/import \1/g' \
                | grep -Eo '(^|[;[:space:](])import[[:space:]]+[A-Za-z_][A-Za-z0-9_., ]*' \
                | sed -E 's/^.*import[[:space:]]+//; s/[[:space:]]+as[[:space:]]+[A-Za-z_0-9]+//g' | tr ',' '\n' | tr -d ' ')
            return 0 ;;
    esac
    return 1
}

# 0 when every command in a remote text is either free of network words or a safe container exec.
safe_remote() {
    local heredoc=$1 text=$2 sep seg t
    local -a tok
    while IFS=$'\t' read -r sep seg; do
        [ -z "${seg// /}" ] && continue
        [ -z "$(net_hit "$seg")" ] && continue
        tok=()
        while IFS= read -r t; do tok+=("$t"); done < <(printf '%s\n' "$seg" | tokenize)
        safe_container_exec "$heredoc" "${tok[@]}" || return 1
    done < <(printf '%s\n' "$text" | split_segments)
    return 0
}

check_segment() {
    local sep=$1 seg=$2 t b word="" i=0
    local -a tok=()
    while IFS= read -r t; do tok+=("$t"); done < <(printf '%s\n' "$seg" | tokenize)
    local n=${#tok[@]}

    # ssh must be the command word; env assignments and simple local wrappers may precede it
    while [ $i -lt $n ]; do
        t=${tok[$i]}
        b=${t##*/}
        case "$b" in ssh|autossh|mosh) word=$b; break ;; esac
        case "$t" in
            *=*|sudo|env|nohup|time|timeout|nice|command|exec|-*|[0-9]*) i=$((i + 1)); continue ;;
        esac
        return 0
    done
    [ -z "$word" ] && return 0
    i=$((i + 1))

    # ssh's options that take a value; autossh adds -M
    local argopts="BbcDEeFIiJLlmOoPpQRSWw" host="" dyn=0 stdin_file=0 heredoc=0 opt val k len
    [ "$word" = autossh ] && argopts="${argopts}M"
    local -a remote=() fwd=()
    while [ $i -lt $n ]; do
        t=${tok[$i]}
        if [ ${#remote[@]} -eq 0 ]; then
            # local redirections of the ssh command itself: < file and << heredoc feed the remote stdin
            if [[ $t =~ ^[0-9]*(<<-?|<>|<|>>|>|&>|>&|<&)(.*)$ ]]; then
                case "${BASH_REMATCH[1]}" in "<<"|"<<-") heredoc=1 ;; "<") stdin_file=1 ;; esac
                [ -z "${BASH_REMATCH[2]}" ] && i=$((i + 1))
                i=$((i + 1)); continue
            fi
            if [ "$t" = "--" ]; then
                i=$((i + 1))
                if [ -z "$host" ]; then host=${tok[$i]:-}; i=$((i + 1)); fi
                while [ $i -lt $n ]; do remote+=("${tok[$i]}"); i=$((i + 1)); done
                break
            fi
            case "$t" in
                --*) i=$((i + 1)); continue ;;          # mosh long options, e.g. --ssh=…
                -?*)
                    k=1; len=${#t}
                    while [ $k -lt $len ]; do
                        opt=${t:$k:1}
                        if [[ $argopts == *"$opt"* ]]; then
                            val=${t:$((k + 1))}
                            if [ -z "$val" ]; then i=$((i + 1)); val=${tok[$i]:-}; fi
                            case "$opt" in
                                D) dyn=1 ;;
                                L) fwd+=("$val") ;;
                                o)
                                    case "$(printf '%s' "$val" | tr '[:upper:]' '[:lower:]')" in
                                        dynamicforward*) dyn=1 ;;
                                        localforward*) fwd+=("$(printf '%s' "$val" | sed -E 's/^[^= ]+[= ]+//; s/[[:space:]]+/:/g')") ;;
                                    esac ;;
                            esac
                            break
                        fi
                        k=$((k + 1))
                    done
                    i=$((i + 1)); continue ;;
            esac
            if [ -z "$host" ]; then host=$t; i=$((i + 1)); continue; fi
        else
            if [[ $t =~ ^[0-9]*(<<-?|<>|<|>>|>|&>|>&|<&)(.*)$ ]]; then
                case "${BASH_REMATCH[1]}" in "<<"|"<<-") heredoc=1 ;; "<") stdin_file=1 ;; esac
                [ -z "${BASH_REMATCH[2]}" ] && i=$((i + 1))
                i=$((i + 1)); continue
            fi
        fi
        remote+=("$t")
        i=$((i + 1))
    done

    if [ $dyn = 1 ]; then
        ask "This opens a SOCKS tunnel through ${host:-the remote host} (ssh -D / DynamicForward). Anything sent through it leaves from that host's IP, outside this machine's agent-request-limiter. Ask the user before tunnelling through a server."
    fi
    local f fh
    for f in "${fwd[@]}"; do
        fh=$(printf '%s' "$f" | awk -F: '{ if (NF >= 3) print $(NF-1) }' | tr -d '[]')
        case "$fh" in ""|localhost|127.0.0.1|::1) ;; *)
            ask "This forwards a local port to $fh through ${host:-the remote host} (ssh -L). Those connections leave from that host's IP, outside this machine's agent-request-limiter. Ask the user before tunnelling through a server." ;;
        esac
    done

    local rtext="${remote[*]}" hit
    hit=$(net_hit "$rtext")
    if [ -n "$hit" ] && [ $stdin_file = 0 ] && [ "$sep" != "|" ] && safe_remote "$heredoc" "$rtext"; then
        hit=""                                     # inspection inside a container, read in full
    fi
    [ -n "$hit" ] && ask "This runs '$hit' on ${host:-a remote host} over ssh. $NET_REASON"

    # a remote shell with no -c reads its script from stdin. ssh joins its arguments with spaces and the
    # remote shell splits them again, so 'bash -s' as one argument is still bash with -s.
    local first bare=0
    first=$(printf '%s\n' "$rtext" | awk '{ print $1 }')
    first=${first##*/}
    if [ -z "$rtext" ]; then bare=1
    else
        case "$first" in sh|bash|zsh|dash|ksh|fish|python*|node|perl|ruby|php)
            bare=1
            [[ " $rtext " == *" -c "* ]] && bare=0 ;;
        esac
    fi
    if [ $bare = 1 ]; then
        if [ $heredoc = 1 ] && [ -n "$BODY" ]; then
            hit=$(net_hit "$BODY")
            [ -n "$hit" ] && ask "This feeds ${host:-a remote host} a script over ssh that runs '$hit'. $NET_REASON"
        elif [ $stdin_file = 1 ] || [ "$sep" = "|" ]; then
            ask "This feeds a shell on ${host:-a remote host} a script through stdin, which this hook cannot read. If that script makes requests, they leave from that host's IP, outside this machine's agent-request-limiter. Check what it runs before approving."
        fi
    fi
    return 0
}

SPLIT=$(printf '%s\n' "$COMMAND" | split_heredocs)
TEXT=$(printf '%s\n' "$SPLIT" | { grep -v "^$MARK" || true; })
BODY=$(printf '%s\n' "$SPLIT" | { grep "^$MARK" || true; } | sed "s/^$MARK//")
printf '%s\n' "$TEXT" | grep -Eq "$SSH_WORD_RE" || exit 0

while IFS=$'\t' read -r sep seg; do
    [ -n "$seg" ] && check_segment "$sep" "$seg"
done < <(printf '%s\n' "$TEXT" | split_segments)
exit 0
