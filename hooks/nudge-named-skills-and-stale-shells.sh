#!/bin/bash
# UserPromptSubmit hook: two plain nudges added to the model's context, no model call.
#
# 1. Named skill. A typed prompt that names a skill or command from the roster ("/search-history" anywhere,
#    or a bare hyphenated name such as stg-msg-cmt, or one of ALLOW_BARE below) gets one line telling the
#    agent to invoke it with the Skill tool instead of doing the work by hand. The roster is the top-level
#    skills ($CLAUDE_CONFIG_DIR/skills/*/SKILL.md) and commands ($CLAUDE_CONFIG_DIR/commands/*.md); a plugin
#    group's sub-skills are not in it. Skipped for a slash command itself, for a prompt under 3 words, for
#    text the harness relays between turns (subagent hand-backs, cross-session messages, task notifications,
#    system reminders), and for a name followed by a `--flag` (pasted shell output, not a request).
# 2. Stale background shells. A Stop hook cannot reach the model without blocking, so the warning rides on
#    the next prompt: this session's background shells running over 60 minutes, from
#    scripts/list-session-background-shells.sh (SESSION_SHELLS_LISTER overrides it), as one line. Silent when
#    none. The lister costs 0.5-0.9 s cold (it snapshots every process and listening socket), and this
#    hook's limit in settings.json is 3 s, so the prompt never waits on it: the hook prints the cached
#    verdict whatever its age and refreshes a cache older than 5 minutes in a detached process. A
#    session's first prompt carries no shells line. A prompt once timed out here (2026-11-10) because the
#    cache was written only after the lister returned, so a killed run left the next prompt cold again.
#
# Both lines were part of the system-one prompt hook until 2026-10-15 and never used its model. They leave
# in one additionalContext, newline-joined, skill line first. Never blocks; fails open and silent on any
# missing directory or tool. The roster is cached for 10 minutes in $CLAUDE_CONFIG_DIR/nudge-named-skills/.
# Its lines carry a kind read from each file's frontmatter: disable-model-invocation: true marks a user-only
# name, which the Skill tool refuses and the agent's skill list omits (2026-11-13: /refocus was called
# "not installed" after a nudge said to invoke it). A typed /name the roster lacks gets a "look before you
# say it is missing" line; paths (/usr/bin) and system directory names are not reported.
#
# Bash 3.2, like the hooks beside it. Cases: hooks/tests/nudge-named-skills-and-stale-shells-cases.tsv, run by
# hooks/tests/run-nudge-named-skills-and-stale-shells.sh.

