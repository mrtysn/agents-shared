---
description: Generate a daily standup summary, log it, and optionally backfill history.
argument-hint: [date] [path]
allowed-tools: Bash, Write, AskUserQuestion
---

Daily standup: collect the last working day's activity, display it, persist it, offer to backfill gaps.

$ARGUMENTS

---

## 1. Collect data

Run the collection script **once** to gather all git activity. It ships with
agents-shared; resolve it through the global command symlink:

```bash
SCRIPT="$(dirname "$(readlink "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/commands/standup.md")")/../../scripts/standup-collect.sh"
"$SCRIPT" [date-if-provided]
```

If $ARGUMENTS contains a directory path instead of (or in addition to) a date, pass it as the second argument:
```bash
"$SCRIPT" [date] [path]
```

The script handles:
- Finding the last day with activity (walks back up to 14 days)
- Reading `~/.claude/standup-repos` for repo list
- Collecting commits, diffs, status, and untracked file contents
- Filtering stash commits
- Checking existing log files and backfill status

If the script exits with an error, report it and stop.

## 2. Display standup

Parse the script output and produce the standup — same structure as the log file below, without the YAML frontmatter. No preamble, no sign-off.

## 3. Write log file

If the script output shows `LOG STATUS` → `MISSING`, write to `.local-logs/standup/<YYYY-MM-DD>.md` **relative to the project working directory**. If `EXISTS`, say so and skip.

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

## 4. Backfill gaps

Based on the `BACKFILL STATUS` section of the script output:

- **`NO_LOG_DIR` or `NO_EXISTING_LOGS`** (first run): ask how far back to go (e.g. "2 weeks", "2026-03-01", "skip")
- **Gaps found** between earliest log and today: list missing weekday dates, ask "backfill these? (yes/skip)"
- **Weekends**: only count as a gap if that date has commits — check by running the script with that date

For each backfill date, run the collection script with that specific date:
```bash
"$SCRIPT" <YYYY-MM-DD>
```

Backfill writes log files only (no screen output per day). Omit `## In Progress` for backfilled days. Show one summary line when done: "Backfilled N days: <first> → <last>"

---

## Formatting rules

These apply to both screen output and log files:

- **Group by theme, not by commit.** Three alert commits become one bullet about the alert system.
- **Hashes on the next line**, indented two spaces under their bullet. Multi-repo commits serving the same purpose (e.g. submodule syncs) share a bullet.
- **`## In Progress`** appears only when there are uncommitted changes — omit the section entirely otherwise.
- **Summaries** are conversational, 1–2 sentences, as if explaining to a teammate over coffee. Not a translation of the commit log. Turkish example tone: *"redis'te analytics kısmında iyileştirmeler yaptım, broadcast fonksiyonlarının üzerinden geçtim"*
- **Describe what was accomplished**, not file names or commit messages verbatim.
- For uncommitted work, the script output includes diff content and untracked file contents — use these to understand intent. Never describe uncommitted work solely from file paths.
