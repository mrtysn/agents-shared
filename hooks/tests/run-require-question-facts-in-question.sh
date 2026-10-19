#!/bin/bash
# DESC: Run the require-question-facts-in-question PreToolUse hook against fake transcripts
#
# Each case writes a small transcript into a temp dir, feeds the hook a PreToolUse payload that
# names it, and compares the exit code (0 = allowed, 2 = refused). Nothing in ~/.claude is read.
#
# Bash, not zsh, to match the hook under test.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../require-question-facts-in-question.sh"

VERBOSE=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        -h|--help) echo "usage: run-require-question-facts-in-question.sh [-v]"; exit 0 ;;
        *) echo "unknown argument '$1'" >&2; exit 1 ;;
    esac
done

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Transcript entries, one JSON object per line.
u()     { jq -cn --arg t "$1" '{type:"user", timestamp:"2026-10-18T10:00:00Z", message:{content:$t}}'; }
think() { jq -cn '{type:"assistant", timestamp:"2026-10-18T10:00:01Z", message:{content:[{type:"thinking", thinking:"a table"}]}}'; }
say()   { jq -cn --arg t "$1" '{type:"assistant", timestamp:"2026-10-18T10:00:02Z", message:{content:[{type:"text", text:$t}]}}'; }
ask()   { jq -cn --arg id "$1" '{type:"assistant", timestamp:"2026-10-18T10:00:03Z", message:{content:[{type:"tool_use", id:$id, name:"AskUserQuestion", input:{questions:[{question:"q"}]}}]}}'; }
answer() { jq -cn --arg id "$1" --arg t "$2" '{type:"user", timestamp:"2026-10-18T10:00:04Z", message:{content:[{type:"tool_result", tool_use_id:$id, content:$t}]}}'; }

total=0
failed=0

# check NAME WANT QUESTION TRANSCRIPT-FILE
check() {
    local name=$1 want=$2 question=$3 file=$4 payload got=0 err
    payload=$(jq -cn --arg q "$question" --arg f "$file" \
        '{tool_name:"AskUserQuestion", transcript_path:$f, tool_input:{questions:[{question:$q, header:"h", options:[]}]}}')
    err=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?
    total=$((total + 1))
    if [ "$got" = "$want" ]; then
        [ "$VERBOSE" = 1 ] && printf 'ok    %s\n' "$name"
        if [ "$want" = 2 ] && ! printf '%s' "$err" | grep -Eq 'put the facts inside the question|Use the absolute path in the question'; then
            failed=$((failed + 1)); printf 'FAIL  %s: refusal gives no remedy\n' "$name"
        fi
    else
        failed=$((failed + 1)); printf 'FAIL  %s: want exit %s, got %s\n' "$name" "$want" "$got"
    fi
}

mk() { local f="$TMP/$1.jsonl"; shift; { for line in "$@"; do printf '%s\n' "$line"; done; } > "$f"; printf '%s' "$f"; }

ABOVE='Create the 15 logins in the table above?'

f=$(mk silent "$(u 'go')" "$(think)")
check 'no text + "above" refuses' 2 "$ABOVE" "$f"
check 'no text + "Above" capitalised refuses' 2 'Above all, create the logins?' "$f"
check 'no text + "the table" refuses' 2 'Which rows of the table should I keep?' "$f"
check 'no text + "as listed" refuses' 2 'Install the tools as listed?' "$f"
check 'no text, no pointer allows' 0 'Create the 15 logins on node01?' "$f"
check 'word boundary: "aboveboard" and "the tabletop" allow' 0 'Is the aboveboard plan for the tabletop ok?' "$f"

f=$(mk spoke "$(u 'go')" "$(think)" "$(say 'Here is the table: ...')")
check 'text + "above" allows' 0 "$ABOVE" "$f"

f=$(mk blank "$(u 'go')" "$(say '   ')")
check 'whitespace-only text counts as none' 2 "$ABOVE" "$f"

# The real failure: text came before an earlier question, the typed answer asked for output,
# and the next question points at it with no text sent in between.
f=$(mk after-answer "$(u 'go')" "$(say 'Wiring all projects needs 15 logins.')" "$(ask q1)" "$(answer q1 'The user answered: "q"="list me them in a table"')" "$(think)")
check 'text before an answered question, none after, refuses' 2 "$ABOVE" "$f"

f=$(mk text-after-answer "$(u 'go')" "$(ask q1)" "$(answer q1 'list me them in a table')" "$(say 'The table: ...')")
check 'text sent after the answer allows' 0 "$ABOVE" "$f"

f=$(mk earlier-turn "$(u 'first')" "$(say 'old text')" "$(u 'second')" "$(think)")
check 'text from an earlier turn does not count' 2 "$ABOVE" "$f"

