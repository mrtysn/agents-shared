#!/bin/bash
# DESC: Run the refuse-requested-content-before-tool-call PreToolUse hook against fake transcripts
#
# Each case writes a small transcript, feeds the hook a PreToolUse payload that names it, and compares the exit
# code (0 = allowed, 2 = refused). The once-per-turn marker lives in a temp XDG_CACHE_HOME; nothing in ~/.claude
# or ~/.cache is touched.
#
# Bash, not zsh, to match the hook under test.

set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../refuse-requested-content-before-tool-call.sh"

VERBOSE=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) echo "usage: run-refuse-requested-content-before-tool-call.sh [-v]"; exit 0 ;;
        *) echo "unknown argument '$1'" >&2; exit 1 ;;
    esac
done

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export XDG_CACHE_HOME="$TMP/cache"

row() {  # type json-content [origin-kind] [time]
    jq -cn --arg t "$1" --argjson c "$2" --arg o "${3:-human}" --arg ts "${4:-2026-11-10T10:00:00.000Z}" \
        '{parentUuid: null, isSidechain: false, uuid: "u", timestamp: $ts, userType: "external", entrypoint: "cli",
          cwd: "/tmp/fixture", sessionId: "00000000-0000-4000-8000-000000000009", version: "2.1.299", type: $t}
         + (if $t == "user" then {origin: {kind: $o}} else {} end) + {message: {role: $t, content: $c}}'
}
prompt() { row user "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')" human "${2:-2026-11-10T10:00:00.000Z}"; }
say()    { row assistant "$(jq -cn --arg x "$1" '[{type: "text", text: $x}]')"; }
call()   { row assistant "$(jq -cn --arg i "$1" --arg n "$2" --argjson in "$3" '[{type: "tool_use", id: $i, name: $n, input: $in}]')"; }
result() { row user "$(jq -cn --arg i "$1" --arg x "$2" '[{type: "tool_result", tool_use_id: $i, content: $x}]')"; }
ask()    { call "$1" AskUserQuestion '{"questions":[{"question":"Next?","header":"Next","options":[{"label":"Go"},{"label":"Stop here"}]}]}'; }

CONTENT=$'Here are the names I suggested, oldest first: Aster, Birch, Cedar, Dune, Ember, Fable.'
LIST=$'- Aster\n- Birch'

total=0
failed=0

mk() { local f="$TMP/$1.jsonl"; shift; { for line in "$@"; do printf '%s\n' "$line"; done; } > "$f"; printf '%s' "$f"; }

# check NAME WANT TOOL TRANSCRIPT [SESSION] [KIND] [COMMAND]: each case gets its own session id so markers never collide.
# KIND (show, draft or work) says which refusal message a refusal must carry; COMMAND is a Bash call's command.
check() {
    local name=$1 want=$2 tool=$3 file=$4 session=${5:-case-$total} kind=${6:-show} cmd=${7:-} payload got=0 err remedy
    payload=$(jq -cn --arg t "$tool" --arg f "$file" --arg s "$session" --arg c "$cmd" '{tool_name:$t, session_id:$s, transcript_path:$f, tool_input:(if $c == "" then {} else {command:$c} end)}')
    err=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?
    total=$((total + 1))
    if [ "$got" = "$want" ]; then
        [ "$VERBOSE" = 1 ] && printf 'ok    %s\n' "$name"
        remedy='End this turn with the content as plain text and no tool call'
        [ "$kind" = draft ] && remedy='End this turn with the draft as the last text and no tool call'
        [ "$kind" = work ] && remedy='Deliver the requested content as text first'
        if [ "$want" = 2 ] && ! printf '%s' "$err" | grep -q "$remedy"; then
            failed=$((failed + 1)); printf 'FAIL  %s: refusal gives no remedy\n' "$name"
        fi
    else
        failed=$((failed + 1)); printf 'FAIL  %s: want exit %s, got %s\n' "$name" "$want" "$got"
    fi
}

