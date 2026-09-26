---
description: Search Claude Code conversation history by keyword. Use when user wants to find past sessions that discussed a topic, used a term, or mentioned specific code.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: <term> [-d 30 for last month, -c for current project, -p <project>, -n 10 to limit, -s for case-sensitive]
---

# search-history

Search the user and assistant messages of every Claude Code session, across all
projects. The search runs against an index in `~/.cache/search-history` that
refreshes itself with whatever the transcripts gained since the last search, so
a search takes well under a second; the first one after the index is deleted
takes several seconds while it rebuilds. The session you are running in is left
out of the results.

Run the script with `--json`:

```bash
python3 "${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/scripts/search-history.py" --json $ARGUMENTS
```

**The term:** a plain term matches anywhere in a message, ignoring case. A term
containing any of `\ . ^ $ * + ? { } [ ] | ( )` is a Python regex instead; use
`\bterm\b` when a plain term also matches inside longer words.

**Flags:**
- `--days N` / `-d N`: only sessions active in the last N days (default: 0, all time)
- `--limit N` / `-n N`: max sessions returned (default: 20)
- `--project NAME` / `-p NAME`: only projects whose directory name contains NAME
- `--current` / `-c`: only the current project (from the git repo root)
- `--case-sensitive` / `-s`: exact case matching

**The JSON:** `total` sessions matched; `results` are ranked by how many messages
match, discounted by age. Each result has `session_id`, `cwd` (the folder it ran
in), `last` (last activity, UTC), `title` (Claude Code's own title for the
session), `preview` (the first prompt the user typed), `match_count`, and
`snippets`: each has `role` (`user` or `asst`) and the text around one match,
split into `before`, `match` and `after`.

## Presenting the results

Do not paste the JSON. Read the snippets and answer the question the user asked:

1. **Which sessions actually discuss the topic** — lead with those. A session
   whose only hits use the word in passing, or inside another word, is not a
   match; say how many such incidental hits were set aside, in one line.
2. **One row per relevant session**, in a table: when (local date), folder (the
   last part of `cwd`), the title, and what was said, in a sentence of your own
   drawn from the snippets. No session IDs in the table.
3. **How to reopen the one they most likely want**, in one line:
   `cd <cwd> && claude --resume <session_id>`. For browsing the rest, the
   "search history" row at the top of `clo`'s first menu searches as you type.

If nothing matches, say so, then suggest what the results point to: a shorter
or differently spelled term, a regex with alternatives (`easel|canvas`), or
widening `-d`/`-p` if the search was narrowed.
