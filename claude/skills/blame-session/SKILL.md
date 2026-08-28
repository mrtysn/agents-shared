---
description: Find which Claude Code sessions modified the currently changed files. Use when user wants to trace uncommitted changes back to specific sessions.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: [--all to include reads, -n 5 to limit, -d 7 for last week, -i for interactive]
---

# blame-session

Identify which Claude Code sessions are responsible for the current uncommitted changes.

Run the script:

```bash
python3 "${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/scripts/blame-session.py" $ARGUMENTS
```

**Flags:**
- Default: only shows sessions that wrote to files (Edit, Write, Bash) in the last 14 days
- `--all` / `-a`: also include sessions that only Read the files
- `--limit N` / `-n N`: limit to N most recent sessions
- `--days N` / `-d N`: show sessions from last N days (default: 14, 0=all time)
- `--interactive` / `-i`: launch curses TUI with cross-highlighting (enter to resume)
- `--resume N` / `-r N`: resume session number N from the last run

**Output modes:**
- **Static** (default): matrix table with multi-round wrapping for wide output. Designed for both human reading and AI agent consumption.
- **Interactive** (`-i`): curses TUI where hovering a file highlights all sessions that touched it, and hovering a session highlights all files it touched. Press Enter to resume a session. Arrow keys / hjkl to navigate, Tab to switch between file/session axis.

Present the output to the user directly.

If no sessions found, explain that either:
1. The changes were made manually (not through Claude Code)
2. The session transcripts may have been cleaned up
3. The changes predate the time window (suggest `--days 0`)