f=$(mk list-ask "$(prompt 'list me all the names you suggested chronologically')" "$(say "$CONTENT")" "$(ask q1)")
check 'list prompt + text + AskUserQuestion refuses' 2 AskUserQuestion "$f" s-once
check 'second attempt in the same turn allows' 0 AskUserQuestion "$f" s-once
check 'another session, same transcript, refuses again' 2 AskUserQuestion "$f" s-other

f=$(mk skill "$(prompt 'give me the text already')" "$(say "$CONTENT")" "$(call t1 Skill '{"skill":"outstanding"}')")
check 'text + Skill refuses' 2 Skill "$f"
f=$(mk agent "$(prompt 'show me the plan')" "$(say "$CONTENT")" "$(call t1 Agent '{"description":"d","prompt":"p"}')")
check 'text + Agent refuses' 2 Agent "$f"
f=$(mk sendmsg "$(prompt 'repeat it for us')" "$(say "$CONTENT")" "$(call t1 SendMessage '{"to":"a","message":"m"}')")
check 'text + SendMessage refuses' 2 SendMessage "$f"
f=$(mk bash "$(prompt 'list me the names')" "$(say "$CONTENT")" "$(call t1 Bash '{"command":"ls"}')")
check 'text + Bash is not this hook'"'"'s tool' 0 Bash "$f"
check 'Read is not this hook'"'"'s tool' 0 Read "$f"

f=$(mk no-text "$(prompt 'list me all the names')" "$(ask q1)")
check 'no text before the call allows' 0 AskUserQuestion "$f"
f=$(mk short-text "$(prompt 'list me all the names')" "$(say 'Looking.')" "$(ask q1)")
check 'a short note before the call allows' 0 AskUserQuestion "$f"
f=$(mk short-list "$(prompt 'list me all the names')" "$(say "$LIST")" "$(ask q1)")
check 'a short list before the call refuses' 2 AskUserQuestion "$f"
f=$(mk table "$(prompt 'what is in the table?')" "$(say $'| a | b |\n|---|---|')" "$(ask q1)")
check 'a table before the call refuses' 2 AskUserQuestion "$f"

f=$(mk capability "$(prompt $'can the sessions app show a list of these and allow me to edit/add/remove?\nor maybe the other app\neither or?')" "$(say "$CONTENT")" "$(ask q1)")
check 'a capability question that says "show a list of these and allow me" allows' 0 AskUserQuestion "$f"
f=$(mk plain "$(prompt 'fix the build')" "$(say "$CONTENT")" "$(ask q1)")
check 'prompt that asks for no content allows' 0 AskUserQuestion "$f"
f=$(mk where "$(prompt 'where is the config file?')" "$(say "$CONTENT")" "$(ask q1)")
check '"where is" prompt refuses' 2 AskUserQuestion "$f"
f=$(mk allthe "$(prompt 'check all the logs')" "$(say "$CONTENT")" "$(ask q1)")
check '"all the" prompt refuses' 2 AskUserQuestion "$f"
f=$(mk word-boundary "$(prompt 'the playlist is listed in a spreadsheet')" "$(say "$CONTENT")" "$(ask q1)")
check 'word boundaries: "playlist", "listed", "spreadsheet" allow' 0 AskUserQuestion "$f"
f=$(mk slash "$(prompt $'<command-message>be-literal</command-message>\n<command-name>/be-literal</command-name>\n<command-args>list me them in a table</command-args>')" "$(say "$CONTENT")" "$(ask q1)")
check 'slash-command args count' 2 AskUserQuestion "$f"

f=$(mk interrupted "$(prompt 'list me all the names' 2026-11-10T10:00:00.000Z)" "$(say "$CONTENT")" "$(prompt '[Request interrupted by user]' 2026-11-10T10:01:00.000Z)" "$(say "$CONTENT")" "$(ask q1)")
check 'interrupted-request marker as last prompt allows' 0 AskUserQuestion "$f"

