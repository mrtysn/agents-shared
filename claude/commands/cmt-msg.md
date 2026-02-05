---
description: Draft a commit message based on current changes and repository style.
allowed-tools: Bash, Read
---

Examine the repository and draft an appropriate commit message.

1. Run `git log --oneline -15` to observe the commit message style
2. Run `git status` and `git diff` to see all current changes
3. Draft a commit message that matches the repository's conventions

$ARGUMENTS

**Format constraint:** Single line, lowercase, no trailing period. Start with a verb (add/fix/update/refactor/implement). Join multiple changes with "and" or commas.

Present ONLY the proposed message. No explanation, no validation, no commentary. Do NOT commit.
