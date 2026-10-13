#!/bin/bash
# PreToolUse hook (Bash, Write): once per session, tells the agent that Claude Code transcripts have a shared reader
#
# The failure this exists to prevent: an agent asked to go over the user's chat logs writes its own jsonl
# parser — an inline `python3 - <<EOF … json.loads …`, a `jq` over ~/.claude/projects, or a script written
# to a file and run later. Over 60 days (to 2026-10-13) that was 303 such Bash calls in 66 sessions, plus
# 39 Write calls, while scripts/extract-session-text.py already reads one session or all of them as text or
# JSON rows. See claude/rules/never-hand-roll-a-transcript-parser.md and the mine-chat-logs skill.
#
# Never blocks and never asks. It adds one note to the model's context (hookSpecificOutput.additionalContext,
# the only form a PreToolUse hook's text reaches the model in), and the command or write goes ahead. The note
# fires at most once per session: a state file named for the session id sits in
# $CLAUDE_CONFIG_DIR/nudge-transcript-parsers/, files older than 14 days are pruned. A session that builds
# a transcript tool gets one line, not one per call; there is no exemption by repo.
#
# Fires on:
#   Bash  a command that names a Claude projects folder (…/.claude/projects, ~/.claude*/projects,
#         $CLAUDE_CONFIG_DIR/…/projects) AND an interpreter or JSON tool (python, jq, node, ruby, perl,
#         json.loads, JSON.parse) AND none of the shared readers below.
#   Write content that names a Claude projects folder AND parses JSON (json.loads, import json, JSON.parse,
#         jq). This catches a parser written to a file and run later as `python3 /tmp/x.py`.
# Plain listing and grep (`ls ~/.claude/projects`, `grep -c x file.jsonl`) pass. Not covered: a path built
# from pieces, and a script written by a tool other than Write or Bash.
#
# Bash, not zsh, to match the hooks beside it. Written for bash 3.2 (macOS /bin/bash).

set -e

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')
SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty')

PATH_RE='claude[A-Za-z0-9_.*-]*/projects|CLAUDE_CONFIG_DIR[^[:space:]]*/projects'
RUN_RE='(^|[^[:alnum:]_.-])(python[0-9.]*|jq|node|deno|bun|ruby|perl)([^[:alnum:]_.-]|$)|json\.loads|JSON\.parse'
JSON_RE='json\.loads|json\.load\(|import json|JSON\.parse|(^|[^[:alnum:]_.-])jq([^[:alnum:]_.-]|$)'
SHARED_RE='extract-session-text|search-history|find-repeated-user-prompts|find-interrupted-responses|find-listed-unasked|find-invisible-output|recent-sessions|blame-session|iterm-revive|report-subagent-token-use|review-ssh-guard-asks|usage-survey|command-moments-survey|count-manual-commit|survey-remote-commands|memory-audit|transcript_items'

case "$TOOL" in
    Bash)
        TEXT=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
        [ -z "$TEXT" ] && exit 0
        printf '%s' "$TEXT" | grep -Eq "$PATH_RE" || exit 0
        printf '%s' "$TEXT" | grep -Eq "$RUN_RE" || exit 0
        printf '%s' "$TEXT" | grep -Eq "$SHARED_RE" && exit 0
        ;;
    Write)
        TEXT=$(printf '%s' "$INPUT" | jq -r '.tool_input.content // empty')
        [ -z "$TEXT" ] && exit 0
        printf '%s' "$TEXT" | grep -Eq "$PATH_RE" || exit 0
        printf '%s' "$TEXT" | grep -Eq "$JSON_RE" || exit 0
        ;;
    *) exit 0 ;;
esac

STATE=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/nudge-transcript-parsers
MARK=$STATE/${SESSION_ID:-no-session}
if [ -f "$MARK" ]; then
    exit 0
fi
{
    mkdir -p "$STATE" &&
    find "$STATE" -type f -mtime +14 -delete &&
    : > "$MARK"
} 2>/dev/null || true

NOTE='Reading Claude Code transcripts: a shared reader exists, and a hand-written jsonl parser is what this note is here to prevent. One session: $AGENTS_SHARED/scripts/extract-session-text.py <session-id> --kinds user,assistant,calls,tools [--grep REGEX] [--around YYYY-MM-DDTHH:MM]. Many sessions: extract-session-text.py --all --days N [--project TEXT] [--session-mentions REGEX] [--kinds ...] --json [--next-user], then jq over the rows. Find a session by keyword: search-history.py. The mine-chat-logs skill has the whole procedure (candidates, small read-only sub-agents to classify, report). Your command was not blocked; this note appears once per session.'
jq -n --arg n "$NOTE" '{hookSpecificOutput: {hookEventName: "PreToolUse", additionalContext: $n}}'
