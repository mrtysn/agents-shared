---
description: Find which Claude Code sessions modified the currently changed files. Use when user wants to trace uncommitted changes back to specific sessions.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: [--all to include reads, -n 5 to limit results]
---

# blame-session

Identify which Claude Code sessions are responsible for the current uncommitted changes.

Run the script:

```bash
python3 ~/dev/personal/agents-shared/scripts/blame-session.py $ARGUMENTS
```

**Flags:**
- Default: only shows sessions that wrote to files (Edit, Write, Bash)
- `--all` / `-a`: also include sessions that only Read the files
- `--limit N` / `-n N`: limit to N most recent sessions

Present the output to the user directly. The output shows:
- Each session ID that touched currently changed files
- The branch and timestamp
- A `claude --resume <id>` command to jump back into that session
- Which files each session modified and with which tools

If the output is empty or no sessions found, explain that either:
1. The changes were made manually (not through Claude Code)
2. The session transcripts may have been cleaned up
3. The changes came from a different machine