set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Single words that would collide with ordinary English if matched bare, but are skills worth routing to.
ALLOW_BARE="archify humanizer homelab-connect"
# Top-level directories that a typed /name is a path to, not a command (never reported as missing).
NOT_COMMANDS="usr bin sbin etc tmp var opt home dev lib users private volumes system library applications proc mnt srv root"
ROSTER_TTL=600
SKIP_MARKERS='Another Claude session sent a message
[Subagent hand-back]
[SYSTEM NOTIFICATION
<agent-message
<cross-session-message
[Cross-session
<system-reminder>
<task-notification'

INPUT=$(cat)
PROMPT=$(printf '%s' "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)
[ -n "$PROMPT" ] || exit 0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
STATE_DIR="$CONFIG_DIR/nudge-named-skills"

# --- stale background shells ---
SHELLS_WARN=""
SHELLS_LISTER="${SESSION_SHELLS_LISTER:-$HERE/../scripts/list-session-background-shells.sh}"
SHELLS_CACHE="${TMPDIR:-/tmp}/session-shells-warn-$(printf '%s' "$SESSION" | tr -dc 'A-Za-z0-9_-')"
SHELLS_LOCK="$SHELLS_CACHE.refreshing"
refresh_shells() { # runs detached from the prompt: list the shells, then replace the cache in one move
    local stale n first warn=""
    stale=$("$SHELLS_LISTER" --session "$SESSION" --older-than 60 2>/dev/null)
    if [ -n "$stale" ]; then
        # Top-level lines only: the lister indents a shell's children.
        n=$(printf '%s\n' "$stale" | grep -c '^[^ ]')
        first=$(printf '%s\n' "$stale" | head -1 | cut -c1-120)
        warn="This session has $n background shell(s) running over 60 minutes (first: $first). Check whether each is still needed and stop the rest."
    fi
    printf '%s' "$warn" > "$SHELLS_CACHE.tmp.$$" 2>/dev/null && mv "$SHELLS_CACHE.tmp.$$" "$SHELLS_CACHE" 2>/dev/null
    rmdir "$SHELLS_LOCK" 2>/dev/null
}
if [ -n "$SESSION" ] && [ -x "$SHELLS_LISTER" ]; then
    # The prompt never waits on the lister (0.5-0.9 s cold, and the hook's limit is 3 s): it uses the
    # cached verdict whatever its age, and a cache older than 5 minutes (or none) is refreshed in a
    # detached process. A session's first prompt therefore carries no shells line; the next one does.
    [ -r "$SHELLS_CACHE" ] && SHELLS_WARN=$(cat "$SHELLS_CACHE" 2>/dev/null)
    if [ -z "$(find "$SHELLS_CACHE" -mmin -5 2>/dev/null)" ]; then
        # one refresh at a time; a lock older than 2 minutes belongs to a killed refresh
        [ -n "$(find "$SHELLS_LOCK" -mmin +2 2>/dev/null)" ] && rmdir "$SHELLS_LOCK" 2>/dev/null
        if mkdir "$SHELLS_LOCK" 2>/dev/null; then
            (refresh_shells) </dev/null >/dev/null 2>&1 &
        fi
    fi
fi

emit() { # skill line (may be empty); adds the shells line
    local out="$1"
    if [ -n "$SHELLS_WARN" ]; then
        out="${out:+$out
}$SHELLS_WARN"
    fi
    [ -n "$out" ] || exit 0
    jq -cn --arg c "$out" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
    exit 0
}

# --- relayed text, slash commands and short prompts get no skill line ---
while IFS= read -r marker; do
    [ -n "$marker" ] || continue
    case "$PROMPT" in
        *"$marker"*) emit "" ;;
    esac
done <<<"$SKIP_MARKERS"
case "$PROMPT" in
    /*) emit "" ;;
esac
WORDCOUNT=$(printf '%s' "$PROMPT" | wc -w | tr -d ' ')
[ "${WORDCOUNT:-0}" -ge 3 ] 2>/dev/null || emit ""

# --- roster, cached ---
# roster.v2.cache: lines are name<TAB>kind<TAB>path (kind user = disable-model-invocation: true). The v1 file
# held bare names and is never read, so an old cache cannot be mistaken for a roster without the mark.
ROSTER_CACHE="$STATE_DIR/roster.v2.cache"
NOW_EPOCH=$(date +%s 2>/dev/null)
ROSTER=""
if [ -n "$NOW_EPOCH" ] && [ -r "$ROSTER_CACHE" ]; then
    # date -r <file> +%s, not stat -f/-c: BSD and GNU date agree on it, the two stats do not.
    CACHE_MTIME=$(date -r "$ROSTER_CACHE" +%s 2>/dev/null)
    if [ -n "$CACHE_MTIME" ] && [ $((NOW_EPOCH - CACHE_MTIME)) -lt "$ROSTER_TTL" ] 2>/dev/null; then
        ROSTER=$(cat "$ROSTER_CACHE" 2>/dev/null)
    fi
fi
if [ -z "$ROSTER" ]; then
    TAB=$(printf '\t')
    RNAMES=""
    # kind_of FILE: "user" when its frontmatter says disable-model-invocation: true, else "ok"
    kind_of() {
        awk 'NR == 1 { if ($0 !~ /^---[ \t\r]*$/) exit; next }
             /^---[ \t\r]*$/ { exit }
             tolower($0) ~ /^disable-model-invocation:[ \t]*["\x27]?true["\x27]?[ \t\r]*$/ { f = 1; exit }
             END { print (f ? "user" : "ok") }' "$1" 2>/dev/null
    }
    for f in "$CONFIG_DIR"/skills/*/SKILL.md; do
        [ -e "$f" ] || continue
        d="${f%/SKILL.md}"
        RNAMES="$RNAMES${d##*/}$TAB$(kind_of "$f")$TAB$f
"
    done
    for f in "$CONFIG_DIR"/commands/*.md; do
        [ -e "$f" ] || continue
        b="${f##*/}"
        RNAMES="$RNAMES${b%.md}$TAB$(kind_of "$f")$TAB$f
