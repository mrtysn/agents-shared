#!/bin/bash
# DESC: Check scripts/system-one-receipts.py on a fixture shadow log: the per-hook summary joins and the --export-cases shapes
#
# Bash, to match the runners beside it. No server and no model: the fixture
# under a temp state dir carries one verdict row per hook plus the outcome
# rows the hooks would append (design doc section 13), and this checks that
# the summary counts them, that a verdict row with no outcome reads as "did
# not run", that an outcome whose ref matches nothing is ignored, that an
# empty log reports zero outcomes without failing, and that the exported
# prompt/stop TSVs carry the hooks/tests case-file columns rebuilt from the
# logged full state (a row with only state_excerpt is marked excerpt-only).

set -uo pipefail   # no -e: every check reports and the tally decides the exit

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT="$HERE/../../scripts/system-one-receipts.py"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/system-one-receipts-test.XXXXXX")
trap 'rm -rf -- "$TMP"' EXIT
mkdir -p "$TMP/shadow/prompt" "$TMP/shadow/stop" "$TMP/shadow/bash" "$TMP/shadow/ask"

fail=0
check() { # label condition-exit-code
    if [ "$2" = 0 ]; then printf 'ok    %s\n' "$1"; else printf 'FAIL  %s\n' "$1"; fail=$((fail + 1)); fi
}

# prompt: two verdict rows, the first labelled acted (kind order -> agrees),
# the second labelled from an excerpt-only pre-review row; plus a dangling ref.
cat > "$TMP/shadow/prompt/s1.jsonl" <<'ROWS'
{"ts":"2026-09-25T10:00:00+0300","ts_epoch":1790319600,"id":"2026-09-25T10:00:00+0300-aaaaaaaa-1","hook":"prompt","session_id":"s1","state_sha256":"aaaaaaaa","state_len":40,"answers":{"kind":{"choice":"order","probabilities":{"order":0.9}}},"would_act":true,"fired":[],"state":"prompt:\nadd a retry to the fetcher\nprevious:\nDone.\nNext?"}
{"ts":"2026-09-25T10:01:00Z","kind":"outcome","ref":"2026-09-25T10:00:00+0300-aaaaaaaa-1","next_kind":"question","next_is_command":false,"acted":true,"tool_calls":3}
{"ts":"2026-09-25T10:01:00+0300","id":"2026-09-25T10:01:00+0300-bbbbbbbb-2","hook":"prompt","session_id":"s1","state_sha256":"bbbbbbbb","state_len":30,"answers":{"kind":{"choice":"question","probabilities":{"question":0.8}}},"would_act":false,"fired":[],"state_excerpt":"prompt:\nwhy is the build red?"}
{"ts":"2026-09-25T10:02:00Z","kind":"outcome","ref":"2026-09-25T10:01:00+0300-bbbbbbbb-2","next_kind":"order","next_is_command":false,"acted":false,"tool_calls":0}
{"ts":"2026-09-25T10:03:00Z","kind":"outcome","ref":"no-such-id","next_kind":"order","next_is_command":false,"acted":true,"tool_calls":1}
ROWS
# stop: one verdict row per Stop (needless_table + overlong in a single
# call, current shape), two Stop events. First fired (needless_table over
# gate) and the user's next command was non-empty -> agrees. Second did not
# fire and the next command was empty -> agrees too.
cat > "$TMP/shadow/stop/s1.jsonl" <<'ROWS'
{"ts":"2026-09-25T10:00:30+0300","ts_epoch":1790319630,"id":"2026-09-25T10:00:30+0300-cccccccc-10","hook":"stop","session_id":"s1","model":"full-v1","state_sha256":"cccccccc","state_len":90,"answers":{"needless_table":{"noul":0.9},"overlong":{"noul":0.1}},"would_act":true,"fired":[{"q":"needless_table","kind":"noul","value":0.9}],"state":"assistant message:\nDone.\n| a | b |\nlength_chars: 14  tables: 1  headers: 0  bullets: 0"}
{"ts":"2026-09-25T10:01:00Z","kind":"outcome","ref":"2026-09-25T10:00:30+0300-cccccccc-10","next_prompt_kind":"other","next_command":"outstanding","ran_outstanding":true}
{"ts":"2026-09-25T10:05:30+0300","ts_epoch":1790319930,"id":"2026-09-25T10:05:30+0300-cccccccd-12","hook":"stop","session_id":"s1","model":"full-v1","state_sha256":"cccccccd","state_len":40,"answers":{"needless_table":{"noul":0.05},"overlong":{"noul":0.05}},"would_act":false,"fired":[],"state":"assistant message:\nDone.\nlength_chars: 5  tables: 0  headers: 0  bullets: 0"}
{"ts":"2026-09-25T10:06:00Z","kind":"outcome","ref":"2026-09-25T10:05:30+0300-cccccccd-12","next_prompt_kind":"question","next_command":"","ran_outstanding":false}
ROWS
# bash: one row that ran and failed, one that ran fine, one with no receipt
# (denied), would_act true only on the denied one -> 3/3 agreement.
cat > "$TMP/shadow/bash/s1.jsonl" <<'ROWS'
{"ts":"2026-09-25T10:00:10+0300","ts_epoch":1790319610,"id":"2026-09-25T10:00:10+0300-dddddddd-20","hook":"bash","session_id":"s1","tool_use_id":"t1","state_sha256":"dddddddd","state_len":30,"answers":{},"would_act":false,"fired":[],"state":"cwd: /tmp\ncommand:\nls /nonexistent"}
{"ts":"2026-09-25T10:00:11Z","kind":"outcome","ref":"2026-09-25T10:00:10+0300-dddddddd-20","ran":true,"exit_code":2,"failed":true,"interrupted":false}
{"ts":"2026-09-25T10:00:12+0300","ts_epoch":1790319612,"id":"2026-09-25T10:00:12+0300-eeeeeeee-21","hook":"bash","session_id":"s1","tool_use_id":"t2","state_sha256":"eeeeeeee","state_len":20,"answers":{},"would_act":false,"fired":[],"state":"cwd: /tmp\ncommand:\necho hi"}
{"ts":"2026-09-25T10:00:13Z","kind":"outcome","ref":"2026-09-25T10:00:12+0300-eeeeeeee-21","ran":true,"exit_code":0,"failed":false,"interrupted":false}
{"ts":"2026-09-25T10:00:14+0300","ts_epoch":1790319614,"id":"2026-09-25T10:00:14+0300-ffffffff-22","hook":"bash","session_id":"s1","tool_use_id":"t3","state_sha256":"ffffffff","state_len":25,"answers":{},"would_act":true,"fired":[{"q":"irreversible","kind":"noul","value":0.9}],"state":"cwd: /tmp\ncommand:\nrm -rf /tmp/x"}
ROWS

