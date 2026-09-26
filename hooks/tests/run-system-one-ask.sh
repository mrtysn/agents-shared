#!/bin/bash
# DESC: Run the system-one-ask PreToolUse hook against its case file structurally (exit code, shadow-mode silence, latency, one log line per question)
#
# Bash, to match the hook under test and the runners beside it. This checks
# the hook's plumbing (exit code, no stdout in shadow mode, under the latency
# budget, one shadow-log line per question of the call), not accuracy --
# accuracy against the labelled set is scripts/system-one-measure.py --hook
# ask, which loads the model in-process and reports per-question
# precision/recall and the options_complete confusion matrix.
#
# The cases file has one row per question; this runner rebuilds each
# AskUserQuestion call from its rows (the `call` column) and feeds the whole
# call to the hook, the way Claude Code does.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../system-one-ask.sh"
WRAPPER="$HERE/../../scripts/system-one"
CASES="$HERE/system-one-ask-cases.tsv"
# Budget per call: 300 ms for one question plus 100 ms per further question.
# A multi-question call runs one model call per question (launched in
# parallel, but the server serialises inference, about 95 ms per state on
# MPS), so the ceiling has to grow with the count; measured means are about
# 205 / 300 / 385 / 495 ms for one to four questions (design doc 11a).
LIMIT_BASE_MS=300
LIMIT_PER_Q_MS=100

usage() {
    cat <<'USAGE'
usage: run-system-one-ask.sh [-v] [--no-stop] [case-file]

Rebuilds each AskUserQuestion call from the case file's rows and feeds it to
hooks/system-one-ask.sh as a PreToolUse payload in shadow mode, checking exit
code, silence, latency (300 ms plus 100 ms per further question) and one
shadow-log line per question.

  -v         print every case
  --no-stop  leave the server running afterwards even if this runner started it
USAGE
}

VERBOSE=0
NOSTOP=0
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        --no-stop) NOSTOP=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) CASES=$1; shift ;;
    esac
done

now_ms() { perl -MTime::HiRes=time -e 'printf "%d\n", time * 1000'; }

STARTED=0
STATUS=$("$WRAPPER" status)
if ! printf '%s\n' "$STATUS" | grep -q '^server: *running'; then
    "$WRAPPER" start
    STARTED=1
fi
PORT=$(printf '%s\n' "$STATUS" | sed -n 's/^server: .*:\([0-9][0-9]*\).*/\1/p' | head -1)
[ -n "$PORT" ] || PORT=7811
for _ in $(seq 1 60); do
    curl -s --max-time 1 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"' && break
    sleep 0.5
done

TMP=$(mktemp -d "${TMPDIR:-/tmp}/system-one-ask-test.XXXXXX")
trap 'rm -rf -- "$TMP"' EXIT
export SYSTEM_ONE_STATE_DIR="$TMP"
export SYSTEM_ONE_MODE=shadow

# Group the rows by call: calls.tsv holds call<TAB>count<TAB>recent<TAB>[question_json...]
# with the questions in index order (the file is written in that order).
awk -F'\t' '!/^#/ && NF >= 11 {
    if (!($5 in seen)) { order[++n] = $5; seen[$5] = 1; count[$5] = $7; recent[$5] = $11; qs[$5] = $9 }
    else qs[$5] = qs[$5] "\t" $9
} END { for (i = 1; i <= n; i++) print order[i] "\t" count[order[i]] "\t" recent[order[i]] "\t" qs[order[i]] }' "$CASES" > "$TMP/calls.tsv"

fail=0 total=0 max_ms=0 sum_ms=0
n=0
while IFS=$'\t' read -r call count recent rest; do
    [ -n "$call" ] || continue
    n=$((n + 1))
    total=$((total + 1))
    session="case$n"

    # A one-line-per-message fixture transcript, built from the call's
    # "recent" column ("user: ...\nuser: ...\nassistant: ...", newlines
    # stored as a literal backslash-n), so the hook's bounded transcript
    # read is exercised the same way run-system-one-prompt.sh exercises it.
    transcript="$TMP/t$n.jsonl"
    : > "$transcript"
    if [ -n "$recent" ]; then
        printf '%s' "$recent" | perl -pe 's/\\n/\n/g' | while IFS= read -r rline; do
            case "$rline" in
                "user: "*) txt=${rline#user: }; role=user ;;
                "assistant: "*) txt=${rline#assistant: }; role=assistant ;;
                *) continue ;;
            esac
            if [ "$role" = user ]; then
                jq -cn --arg t "$txt" '{type:"user", message:{role:"user", content:$t}}' >> "$transcript"
            else
                jq -cn --arg t "$txt" '{type:"assistant", message:{content:[{type:"text", text:$t}]}}' >> "$transcript"
            fi
        done
    fi

    # The tab-separated question_json cells (newlines escaped) back into one array.
    questions=$(printf '%s' "$rest" | perl -pe 's/\\n/\n/g' | jq -cs '.')
    nq=$(printf '%s' "$questions" | jq 'length')
    payload=$(jq -cn --arg s "$session" --arg tp "$transcript" --argjson q "$questions" \
        '{session_id: $s, transcript_path: $tp, tool_name: "AskUserQuestion", tool_input: {questions: $q}}')

    t0=$(now_ms)
    set +e
    out=$(printf '%s' "$payload" | "$HOOK")
    rc=$?
    set -e
    ms=$(( $(now_ms) - t0 ))
    sum_ms=$((sum_ms + ms))
    [ "$ms" -gt "$max_ms" ] && max_ms=$ms
    logged=0
    [ -s "$TMP/shadow/ask/$session.jsonl" ] && logged=$(grep -c '' "$TMP/shadow/ask/$session.jsonl")
    limit=$((LIMIT_BASE_MS + LIMIT_PER_Q_MS * (nq - 1)))
    status=ok
    if [ "$rc" != 0 ]; then status="ERROR exit $rc"; fail=$((fail + 1))
    elif [ -n "$out" ]; then status="ERROR output in shadow mode"; fail=$((fail + 1))
    elif [ "$ms" -gt "$limit" ]; then status="ERROR ${ms}ms > ${limit}ms"; fail=$((fail + 1))
    elif [ "$logged" != "$nq" ]; then status="ERROR $logged shadow log line(s) for $nq question(s)"; fail=$((fail + 1))
    elif [ "$nq" != "$count" ]; then status="ERROR case file has $nq of $count rows for this call"; fail=$((fail + 1))
    fi
    if [ "$status" != ok ] || [ "$VERBOSE" = 1 ]; then
        q1=$(printf '%s' "$questions" | jq -r '.[0].question // ""' 2>/dev/null)
        printf '%-6s %5dms  %s q=%s  %s\n' \
            "$([ "$status" = ok ] && echo ok || echo FAIL)" "$ms" "$call" "$nq" "${q1:0:60}"
        [ "$status" != ok ] && printf '       %s\n' "$status"
    fi
done < "$TMP/calls.tsv"

echo "ran $total calls; max ${max_ms}ms, mean $((total > 0 ? sum_ms / total : 0))ms; hook errors $fail"
if [ "$STARTED" = 1 ] && [ "$NOSTOP" = 0 ]; then
    unset SYSTEM_ONE_STATE_DIR
    "$WRAPPER" stop
fi
[ "$fail" = 0 ]