# Content delivered, then a question that was answered, then another call: the first call already had its turn.
f=$(mk second-call "$(prompt 'list me all the names')" "$(say "$CONTENT")" "$(ask q1)" "$(result q1 'Your questions have been answered: "Next?"="Go"')" "$(call t2 Skill '{"skill":"x"}')")
check 'a later call after an answered earlier one allows' 0 Skill "$f"
f=$(mk text-after-answer "$(prompt 'list me all the names')" "$(ask q1)" "$(result q1 'answered')" "$(say "$CONTENT")" "$(call t2 Skill '{"skill":"x"}')")
check 'text written after an answered call refuses' 2 Skill "$f"
f=$(mk earlier-turn "$(prompt 'list me all the names' 2026-11-10T09:00:00.000Z)" "$(say "$CONTENT")" "$(prompt 'fix the build' 2026-11-10T10:00:00.000Z)" "$(ask q1)")
check 'content from an earlier turn does not count' 0 AskUserQuestion "$f"

# A copy-ready draft (fenced block) written ahead of a tool call, whatever the prompt asked for.
DRAFT=$'Here is the reply:\n\n```\nHi Alex,\nthanks for the update.\n```'
f=$(mk draft-bash "$(prompt 'not a good way to put it i think')" "$(say "$DRAFT")" "$(call t1 Bash '{"command":"git commit"}')")
check 'draft + Bash refuses' 2 Bash "$f" s-draft-bash draft
check 'draft + Bash, second attempt in the same turn allows' 0 Bash "$f" s-draft-bash draft
f=$(mk draft-edit "$(prompt 'not a good way to put it i think')" "$(say "$DRAFT")" "$(call t1 Edit '{"file_path":"/x"}')")
check 'draft + Edit refuses' 2 Edit "$f" s-draft-edit draft
f=$(mk draft-write "$(prompt 'tidy that')" "$(say "$DRAFT")" "$(call t1 Write '{"file_path":"/x"}')")
check 'draft + Write refuses' 2 Write "$f" s-draft-write draft
f=$(mk draft-ask "$(prompt 'not a good way to put it i think')" "$(say "$DRAFT")" "$(ask q1)")
check 'draft + AskUserQuestion refuses with the draft message' 2 AskUserQuestion "$f" s-draft-ask draft
f=$(mk draft-skill "$(prompt 'tidy that')" "$(say "$DRAFT")" "$(call t1 Skill '{"skill":"x"}')")
check 'draft + Skill refuses' 2 Skill "$f" s-draft-skill draft
f=$(mk draft-agent "$(prompt 'tidy that')" "$(say "$DRAFT")" "$(call t1 Agent '{"description":"d","prompt":"p"}')")
check 'draft + Agent refuses' 2 Agent "$f" s-draft-agent draft
f=$(mk draft-sendmsg "$(prompt 'tidy that')" "$(say "$DRAFT")" "$(call t1 SendMessage '{"to":"a","message":"m"}')")
check 'draft + SendMessage refuses' 2 SendMessage "$f" s-draft-sendmsg draft
f=$(mk draft-read "$(prompt 'not a good way to put it i think')" "$(say "$DRAFT")" "$(call t1 Read '{"file_path":"/x"}')")
check 'draft + Read is not in the matcher list' 0 Read "$f" s-draft-read
f=$(mk plain-bash "$(prompt 'not a good way to put it i think')" "$(say 'Fixing the wording now, then committing it.')" "$(call t1 Bash '{"command":"git commit"}')")
check 'plain prose + Bash allows' 0 Bash "$f" s-plain-bash
f=$(mk draft-earlier "$(prompt 'draft the email' 2026-11-10T09:00:00.000Z)" "$(say "$DRAFT")" "$(prompt 'fix the build' 2026-11-10T10:00:00.000Z)" "$(call t1 Bash '{"command":"ls"}')")
check 'a fenced block from an earlier turn does not count' 0 Bash "$f" s-draft-earlier
f=$(mk draft-answered "$(prompt 'not a good way to put it i think')" "$(say "$DRAFT")" "$(call t1 Bash '{"command":"ls"}')" "$(result t1 'ok')" "$(call t2 Bash '{"command":"git commit"}')")
check 'a later Bash after an answered call allows' 0 Bash "$f" s-draft-answered
f=$(mk draft-after-answer "$(prompt 'not a good way to put it i think')" "$(call t1 Bash '{"command":"ls"}')" "$(result t1 'ok')" "$(say "$DRAFT")" "$(call t2 Bash '{"command":"git commit"}')")
check 'a draft written after an answered call refuses' 2 Bash "$f" s-draft-after-answer draft