SUMMARY=$(python3 "$SCRIPT" --state-dir "$TMP")
printf '%s\n' "$SUMMARY" | grep -Eq '^prompt +2 +2 +1\.00 +2 '; check "prompt: 2 rows, 2 with outcome, agreement 1.00 (dangling ref ignored)" $?
printf '%s\n' "$SUMMARY" | grep -Eq '^stop +2 +2 +1\.00 +2 '; check "stop: one verdict row per Stop, fired vs next_command agrees on both" $?
printf '%s\n' "$SUMMARY" | grep -Eq '^bash +3 +2 +1\.00 +3 .*1 ran and failed'; check "bash: no-receipt row reads as did-not-run, one failed run counted" $?
printf '%s\n' "$SUMMARY" | grep -Eq '^ask +0 +0 +- +0 '; check "ask: empty log reports zero, no error" $?

python3 "$SCRIPT" --state-dir "$TMP" --export-cases prompt "$TMP/prompt.tsv" >/dev/null
EXPECT_P=$'order\t1\tadd a retry to the fetcher\tDone.\\nNext?'
[ "$(sed -n 3p "$TMP/prompt.tsv")" = "$EXPECT_P" ]; check "prompt export: kind, wants_action, prompt, previous rebuilt from the full state" $?
[ "$(sed -n 4p "$TMP/prompt.tsv")" = $'question\t0\twhy is the build red?\t\texcerpt-only' ]; check "prompt export: excerpt-only row marked" $?
[ "$(head -1 "$TMP/prompt.tsv")" = "# kind	wants_action	prompt	previous" ]; check "prompt export: header matches system-one-prompt-cases.tsv" $?

python3 "$SCRIPT" --state-dir "$TMP" --export-cases stop "$TMP/stop.tsv" >/dev/null
[ "$(sed -n 3p "$TMP/stop.tsv")" = $'outstanding\tDone.\\n| a | b |' ]; check "stop export: label and message rebuilt from the full state" $?
[ "$(sed -n 4p "$TMP/stop.tsv")" = $'not_outstanding\tDone.' ]; check "stop export: second Stop's ran_outstanding=false labelled correctly" $?
[ "$(grep -c '^outstanding' "$TMP/stop.tsv")" = 1 ]; check "stop export: one row per labelled verdict row" $?

EMPTY=$(mktemp -d "${TMPDIR:-/tmp}/system-one-receipts-empty.XXXXXX"); mkdir -p "$EMPTY/shadow"
python3 "$SCRIPT" --state-dir "$EMPTY" | grep -q 'no outcome rows anywhere'; check "empty state dir: zero outcomes reported, exit 0" $?
rm -rf -- "$EMPTY"

echo "receipts checks failed: $fail"
[ "$fail" = 0 ]
