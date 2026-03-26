---
description: Generate a daily standup summary, log it, and optionally backfill history.
argument-hint: [date] [path]
allowed-tools: Bash, Read, Grep, Glob, Write, AskUserQuestion
---

Daily standup: collect the last working day's activity, display it, persist it, offer to backfill gaps.

$ARGUMENTS

---

## 1. Resolve inputs

- **Date**: use date from $ARGUMENTS if provided (convert relative dates to absolute). If no date given, find the **last day with activity**: starting from yesterday, walk backwards day by day (up to 14 days). For each candidate date, check `git log --since="<date> 00:00:00" --until="<next-day> 00:00:00" --all` across all repos — stop at the first date that has at least one commit. If today has uncommitted changes and no prior day has commits, use today. If nothing is found within 14 days, tell the user and stop.
- **Repos**: if $ARGUMENTS contains a directory path, discover repos under it (`find <path> -maxdepth 3 -name ".git" -type d`). Otherwise read `~/.claude/standup-repos` (one path per line, `#` comments). If missing or empty, tell the user and stop.

## 2. Collect data

For each repo:
```bash
git -C <path> log --since="<date> 00:00:00" --until="<next-day> 00:00:00" --format="%h %s" --all
```

For uncommitted work (only when date is today or yesterday):
```bash
git -C <path> diff --stat
git -C <path> status --short
```

**Untracked files and directories** (`??` in status) are invisible to `git diff`. For each untracked entry:
- If it's a directory, list its contents and read key files (main script, query, entrypoint) to understand intent.
- If it's a single file, read the first ~40 lines.
- Treat untracked work with the same weight as staged/modified changes — it represents real effort that must appear in the standup.

Skip repos with zero commits and no uncommitted changes.

## 3. Display standup

Output the standup directly to screen — same structure as the log file below, without the YAML frontmatter. No preamble, no sign-off.

## 4. Write log file

Write to `.local-logs/standup/<YYYY-MM-DD>.md` **relative to the project working directory** (not `~/.claude/` or any other root). If the file already exists, say so and skip.

```markdown
---
date: <YYYY-MM-DD>
repos: [<repo-name>, ...]
---

# <YYYY-MM-DD>

## Done
- <grouped narrative bullet>
  `<hash>` `<hash>`
- <another bullet>
  `<hash>`

## In Progress
- **<repo-name>**: <what the uncommitted changes do>

---
**EN:** <one casual sentence covering the day's work>
**TR:** <same in Turkish, natural spoken style>
```

## 5. Backfill gaps

After writing the log, check for missing weekday entries between the earliest existing log and today:
- **First run** (no logs exist): ask how far back to go (e.g. "2 weeks", "2026-03-01", "skip")
- **Gaps found**: list missing dates, ask "backfill these? (yes/skip)"
- **Weekends**: only count as a gap if the day has commits in any repo — skip silently otherwise

Backfill writes log files only (no screen output per day). Omit `## In Progress` for backfilled days. Show one summary line when done: "Backfilled N days: <first> → <last>"

---

## Formatting rules

These apply to both screen output and log files:

- **Group by theme, not by commit.** Three alert commits become one bullet about the alert system.
- **Hashes on the next line**, indented two spaces under their bullet. Multi-repo commits serving the same purpose (e.g. submodule syncs) share a bullet.
- **`## In Progress`** appears only when there are uncommitted changes — omit the section entirely otherwise.
- **Summaries** are conversational, 1–2 sentences, as if explaining to a teammate over coffee. Not a translation of the commit log. Turkish example tone: *"redis'te analytics kısmında iyileştirmeler yaptım, broadcast fonksiyonlarının üzerinden geçtim"*
- **Describe what was accomplished**, not file names or commit messages verbatim.
- For uncommitted work, **read the diff** (tracked files) or **read the files** (untracked) to understand intent. Never describe uncommitted work solely from file paths — understand what was built.
