---
description: Search Claude Code conversation history by keyword. Use when user wants to find past sessions that discussed a topic, used a term, or mentioned specific code.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: <keyword> [-d 30 for last month, -c for current project, -p <project>, -n 10 to limit, -s for case-sensitive]
---

# search-history

Search Claude Code session transcripts for keyword matches across all projects.

Run the script:

```bash
python3 "${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/scripts/search-history.py" $ARGUMENTS
```

**Flags:**
- `keyword` (positional, required): search term — supports regex
- `--days N` / `-d N`: limit to last N days (default: 14, 0=all time)
- `--limit N` / `-n N`: max sessions to show (default: 20)
- `--project NAME` / `-p NAME`: filter to project (substring match on directory name)
- `--current` / `-c`: filter to current project (from git repo root)
- `--case-sensitive` / `-s`: exact case matching (default: case-insensitive)
- `--resume N` / `-r N`: resume session number N from the last run

**Output:** ranked session table with match counts, snippets, and resume numbers.

Present the output to the user directly.

If no matches found, suggest:
1. Broadening the time window (`-d 0` for all time)
2. Trying alternate spellings or a regex pattern
3. Checking if the topic was discussed in a different project (`-p <name>`)
