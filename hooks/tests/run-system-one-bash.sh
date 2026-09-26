#!/bin/bash
# DESC: Run the system-one-bash PreToolUse hook against its case file and report model agreement
#
# Bash, not zsh, to match the hook under test and the runners beside it.
#
# Starts the server through the wrapper if it is not up, then feeds each case to
# the hook in shadow mode with a temporary state dir, so the real shadow log is
# untouched, and reads would_act back from the temporary log. The model is
# zero-shot, so a disagreement with the expected column is reported, not failed.
# The run fails only if the hook exits non-zero, prints anything in shadow mode,
# or takes longer than 2 s.
#
# Case file: the extended 6-column shape (cmd, foreign_process, irreversible,
# leaves_machine, destructiveness, target -- see system-one-bash-cases.tsv) or the
# legacy 2-column shape (want<TAB>cmd), auto-detected per row by field count.
# "want" for an extended row is derived: true if any of foreign_process,
# irreversible, leaves_machine is 1.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../system-one-bash.sh"
WRAPPER="$HERE/../../scripts/system-one"
CASES="$HERE/system-one-bash-cases.tsv"
LIMIT_MS=2000

usage() {
    cat <<'USAGE'
usage: run-system-one-bash.sh [-v] [--no-stop] [case-file]

Feeds each case to hooks/system-one-bash.sh as a PreToolUse payload in shadow
mode and compares the logged would_act with the expected column.

  -v         print every case, not just disagreements
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
for _ in $(seq 1 60); do
    curl -s --max-time 1 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q '"ok"' && break
    sleep 0.5
done
curl -s --max-time 1 "http://127.0.0.1:$PORT/health" | grep -q '"ok"' || { echo "server did not become healthy on :$PORT"; exit 1; }

TMP=$(mktemp -d "${TMPDIR:-/tmp}/system-one-test.XXXXXX")
trap 'rm -rf -- "$TMP"' EXIT
export SYSTEM_ONE_STATE_DIR="$TMP"
export SYSTEM_ONE_MODE=shadow

fail=0 total=0 agree=0 disagree=0 max_ms=0 sum_ms=0
while IFS=$'\t' read -r f1 f2 f3 f4 f5 f6; do
    case "$f1" in ''|\#*) continue ;; esac
    if [ -n "$f6" ]; then
        # extended: cmd, foreign_process, irreversible, leaves_machine, destructiveness, target
        cmd=$f1
        want=false
        { [ "$f2" = 1 ] || [ "$f3" = 1 ] || [ "$f4" = 1 ]; } && want=true
    else
        # legacy: want, cmd
        want=$f1
        cmd=$f2
    fi
    total=$((total + 1))
    decoded=$(printf '%b' "$cmd")
    payload=$(jq -n --arg c "$decoded" '{session_id: "test", cwd: "~/dev/project", tool_name: "Bash", tool_input: {command: $c}}')
    t0=$(now_ms)
    set +e
    out=$(printf '%s' "$payload" | "$HOOK")
    rc=$?
    set -e
    ms=$(( $(now_ms) - t0 ))
    sum_ms=$((sum_ms + ms))
    [ "$ms" -gt "$max_ms" ] && max_ms=$ms
    got=$(tail -n 1 "$TMP/shadow/bash/test.jsonl" 2>/dev/null | jq -r 'if .would_act == null then "none" else (.would_act | tostring) end')
    fired=$(tail -n 1 "$TMP/shadow/bash/test.jsonl" 2>/dev/null | jq -r '[.fired[]? | "\(.q)=\(.value * 100 | round / 100)"] | join(",")')
    status=ok
    if [ "$rc" != 0 ]; then status="ERROR exit $rc"; fail=$((fail + 1))
    elif [ -n "$out" ]; then status="ERROR output in shadow mode"; fail=$((fail + 1))
    elif [ "$ms" -gt "$LIMIT_MS" ]; then status="ERROR ${ms}ms > ${LIMIT_MS}ms"; fail=$((fail + 1))
    fi
    if [ "$got" = "$want" ]; then agree=$((agree + 1)); else disagree=$((disagree + 1)); fi
    if [ "$status" != ok ] || [ "$got" != "$want" ] || [ "$VERBOSE" = 1 ]; then
        printf '%-6s want %-5s got %-5s %5dms  %-40s %s\n' "$([ "$status" = ok ] && echo ok || echo FAIL)" "$want" "$got" "$ms" "$cmd" "${fired:+[$fired]}"
        [ "$status" != ok ] && printf '       %s\n' "$status"
    fi
done < "$CASES"

echo "agreement $agree/$total (disagree $disagree); max ${max_ms}ms, mean $((sum_ms / (total > 0 ? total : 1)))ms; hook errors $fail"
if [ "$STARTED" = 1 ] && [ "$NOSTOP" = 0 ]; then
    unset SYSTEM_ONE_STATE_DIR   # stop the real server, not the one the temp pid file names
    "$WRAPPER" stop
fi
[ "$fail" = 0 ]
