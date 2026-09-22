#!/bin/bash
# PreToolUse hook: code that can reach the network, run on a remote host over ssh, needs the user's yes
#
# The failure this exists to prevent: testing a scraper by running it on a server. Every request it
# makes leaves from that server's IP — outside this machine's agent-request-limiter, uncounted — and
# a rate limit or ban lands on a production box. On 2026-09-22 an agent sent ~45 requests to Google
# from node01 this way, via `ssh node01 'docker exec funds-poller python …'`, while debugging code
# that could have been tested locally against one saved response.
#
# Asks (never blocks) when an ssh command's remote part runs something network-capable:
#   docker exec / docker run / docker compose exec|run / kubectl exec — code inside a container
#   curl, wget, nc, ncat, socat, telnet, http(ie), aria2c, lynx, w3m
#   interpreters and package managers: python, node, deno, bun, ruby, perl, php, uv, pip, npm, npx
# Plain inspection over ssh (ls, cat, docker ps, docker logs, systemctl, journalctl) passes, and so
# do scp and rsync, which copy files rather than run code.
#
# Not covered: ssh inside a script file. Same carve-out as require-absolute-rm.sh.
#
# Bash, not zsh, to match the hooks beside it and to keep working on Linux boxes that sync
# agents-shared without /bin/zsh.

set -e

INPUT=$(cat)
COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
[ -z "$COMMAND" ] && exit 0

# Heredoc bodies are data — commit messages, generated files — and routinely mention ssh and curl.
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

TEXT=$(printf '%s\n' "$COMMAND" | strip_heredocs | tr '\n' ' ')

# ssh as a command word: at the start, or after a separator, a subshell, or command substitution.
# ssh-keygen, ssh-add and git's ssh URLs are not matched (the next character is not a blank).
SSH_RE='(^|[;&|({`[:space:]]|\$\()ssh[[:space:]]'
[[ $TEXT =~ $SSH_RE ]] || exit 0
# everything after the first ssh: the remote part, plus any local commands chained after it
REMOTE=${TEXT#*"${BASH_REMATCH[0]}"}

NET_RE='(^|[^[:alnum:]_.-])(docker([[:space:]]+compose)?[[:space:]]+(exec|run)|kubectl[[:space:]]+exec|curl|wget|nc|ncat|socat|telnet|https?|httpie|aria2c|lynx|w3m|python[0-9.]*|node|deno|bun|ruby|perl|php|uv|pip[0-9.]*|npm|npx)([^[:alnum:]_.-]|$)'
HIT=$(printf '%s' "$REMOTE" | grep -Eo "$NET_RE" | head -1 | sed -E 's/^[^[:alnum:]]+//; s/[^[:alnum:]]+$//')
[ -z "$HIT" ] && exit 0

REASON="This runs '$HIT' on a remote host over ssh. Whatever it fetches leaves from that host's IP, outside this machine's agent-request-limiter and uncounted, and a rate limit or ban lands on that server. To test code that makes requests: fetch once locally, save the response, and test against the saved copy. Run network code on a server only when the user asked for exactly that."

jq -n --arg r "$REASON" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $r}}'
exit 0
