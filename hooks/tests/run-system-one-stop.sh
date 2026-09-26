#!/bin/bash
# DESC: Run the system-one-stop Stop hook against its case file structurally (exit code, shadow-mode silence, latency)
#
# Bash, to match the hook under test and the runner beside it. Checks the
# hook's plumbing, not accuracy -- accuracy against the labelled set is
# scripts/system-one-measure.py --hook stop, which loads the model in-process
# and reports per-class precision/recall and a confusion matrix.
#
# Each case's message becomes a one-line fixture transcript (a single
# assistant text message, its escaped newlines restored), since the hook
# reads transcript_path itself.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../system-one-stop.sh"
WRAPPER="$HERE/../../scripts/system-one"
CASES="$HERE/system-one-stop-cases.tsv"
QUESTIONS="$HERE/../system-one-stop-questions.json"
LIMIT_MS=500

usage() {
    cat <<'USAGE'
usage: run-system-one-stop.sh [-v] [--no-stop] [case-file]

Feeds each case to hooks/system-one-stop.sh as a Stop payload (transcript_path
pointing at a one-message fixture) in shadow mode, checking exit code,
silence, latency and the expected shadow-log lines (one, for
needless_table/overlong; zero when the deterministic pre-gate skips the call).

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

TMP=$(mktemp -d "${TMPDIR:-/tmp}/system-one-stop-test.XXXXXX")
trap 'rm -rf -- "$TMP"' EXIT
export SYSTEM_ONE_STATE_DIR="$TMP"
export SYSTEM_ONE_MODE=shadow

# The hook makes one call per Stop (needless_table/overlong on
# SYSTEM_ONE_STOP_MODEL), writing one shadow-log line. The deterministic
# pre-gate (pregate.max_chars in the questions file) skips the call entirely
# for a message shorter than that with no table line, so those cases expect
# zero lines; every other case expects exactly one.
PREGATE=$(jq -r '.pregate.max_chars // 0' "$QUESTIONS" 2>/dev/null)
pregated() {
    jq -rn --arg t "$1" --argjson n "$PREGATE" '
        ($t | gsub("\\\\n"; "\n")) as $m
        | if ($m | length) < $n and ([$m | split("\n")[] | select(test("^\\s*\\|.*\\|\\s*$"))] | length) == 0
          then "yes" else "no" end'
}

fail=0 total=0 max_ms=0 sum_ms=0 skipped=0
n=0
while IFS=$'\t' read -r label msg; do
    case "$label" in ''|\#*) continue ;; esac
    n=$((n + 1))
    total=$((total + 1))
    session="case$n"
    transcript="$TMP/t$n.jsonl"
    # The cases file stores a message's newlines as a literal backslash-n.
    jq -cn --arg t "$msg" '{type:"assistant", message:{content:[{type:"text", text:($t | gsub("\\\\n"; "\n"))}]}}' > "$transcript"
    payload=$(jq -n --arg tp "$transcript" --arg s "$session" '{session_id:$s, transcript_path:$tp, stop_hook_active:false}')
    t0=$(now_ms)
    set +e
    out=$(printf '%s' "$payload" | "$HOOK")
    rc=$?
    set -e
    ms=$(( $(now_ms) - t0 ))
    sum_ms=$((sum_ms + ms))
    [ "$ms" -gt "$max_ms" ] && max_ms=$ms
    logged=0
    [ -s "$TMP/shadow/stop/$session.jsonl" ] && logged=$(grep -c '' "$TMP/shadow/stop/$session.jsonl")
    expect=1
    if [ "$(pregated "$msg")" = yes ]; then expect=0; skipped=$((skipped + 1)); fi
    status=ok
    if [ "$rc" != 0 ]; then status="ERROR exit $rc"; fail=$((fail + 1))
    elif [ -n "$out" ]; then status="ERROR output in shadow mode"; fail=$((fail + 1))
    elif [ "$ms" -gt "$LIMIT_MS" ]; then status="ERROR ${ms}ms > ${LIMIT_MS}ms"; fail=$((fail + 1))
    elif [ "$logged" != "$expect" ]; then status="ERROR shadow log lines: expected $expect, got $logged"; fail=$((fail + 1))
    fi
    if [ "$status" != ok ] || [ "$VERBOSE" = 1 ]; then
        printf '%-6s %5dms  gold=%-9s %s\n' "$([ "$status" = ok ] && echo ok || echo FAIL)" "$ms" "$label" "${msg:0:60}"
        [ "$status" != ok ] && printf '       %s\n' "$status"
    fi
done < "$CASES"

echo "ran $total cases ($skipped pre-gated: no call); max ${max_ms}ms, mean $((total > 0 ? sum_ms / total : 0))ms; hook errors $fail"
if [ "$STARTED" = 1 ] && [ "$NOSTOP" = 0 ]; then
    unset SYSTEM_ONE_STATE_DIR
    "$WRAPPER" stop
fi
[ "$fail" = 0 ]
