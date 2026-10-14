# Rule Failure Survey

Every morning at 09:30 this job counts, over the last 7 days of Claude Code transcripts, three
failures that rules in `claude/rules/` exist to prevent, and notifies when a count rose against the
count from 7 or more days earlier.

| Count | Counter | Rule it measures |
|---|---|---|
| hand-rolled transcript parsers | `scripts/count-hand-rolled-transcript-parsers.py --days 7 --json` | never-hand-roll-a-transcript-parser |
| manual commit requests | `scripts/count-manual-commit-requests.py --days 7 --samples 0` | commit-atomically-as-you-build |
| claims about output the user never saw | `scripts/find-invisible-output-claims.py --since <7 days ago> --json` | restate-hidden-output-in-replies |

Each run appends one JSON row per day (`date`, `parsers`, `commits`, `invisible`) to
`${XDG_STATE_HOME:-~/.local/state}/rule-failure-survey/history.jsonl` and replaces that day's row on
a second run. A rise raises one macOS notification through `terminal-notifier` that states the
counts. It never says what to do; the remedy is in the rule.

The counters read transcripts only. The job makes no network request and calls no model.

- `project-lifecycle test` parses the script; `project-lifecycle run` runs it once now.
- A first run has no row to compare against and only records. The comparison starts 7 days later.
- To add a count, add its counter to `scripts/rule-failure-survey.zsh` and a field to the row.
