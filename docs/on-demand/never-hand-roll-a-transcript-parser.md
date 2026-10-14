# Never hand-roll a transcript parser

**To read Claude Code transcripts (`~/.claude/projects/**/*.jsonl`), use the shared
reader. Do not write a parser.** An inline `python3 - <<EOF … json.loads …`, a `jq` over
the raw files, or a script written to `/tmp` and run later is the failure: it costs
tokens to write, it is thrown away, and the next session writes it again.

## What to use

| You need | Run |
|---|---|
| One session, as text | `$AGENTS_SHARED/scripts/extract-session-text.py <session-id> --kinds user,assistant,calls,tools [--grep REGEX] [--around YYYY-MM-DDTHH:MM]` |
| Many sessions, as rows | `extract-session-text.py --all --days N [--project TEXT] [--session-mentions REGEX] --kinds ... --json [--next-user]`, then `jq` over the rows |
| Whether a rule or hook note reached a session, and where | `extract-session-text.py <session-id> --kinds user,calls,attachments`: RULE-LOADED rows (a path-scoped rule) and HOOK-CONTEXT rows (a hook's added text) sit in order with the calls |
| A session found by keyword | `$AGENTS_SHARED/scripts/search-history.py` |
| A task like "scour my chat logs", "find the times when…" | the [mine-chat-logs skill](../skills/mine-chat-logs/SKILL.md) |

`jq` over the reader's rows is fine; parsing the raw jsonl is not.

## When the reader lacks something

Extend it where it lives (`scripts/extract-session-text.py`, `scripts/transcript_items.py`,
tests in `scripts/tests/`), per [fix what tripped you](fix-what-tripped-you-at-its-source.md).
A workaround parser beside it leaves the same gap for the next session.

## Enforcement

`hooks/nudge-transcript-parsers.sh` adds a note to the session, once, the first time a
command or a written file reads a Claude projects folder with python, jq or similar.
It never blocks. The note is a reminder of this rule, not a replacement for it.

## Provenance

Oct 13 2026, notebook: over 60 days, 350 Bash calls in 79 sessions parsed the
transcripts by hand, while 17 calls used a shared script
(`scripts/count-hand-rolled-transcript-parsers.py` repeats the count). The user: "I keep asking agents to go over chat
logs. They are all probably writing their own python parses to go over the jsonl. this
has become WAY TOO inefficient."