# Work before content (trigger 3): the incident shape. "list me X and continue", then state-changing calls and a short
# announcement, with the list not yet written.
ANNOUNCE='Finishing the repo sync first, then the list.'
LONGLIST=$'Outstanding items:\n- Rebuild the index\n- Push the docs\n- Rotate the key'
f=$(mk work-incident-bash "$(prompt 'ok, list me /outstanding and continue')" "$(say "$ANNOUNCE")" "$(call t1 Bash '{"command":"git commit -m x"}')")
check 'show request + short announcement + git commit refuses' 2 Bash "$f" s-work-bash work 'git commit -m x'
check 'second state-changing call in the same turn allows' 0 Bash "$f" s-work-bash work 'git commit -m x'
f=$(mk work-incident-edit "$(prompt 'ok, list me /outstanding and continue')" "$(say "$ANNOUNCE")" "$(call t1 Edit '{"file_path":"/x"}')")
check 'show request + short announcement + Edit refuses' 2 Edit "$f" s-work-edit work
f=$(mk work-write "$(prompt 'show me the plan')" "$(call t1 Write '{"file_path":"/x"}')")
check 'show request + no text + Write refuses' 2 Write "$f" s-work-write work
f=$(mk work-readonly "$(prompt 'ok, list me /outstanding and continue')" "$(say "$ANNOUNCE")" "$(call t1 Bash '{"command":"git status"}')")
check 'show request + read-only Bash (git status) allows' 0 Bash "$f" s-work-ro1 work 'git status --short'
check 'read-only pipeline (git log | head, grep with a quoted pipe) allows' 0 Bash "$f" s-work-ro2 work "cd /tmp/x && git log --oneline | head -5; grep -n 'a|b' notes.md"
check 'sed without -i, 2>/dev/null and 2>&1 allow' 0 Bash "$f" s-work-ro3 work 'sed -n 1,5p f.md 2>/dev/null | cat 2>&1'
check 'redirection to a file refuses' 2 Bash "$f" s-work-redir work 'ls > out.txt'
check 'unknown command refuses' 2 Bash "$f" s-work-unk work 'project-lifecycle install'
check 'chained git write refuses' 2 Bash "$f" s-work-push work 'git status && git add -A'
check 'sed -i refuses' 2 Bash "$f" s-work-sedi work 'sed -i s/a/b/ f.md'
f=$(mk work-delivered "$(prompt 'ok, list me /outstanding and continue')" "$(say "$LONGLIST")" "$(call t1 Edit '{"file_path":"/x"}')")
check 'content delivered first (a list), then Edit allows' 0 Edit "$f" s-work-delivered work
f=$(mk work-delivered-long "$(prompt 'show me the plan')" "$(say "$CONTENT$CONTENT$CONTENT")" "$(call t1 Edit '{"file_path":"/x"}')")
check 'content delivered first (long text), then Edit allows' 0 Edit "$f" s-work-delivered2 work
f=$(mk work-no-show "$(prompt 'fix the build and continue')" "$(say "$ANNOUNCE")" "$(call t1 Edit '{"file_path":"/x"}')")
check 'continue alone (no show request) + Edit allows' 0 Edit "$f" s-work-noshow work
f=$(mk work-plain "$(prompt 'fix the build')" "$(call t1 Edit '{"file_path":"/x"}')")
check 'plain work prompt + Edit allows' 0 Edit "$f" s-work-plain work
f=$(mk work-earlier "$(prompt 'list me all the names' 2026-11-10T09:00:00.000Z)" "$(prompt 'fix the build' 2026-11-10T10:00:00.000Z)" "$(call t1 Edit '{"file_path":"/x"}')")
check 'show request from an earlier turn does not count' 0 Edit "$f" s-work-earlier work

