#!/bin/bash
# DESC: Run the system-one-prompt UserPromptSubmit hook against its case file structurally (exit code, shadow-mode silence, latency)
#
# Bash, to match the hook under test and the runner beside it. This checks the
# hook's plumbing (exit 0, no stdout in shadow mode, under the latency budget,
# a shadow-log line written), not accuracy -- accuracy against the labelled
# set is scripts/system-one-measure.py --hook prompt, which loads the model
# in-process and reports per-class precision/recall and a confusion matrix.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../system-one-prompt.sh"
WRAPPER="$HERE/../../scripts/system-one"
CASES="$HERE/system-one-prompt-cases.tsv"
LIMIT_MS=300

usage() {
    cat <<'USAGE'
usage: run-system-one-prompt.sh [-v] [--no-stop] [case-file]

Feeds each case to hooks/system-one-prompt.sh as a UserPromptSubmit payload in
shadow mode, checking exit code, silence, latency and a written shadow-log line.

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

TMP=$(mktemp -d "${TMPDIR:-/tmp}/system-one-prompt-test.XXXXXX")
trap 'rm -rf -- "$TMP"' EXIT
export SYSTEM_ONE_STATE_DIR="$TMP"
export SYSTEM_ONE_MODE=shadow

fail=0 total=0 max_ms=0 sum_ms=0
n=0
while IFS=$'\t' read -r kind wants_action prompt prev; do
    case "$kind" in ''|\#*) continue ;; esac
    n=$((n + 1))
    total=$((total + 1))
    session="case$n"
    # A case with a previous assistant message gets a one-line fixture
    # transcript, so the hook's bounded transcript read is exercised too; the
    # column stores newlines as a literal backslash-n.
    transcript=/nonexistent
    if [ -n "$prev" ]; then
        transcript="$TMP/t$n.jsonl"
        jq -cn --arg t "$prev" '{type:"assistant", message:{content:[{type:"text", text:($t | gsub("\\\\n"; "\n"))}]}}' > "$transcript"
    fi
    payload=$(jq -n --arg p "$prompt" --arg s "$session" --arg tp "$transcript" '{session_id: $s, prompt: $p, transcript_path: $tp}')
    t0=$(now_ms)
    set +e
    out=$(printf '%s' "$payload" | "$HOOK")
    rc=$?
    set -e
    ms=$(( $(now_ms) - t0 ))
    sum_ms=$((sum_ms + ms))
    [ "$ms" -gt "$max_ms" ] && max_ms=$ms
    logged=no
    [ -s "$TMP/shadow/prompt/$session.jsonl" ] && logged=yes
    status=ok
    if [ "$rc" != 0 ]; then status="ERROR exit $rc"; fail=$((fail + 1))
    elif [ -n "$out" ]; then status="ERROR output in shadow mode"; fail=$((fail + 1))
    elif [ "$ms" -gt "$LIMIT_MS" ]; then status="ERROR ${ms}ms > ${LIMIT_MS}ms"; fail=$((fail + 1))
    elif [ "$logged" != yes ]; then status="ERROR no shadow log line"; fail=$((fail + 1))
    fi
    if [ "$status" != ok ] || [ "$VERBOSE" = 1 ]; then
        printf '%-6s %5dms  gold=%-11s %s\n' "$([ "$status" = ok ] && echo ok || echo FAIL)" "$ms" "$kind" "${prompt:0:60}"
        [ "$status" != ok ] && printf '       %s\n' "$status"
    fi
done < "$CASES"

echo "ran $total cases; max ${max_ms}ms, mean $((total > 0 ? sum_ms / total : 0))ms; hook errors $fail"
if [ "$STARTED" = 1 ] && [ "$NOSTOP" = 0 ]; then
    unset SYSTEM_ONE_STATE_DIR
    "$WRAPPER" stop
fi
[ "$fail" = 0 ]
