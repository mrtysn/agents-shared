#!/bin/zsh
# DESC: Rule Failure Survey: counts three rule failures over 7 days and notifies when one rises week over week
set -euo pipefail

# Each run counts, over the last 7 days of Claude Code transcripts, the failures three rules
# exist to prevent, appends one row per day to a history file, and compares the row with the
# one from 7 or more days earlier. A count that rose raises one macOS notification that states
# the problem. The three counters read transcripts through the shared reader; no network, no model.

root=$(git -C "${0:A:h}" rev-parse --show-toplevel)
scripts=$root/scripts
state=${XDG_STATE_HOME:-$HOME/.local/state}/rule-failure-survey
rows=$state/history.jsonl
mkdir -p "$state"
touch "$rows"

# /bin/date: the BSD date takes -v; a GNU date earlier on PATH does not.
today=$(/bin/date +%F)
since=$(/bin/date -v-7d +%F)

parsers=$(python3 "$scripts/count-hand-rolled-transcript-parsers.py" --days 7 --json | jq '.calls["hand-rolled"]')
commits=$(python3 "$scripts/count-manual-commit-requests.py" --days 7 --samples 0 | sed -n 's/^commit requests: \([0-9][0-9]*\) in.*/\1/p')
invisible=$(python3 "$scripts/find-invisible-output-claims.py" --since "$since" --examples 0 --json | jq '.reference_hits | length')

# The skill-group usage cache that hooks/note-skill-groups-used-here.sh reads at session start.
python3 "$scripts/report-skill-group-use.py" --write-cache --quiet

for value in "$parsers" "$commits" "$invisible"; do
    [[ "$value" =~ '^[0-9]+$' ]] || { print -u2 "rule-failure-survey: a counter printed no number (parsers='$parsers' commits='$commits' invisible='$invisible')"; exit 1 }
done

row=$(jq -cn --arg d "$today" --argjson p "$parsers" --argjson c "$commits" --argjson i "$invisible" \
    '{date: $d, parsers: $p, commits: $c, invisible: $i}')

tmp=$(mktemp)
grep -v "\"date\":\"$today\"" "$rows" > "$tmp" || true
print -r -- "$row" >> "$tmp"
mv "$tmp" "$rows"

print "rule-failure-survey: $today  hand-rolled parsers $parsers  manual commit requests $commits  invisible-output claims $invisible"

previous=$(jq -s --arg cutoff "$since" 'map(select(.date <= $cutoff)) | last // empty' "$rows")
if [[ -z "$previous" ]]; then
    print "rule-failure-survey: no row from 7 or more days ago yet; nothing to compare"
    exit 0
fi

rose=()
jq_get() { print -r -- "$previous" | jq -r ".$1"; }
(( parsers > $(jq_get parsers) )) && rose+=("hand-rolled transcript parsers $(jq_get parsers) to $parsers")
(( commits > $(jq_get commits) )) && rose+=("manual commit requests $(jq_get commits) to $commits")
(( invisible > $(jq_get invisible) )) && rose+=("claims about output you never saw $(jq_get invisible) to $invisible")

if (( ${#rose} == 0 )); then
    print "rule-failure-survey: no count rose against $(jq_get date)"
    exit 0
fi

message="${(j:; :)rose} (7 days, against $(jq_get date))"
print "rule-failure-survey: ROSE: $message"
terminal-notifier -title "Rule failures rose" -message "$message" -group rule-failure-survey >/dev/null