# A sub-agent's call (agent_id in the input) is never refused, whoever wrote the draft in the parent's turn.
f=$(mk draft-subagent "$(prompt 'tidy that')" "$(say "$DRAFT")" "$(call t1 Agent '{"description":"d","prompt":"p"}')")
got=0; jq -cn --arg f "$f" '{tool_name:"Bash", session_id:"s-subagent", agent_id:"a1", transcript_path:$f, tool_input:{}}' | "$HOOK" >/dev/null 2>&1 || got=$?
total=$((total + 1))
if [ "$got" = 0 ]; then [ "$VERBOSE" = 1 ] && echo 'ok    sub-agent call allows'; else failed=$((failed + 1)); echo "FAIL  sub-agent call: got $got"; fi

# A draft that ended a finished reply was shown: what resumes the session afterwards closes it.
meta() { row user "$(jq -cn --arg x "$1" '$x')" "" "${2:-2026-11-10T10:00:30.000Z}" | jq -c '. + {isMeta: true} | del(.origin)'; }
f=$(mk draft-stophook "$(prompt 'not a good way to put it i think')" "$(say "$DRAFT")" "$(meta $'Stop hook feedback:\nYou are ending the turn idle')" "$(call t1 Bash '{"command":"git commit"}')")
check 'draft, Stop-hook feedback, then Bash allows' 0 Bash "$f" s-draft-stophook
f=$(mk draft-notify "$(prompt 'not a good way to put it i think')" "$(say "$DRAFT")" "$(row user "$(jq -cn '"<task-notification>\n<task-id>x</task-id>\n</task-notification>"')" "" | jq -c 'del(.origin)')" "$(call t1 Bash '{"command":"ls"}')")
check 'draft, task notification, then Bash allows' 0 Bash "$f" s-draft-notify
f=$(mk draft-stophook-newdraft "$(prompt 'tidy that')" "$(say "$DRAFT")" "$(meta 'Stop hook feedback: x')" "$(say "$DRAFT")" "$(call t1 Bash '{"command":"ls"}')")
check 'a new draft after the Stop-hook feedback refuses' 2 Bash "$f" s-draft-stophook-new draft

# Fail open.
check 'transcript missing allows' 0 AskUserQuestion "$TMP/nonexistent.jsonl"
printf 'not json at all\n' > "$TMP/garbage.jsonl"
check 'garbage transcript allows' 0 AskUserQuestion "$TMP/garbage.jsonl"
got=0; printf 'not json' | "$HOOK" >/dev/null 2>&1 || got=$?
total=$((total + 1))
if [ "$got" = 0 ]; then [ "$VERBOSE" = 1 ] && echo 'ok    garbage stdin allows'; else failed=$((failed + 1)); echo "FAIL  garbage stdin: got $got"; fi
got=0; jq -cn --arg f "$TMP/list-ask.jsonl" '{tool_name:"AskUserQuestion", transcript_path:$f}' | TRANSCRIPT_READER="$TMP/no-reader.py" "$HOOK" >/dev/null 2>&1 || got=$?
total=$((total + 1))
if [ "$got" = 0 ]; then [ "$VERBOSE" = 1 ] && echo 'ok    missing reader allows'; else failed=$((failed + 1)); echo "FAIL  missing reader: got $got"; fi
printf '#!/bin/sh\nexit 1\n' > "$TMP/bad-reader.py"; chmod +x "$TMP/bad-reader.py"
got=0; jq -cn --arg f "$TMP/list-ask.jsonl" '{tool_name:"AskUserQuestion", session_id:"s-badreader", transcript_path:$f}' | TRANSCRIPT_READER="$TMP/bad-reader.py" "$HOOK" >/dev/null 2>&1 || got=$?
total=$((total + 1))
if [ "$got" = 0 ]; then [ "$VERBOSE" = 1 ] && echo 'ok    failing reader allows'; else failed=$((failed + 1)); echo "FAIL  failing reader: got $got"; fi

# Late text: the content reaches the transcript file a moment after the hook starts, and is still caught.
f=$(mk late "$(prompt 'list me all the names')")
( sleep 0.5; say "$CONTENT" >> "$f" ) &
check 'content written a moment after the hook starts refuses' 2 AskUserQuestion "$f" s-late
wait

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = 0 ]