# Second trigger: a file path in the question needs its absolute form in visible text.
ABS=/Users/x/repo/games/a/b.html
f=$(mk path-silent "$(u 'go')" "$(think)")
check 'path in question, no text refuses' 2 "Which of $ABS reads better?" "$f"
f=$(mk path-rel "$(u 'go')" "$(say "Report: $ABS")")
check 'relative path in question, absolute in prose refuses' 2 'Which of games/a/b.html reads better?' "$f"
check 'absolute path in question and in prose allows' 0 "Which of $ABS reads better?" "$f"
f=$(mk path-notes "$(u 'go')" "$(say 'Working on it, one moment.')")
check 'absolute path in question, prose without it refuses' 2 "Which of $ABS reads better?" "$f"
f=$(mk path-earlier "$(u 'first')" "$(say "Report: $ABS")" "$(u 'second')" "$(say 'noted')")
check 'absolute path sent in an earlier turn refuses' 2 "Which of $ABS reads better?" "$f"
f=$(mk path-none "$(u 'go')" "$(think)")
check 'no path, no pointer allows' 0 'Which design reads better?' "$f"
check 'URL is not a file path' 0 'Is https://x.com/a.html the right source?' "$f"
check 'a name without a slash is not a path' 0 'Is report.html the right name?' "$f"
f=$(mk path-text-prose "$(u 'go')" "$(say "Saved to $ABS.")")
check 'absolute path followed by a period in prose allows' 0 "Which of $ABS reads better?" "$f"

# Third trigger: letter labels coined in the session, checked across the question and its options.
# checkopts NAME WANT QUESTION OPTION-LABEL OPTION-DESCRIPTION
checkopts() {
    local name=$1 want=$2 payload got=0 err
    payload=$(jq -cn --arg q "$3" --arg l "$4" --arg d "$5" --arg f "$TMP/none.jsonl" \
        '{tool_name:"AskUserQuestion", transcript_path:$f, tool_input:{questions:[{question:$q, header:"h", options:[{label:$l, description:$d}]}]}}')
    err=$(printf '%s' "$payload" | "$HOOK" 2>&1 >/dev/null) || got=$?
    total=$((total + 1))
    if [ "$got" = "$want" ]; then
        [ "$VERBOSE" = 1 ] && printf 'ok    %s\n' "$name"
        if [ "$want" = 2 ] && ! printf '%s' "$err" | grep -q 'put the facts inside the question'; then
            failed=$((failed + 1)); printf 'FAIL  %s: refusal gives no remedy\n' "$name"
        fi
    else
        failed=$((failed + 1)); printf 'FAIL  %s: want exit %s, got %s\n' "$name" "$want" "$got"
    fi
}
# The real failure (2026-10-19, social-content): letters from a decision form reused in a question.
checkopts 'undefined "pair A" and "B or C" refuses' 2 'The reel uses chibi pair A. Render now?' 'Switch to B or C first' 'Rebuild with the bear and bunny or the mochi pair'
checkopts 'undefined "option B" in a description refuses' 2 'Which layout?' 'Grid' 'Same as option B but wider'
checkopts 'letters defined with a colon allow' 0 'A: two people, B: bear and bunny. Which pair?' 'A or B' 'pick one'
checkopts 'letters defined with parentheses allow' 0 'Keep pair A (two people) or switch?' 'Keep pair A' 'as built'
checkopts 'no letter labels allow' 0 'Render the reel now?' 'Render now' 'make the upload file'
checkopts 'a lone capital in prose allows' 0 'Should I add a CTA at the end?' 'Add a CTA' 'one line, A1 size'

# Fail open.
check 'transcript missing allows' 0 "$ABOVE" "$TMP/nonexistent.jsonl"
payload=$(jq -cn --arg q "$ABOVE" '{tool_name:"AskUserQuestion", tool_input:{questions:[{question:$q}]}}')
got=0; printf '%s' "$payload" | "$HOOK" >/dev/null 2>&1 || got=$?
total=$((total + 1))
if [ "$got" = 0 ]; then [ "$VERBOSE" = 1 ] && echo 'ok    no transcript_path allows'; else failed=$((failed + 1)); echo "FAIL  no transcript_path: got $got"; fi
got=0; printf 'not json' | "$HOOK" >/dev/null 2>&1 || got=$?
total=$((total + 1))
if [ "$got" = 0 ]; then [ "$VERBOSE" = 1 ] && echo 'ok    garbage stdin allows'; else failed=$((failed + 1)); echo "FAIL  garbage stdin: got $got"; fi

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = 0 ]
