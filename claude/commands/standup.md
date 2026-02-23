---
description: Generate a daily standup summary of yesterday's work across repos.
allowed-tools: Bash, Read, Grep, Glob
---

Generate a concise daily standup summary of yesterday's work.

$ARGUMENTS

## Repo discovery

**Default (no path argument):** check `~/.claude/standup-repos` for a list of paths (one per line, `#` comments ignored). If the file is absent or empty, tell the user to create it and stop.

**With a path argument:** if $ARGUMENTS contains a directory path, find all git repos under it:
```bash
find <path> -maxdepth 3 -name ".git" -type d | sed 's/\/.git$//'
```

**Date argument:** if $ARGUMENTS contains a date (e.g. `2026-02-18`), use that instead of yesterday. Arguments can be combined: `/standup 2026-02-18 ~/dev/personal/godot`

## Data collection

For each repo, collect:
- Commits from the target date: `git -C <path> log --since="<date> 00:00:00" --until="<next-day> 00:00:00" --format="%h %s" --all`
- Current uncommitted changes: `git -C <path> diff --stat` and `git -C <path> status --short`
- Skip repos with no commits and no local changes

## Output format — keep it tight for a standup:

```
## Standup — <date>

**Done:**
- <bullet per meaningful commit or group of related commits>

**In progress:**
- <bullet per repo with uncommitted work, summarizing what the changes do>
```

## Summary

After the standup block, add a one-liner summary in each language:

```
**Summary (EN):** <one casual sentence covering the day's work, conversational tone>

**Summary (TR):** <same summary in Turkish, natural spoken style — e.g. "redis'te analytics kısmında iyileştirmeler yaptım, broadcast fonksiyonlarının üzerinden geçtim">
```

- Write as if explaining to a teammate over coffee, not translating a commit log
- Group by theme, not by commit
- Keep each summary to 1–2 sentences max

## Rules
- Group related commits into single bullets (e.g., 3 commits about alerts → one bullet)
- Describe *what was accomplished*, not commit hashes
- For uncommitted work, read the diff to understand intent — don't just list file names
- No filler, no preamble, no sign-off — just the standup block and summaries
