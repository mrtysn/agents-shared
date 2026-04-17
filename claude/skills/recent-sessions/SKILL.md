---
description: List Claude Code sessions by recency with opening prompts and primary file. Use for recovering context after a crash, restart, or lost iTerm window — shows what was being worked on, when, and in which project.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: [-d 3 for last 3 days, -n 25 to limit, -c for current project, -p <name>, --prompts N, --full, -r N to resume]
---

# recent-sessions

List recent Claude Code sessions across all projects, sorted by mtime. For each session renders:

- header row: `#N | session UUID | project | mtime | size | first user prompt`
- `> …` lines: the next few user prompts (catches sessions that pivot after opening)
- `~ path` line: the most-touched file in the session (another discriminator when the prose is ambiguous)

Scope: this tool answers *"what was I doing recently?"*. For *"find the session that discussed X"*, use `/search-history` instead.

Run the script:

```bash
python3 ~/dev/personal/agents-shared/scripts/recent-sessions.py $ARGUMENTS
```

**Flags:**
- `--days N` / `-d N`: only sessions from the last N days (default: 3, 0=all time)
- `--limit N` / `-n N`: max sessions to show (default: 25, 0=all)
- `--project NAME` / `-p NAME`: filter by project (substring match)
- `--current` / `-c`: filter to current project (from git repo root)
- `--prompts N`: number of opening user prompts to show per session (default: 2)
- `--full`: do not truncate prompt / file-path columns
- `--resume N` / `-r N`: resume session number N from the last run

**Typical flows:**
- "What was I working on before the restart?" → `recent-sessions -d 1`
- "Current project only" → `recent-sessions -c`
- "Resume session #3 from the list above" → `recent-sessions -r 3`

The numbered list is cached (shared with `/search-history`), so `--resume N` works after either command.

## Known limitation

Sessions that pivot after opening will still be *labelled* by their opening prompts. The `> …` continuation prompts and the `~ path` row soften this, but no cheap heuristic catches every pivot. When the prose looks wrong, trust the `~ path` line or fall back to `/search-history` with a keyword.
