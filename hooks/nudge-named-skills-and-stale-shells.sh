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
#    none. The lister costs about 100 ms, so its verdict is cached per session for 5 minutes.
#
# Both lines were part of the system-one prompt hook until 2026-10-15 and never used its model. They leave
# in one additionalContext, newline-joined, skill line first. Never blocks; fails open and silent on any
# missing directory or tool. The roster is cached for 10 minutes in $CLAUDE_CONFIG_DIR/nudge-named-skills/.
#
# Bash 3.2, like the hooks beside it. Cases: hooks/tests/nudge-named-skills-and-stale-shells-cases.tsv, run by
# hooks/tests/run-nudge-named-skills-and-stale-shells.sh.

set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# Single words that would collide with ordinary English if matched bare, but are skills worth routing to.
ALLOW_BARE="archify humanizer homelab-connect"
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
if [ -n "$SESSION" ] && [ -x "$SHELLS_LISTER" ]; then
    if [ -n "$(find "$SHELLS_CACHE" -mmin -5 2>/dev/null)" ]; then
        SHELLS_WARN=$(cat "$SHELLS_CACHE" 2>/dev/null)
    else
        STALE=$("$SHELLS_LISTER" --session "$SESSION" --older-than 60 2>/dev/null)
        if [ -n "$STALE" ]; then
            # Top-level lines only: the lister indents a shell's children.
            STALE_N=$(printf '%s\n' "$STALE" | grep -c '^[^ ]')
            STALE_FIRST=$(printf '%s\n' "$STALE" | head -1 | cut -c1-120)
            SHELLS_WARN="This session has $STALE_N background shell(s) running over 60 minutes (first: $STALE_FIRST). Check whether each is still needed and stop the rest."
        fi
        printf '%s' "$SHELLS_WARN" > "$SHELLS_CACHE" 2>/dev/null
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
ROSTER_CACHE="$STATE_DIR/roster.cache"
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
    RNAMES=""
    for f in "$CONFIG_DIR"/skills/*/SKILL.md; do
        [ -e "$f" ] || continue
        d="${f%/SKILL.md}"
        RNAMES="$RNAMES${d##*/}
"
    done
    for f in "$CONFIG_DIR"/commands/*.md; do
        [ -e "$f" ] || continue
        b="${f##*/}"
        RNAMES="$RNAMES${b%.md}
"
    done
    ROSTER=$(printf '%s' "$RNAMES" | tr 'A-Z' 'a-z' | sort -u 2>/dev/null)
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
MATCHED=$(printf '%s\n' "$ROSTER" | awk -v prompt="$PROMPT_FLAT" -v allow="$ALLOW_BARE" '
    BEGIN {
        lp = tolower(prompt)
        n = split(lp, toks, /[ \t]+/)
        nallow = split(allow, allowarr, " ")
        for (i = 1; i <= nallow; i++) if (allowarr[i] != "") allowset[allowarr[i]] = 1
    }
    { name = tolower($0); if (name != "") roster[name] = 1 }
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
            if (!(name in roster)) continue
            if (is_slash) { matched[name] = 1; continue }
            if (index(name, "-") > 0 || (name in allowset)) matched[name] = 1
        }
        out = ""
        for (m in matched) out = out (out == "" ? "" : "\n") m
        print out
    }' 2>/dev/null)
[ -n "$MATCHED" ] || emit ""

LIST=""
NCOUNT=0
while IFS= read -r nm; do
    [ -n "$nm" ] || continue
    NCOUNT=$((NCOUNT + 1))
    LIST="${LIST:+$LIST, }/$nm"
done <<<"$MATCHED"
if [ "$NCOUNT" -eq 1 ]; then
    emit "This prompt names the skill $LIST; invoke it with the Skill tool instead of doing the work by hand."
fi
emit "This prompt names the skills $LIST; invoke them with the Skill tool instead of doing the work by hand."
