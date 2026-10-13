---
description: Mine the user's Claude Code chat logs: find every occurrence of a failure, a request, or a skill or tool use across many sessions, recall one past conversation, or review how one session fared. Uses the shared extract-session-text reader, small read-only sub-agents to classify, and a findings report; never a hand-written jsonl parser. Use when the user says "scour my chat logs", "find the times when...", "check the conversation logs for similar", "survey my recent conversations", "go over session X's log", or when another skill needs evidence from past sessions.
user-invocable: true
allowed-tools: Bash, Read, Agent
argument-hint: <what to find in the chat logs>
---

# mine-chat-logs

Reads the user's past sessions and reports what is in them. **It reports findings and
decides nothing.** Whether a pattern earns a skill or rule is
`pattern-discovery-for-new-skill`, which calls this skill for its evidence. Any other
skill or agent session calls it the same way: run the steps it needs, take back the
files and counts.

**Never write a transcript parser.** Every read goes through
`$AGENTS_SHARED/scripts/extract-session-text.py` (text or JSON rows, one session or
all) and `jq` over its rows. `--help` lists every flag. A parser written for one
question costs tokens now and is thrown away; `claude/rules/never-hand-roll-a-transcript-parser.md`
says why.

## 1. Pick the kind

| The user wants | Use |
|---|---|
| One past conversation found again ("find the chat where...") | `search-history` to find the session, then `extract-session-text.py <id> --around <time>` or `--grep` |
| Every time something happened, across sessions | steps 2 to 6 below |
| How one session fared | `extract-session-text.py <id> --kinds user,assistant,calls --chunk-chars 60000 --out <scratch>/s`, then read the chunks |
| Their own typed prompts matching a phrase, counted | `find-repeated-user-prompts.py` (see `pattern-discovery-for-new-skill`) |

Three surveys already exist; when the question is one of them, run it first:
`find-interrupted-responses.py` (dropped connections and what was typed next),
`find-listed-unasked-decisions.py` (decisions listed in prose instead of asked),
`find-invisible-output-claims.py` ("as shown above" about output the user never saw).

## 2. State the window

```bash
python3 "$AGENTS_SHARED/scripts/extract-session-text.py" --all --days 30 --window
```

Prints the session count and the earliest entry. The report says "transcripts begin
<date>; nothing earlier is visible". Never claim a habit is older than the logs, or new.

## 3. Candidates, mechanically

One JSON row per block, the agent's side with the user's reply attached:

```bash
python3 "$AGENTS_SHARED/scripts/extract-session-text.py" --all --days 30 \
  --kinds assistant,calls --json --next-user --grep 'REGEX' \
  --exclude-session <this session's id> > <scratch>/candidates.jsonl
```

- Narrow with `--project TEXT`, `--since/--until`, `--subagents` (sub-agent
  transcripts, rows flagged `sidechain`), and `--session-mentions REGEX`. That one
  matches the raw file, skill listings included, so give it a pattern only a real use
  produces: `'"skill": ?"archify"'`, not `archify`.
- Row fields: `session, project, time, group, label, text, tool, input, next_user`
  (plus `sidechain, meta, origin, api_error`). Tool inputs and results are cut to 2000
  characters unless `--max-chars` says otherwise.
- Pick a regex only the failure produces; a loose one buries it. Count the rows with
  `wc -l` and the sessions with `jq -r .session | sort -u | wc -l` before going on.

## 4. Classify with small agents

Fewer than about 30 candidates: read them yourself. More: split the rows into batches
of about 30 (`jq`/`split`), one `haiku` sub-agent per batch, effort low, read-only. Each
brief holds the question in the user's words, what counts as a real instance and what
is noise (a lookup of an old chat, pasted logs, a test harness, this session's own
prompts, injected agent messages), the batch file's absolute path, and the output: a
JSONL file of `{id, verdict: REAL|NOISE|UNSURE, why, quote}` at an absolute path under
the scratchpad, with a report of about 250 words. Add the sizing table from
`size-subagents-to-the-task.md` so their own spawns are sized. Then read about eight of
the verdicts yourself, at least two of each kind.

## 5. Read the context

For about eight real instances, drawn from every group, not only the suspected one:

```bash
python3 "$AGENTS_SHARED/scripts/extract-session-text.py" <session-id> \
  --kinds user,assistant,calls --around <YYYY-MM-DDTHH:MM> --context 6
```

## 6. Report

The corrected count (candidates minus noise) with its session count, the window edge,
matches per week and per project (`jq` group-by over the rows), the rate per active
day, two to four kinds each with a verbatim quote, and for a keyword or regex filter
the word "estimate", never "bound". When daily counts jump around, say "spiky, no
readable trend". A short answer goes in the reply; more than about 15 rows is a page
from `/new-html-page` named `YYYY-MM-DD-slug.html` in the notebook repo.

A candidate query worth running again goes in `agents-shared/scripts/`, not the
scratchpad. A calling skill gets the paths of `candidates.jsonl` and the verdict files
and the counts, and carries on from there.
