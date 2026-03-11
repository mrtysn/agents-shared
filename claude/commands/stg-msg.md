---
description: Stage only your own changes, leave the rest untouched, and draft a commit message.
allowed-tools: Bash, Read
---

Stage ONLY the changes you made during this session. Leave all other staged or unstaged changes exactly as they were.

1. Run `git log --oneline -15` to observe the commit message style
2. Run `git status` and `git diff` to identify all current changes
3. Determine which files and hunks you modified — stage only those using `git add` (use `git add -p` for partial files if needed)
4. Do NOT unstage anything that was already staged before your changes
5. Do NOT stage changes that existed before this session
6. Run `git diff --cached` to confirm only your changes are staged

Then draft a commit message for the staged changes.

$ARGUMENTS

**Format constraint:** Single line, lowercase, no trailing period. Start with a verb (add/fix/update/refactor/implement). Join multiple changes with "and" or commas.

Present ONLY the proposed message after staging. No explanation, no validation, no commentary. Do NOT commit.
