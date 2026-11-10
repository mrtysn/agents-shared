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

# check NAME WANT TOOL TRANSCRIPT [SESSION]: each case gets its own session id so markers never collide.
check() {
    local name=$1 want=$2 tool=$3 file=$4 session=${5:-case-$total} payload got=0 err
    payload=$(jq -cn --arg t "$tool" --arg f "$file" --arg s "$session" '{tool_name:$t, session_id:$s, transcript_path:$f, tool_input:{}}')
    err=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?
    total=$((total + 1))
    if [ "$got" = "$want" ]; then
        [ "$VERBOSE" = 1 ] && printf 'ok    %s\n' "$name"
        if [ "$want" = 2 ] && ! printf '%s' "$err" | grep -q 'End this turn with the content as plain text and no tool call'; then
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
