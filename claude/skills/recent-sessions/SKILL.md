---
description: List Claude Code sessions by recency with first user prompt. Use for recovering context after a crash, restart, or lost iTerm window — shows what was being worked on, when, and in which project.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: [-d 3 for last 3 days, -n 25 to limit, -c for current project, -p <name>, -m <regex>, -r N to resume]
---

# recent-sessions

List recent Claude Code sessions across all projects, sorted by mtime, with each session's first user prompt. Complements `/search-history` — this is the time-driven view, not the keyword-driven one.

Run the script:

```bash
python3 ~/dev/personal/agents-shared/scripts/recent-sessions.py $ARGUMENTS
```

**Flags:**
- `--days N` / `-d N`: only sessions from the last N days (default: 3, 0=all time)
- `--limit N` / `-n N`: max sessions to show (default: 25, 0=all)
- `--project NAME` / `-p NAME`: filter by project (substring match)
- `--current` / `-c`: filter to current project (from git repo root)
- `--match REGEX` / `-m REGEX`: filter to sessions whose first prompt or content matches
- `--full`: do not truncate the first-prompt column
- `--id-len N`: session-id chars to show (default: 36, full UUID; lower for preview only)
- `--resume N` / `-r N`: resume session number N from the last run

**Output:** numbered table of `#N | session-id | project | mtime | size | first prompt`.

Present the output to the user directly.

**Typical flows:**
- "What was I working on before the restart?" → `recent-sessions -d 1`
- "Find that session from last week about pagination" → `recent-sessions -d 14 -m pagination`
- "Resume session #3 from the list above" → `recent-sessions -r 3`

The numbered list is cached (shared with `/search-history`), so `--resume N` works after either command.