"
    done
    ROSTER=$(printf '%s' "$RNAMES" | sort -u -t "$TAB" -k1,1f 2>/dev/null)
    if [ -n "$ROSTER" ]; then
        mkdir -p "$STATE_DIR" 2>/dev/null
        printf '%s\n' "$ROSTER" >"$ROSTER_CACHE.tmp.$$" 2>/dev/null \
            && mv "$ROSTER_CACHE.tmp.$$" "$ROSTER_CACHE" 2>/dev/null
    fi
fi
[ -n "$ROSTER" ] || emit ""

# --- match ---
# Newlines flattened to spaces before -v: this platform's awk (BWK "one true awk") errors on a raw newline
# inside a -v value, and the matcher splits on whitespace anyway.
PROMPT_FLAT=$(printf '%s' "$PROMPT" | tr '\n\t' '  ')
MATCHED=$(printf '%s\n' "$ROSTER" | awk -F '\t' -v prompt="$PROMPT_FLAT" -v allow="$ALLOW_BARE" -v notcmd="$NOT_COMMANDS" '
    BEGIN {
        lp = tolower(prompt)
        n = split(lp, toks, /[ \t]+/)
        nallow = split(allow, allowarr, " ")
        for (i = 1; i <= nallow; i++) if (allowarr[i] != "") allowset[allowarr[i]] = 1
        nnot = split(notcmd, notarr, " ")
        for (i = 1; i <= nnot; i++) if (notarr[i] != "") notset[notarr[i]] = 1
    }
    { name = tolower($1); if (name != "") { roster[name] = 1; kind[name] = $2; path[name] = $3 } }
    END {
        for (i = 1; i <= n; i++) {
            tok = toks[i]
            gsub(/^["\x27(\[{<.,!?:;*`]+|["\x27)\]}>.,!?:;*`]+$/, "", tok)
            if (tok == "") continue
            nextraw = (i < n) ? toks[i + 1] : ""
            if (index(nextraw, "--") == 1) continue
            name = tok
            is_slash = 0
            if (substr(tok, 1, 1) == "/") { name = substr(tok, 2); is_slash = 1 }
            if (!(name in roster)) {
                # A /name typed at the start of a word that the roster lacks. A second slash (a path),
                # a known system directory or a non-command shape is not a command name.
                if (is_slash && name ~ /^[a-z][a-z0-9-]*$/ && !(name in notset)) unknown[name] = 1
                continue
            }
            if (is_slash) { matched[name] = 1; continue }
            if (index(name, "-") > 0 || (name in allowset)) matched[name] = 1
        }
        out = ""
        for (m in matched) out = out (out == "" ? "" : "\n") m "\t" kind[m] "\t" path[m]
        for (m in unknown) out = out (out == "" ? "" : "\n") m "\tunknown\t"
        print out
    }' 2>/dev/null)
[ -n "$MATCHED" ] || emit ""

LIST=""
NCOUNT=0
USERLINES=""
UNKLINES=""
TAB=$(printf '\t')
while IFS="$TAB" read -r nm kind path; do
    [ -n "$nm" ] || continue
    case "$kind" in
        user)
            shown="$path"
            case "$path" in "$HOME"/*) shown="~${path#"$HOME"}" ;; esac
            USERLINES="${USERLINES:+$USERLINES
}This prompt names /$nm, a user-only command ($shown, disable-model-invocation): it is installed, but the Skill tool refuses it and the skill list leaves it out. Ask the user to type /$nm themselves; never call it uninstalled."
            ;;
        unknown)
            UNKLINES="${UNKLINES:+$UNKLINES
}This prompt names /$nm, which the hook's roster does not hold. Before saying it is not installed, look in ~/.claude/commands, ~/.claude/skills and installed plugins, then call the Skill tool."
            ;;
        *)
            NCOUNT=$((NCOUNT + 1))
            LIST="${LIST:+$LIST, }/$nm"
            ;;
    esac
done <<<"$MATCHED"
OUT=""
if [ "$NCOUNT" -eq 1 ]; then
    OUT="This prompt names the skill $LIST; invoke it with the Skill tool instead of doing the work by hand."
elif [ "$NCOUNT" -gt 1 ]; then
    OUT="This prompt names the skills $LIST; invoke them with the Skill tool instead of doing the work by hand."
fi
if [ -n "$OUT" ]; then
    OUT="$OUT Its absence from your skill list does not mean it is missing: the list leaves out on-demand and user-only entries. Call the Skill tool, and if it refuses, ask the user to type it."
fi
for part in "$USERLINES" "$UNKLINES"; do
    [ -n "$part" ] && OUT="${OUT:+$OUT
}$part"
done
emit "$OUT"
