---
description: Show git status alongside recent commits for full context.
disable-model-invocation: true
allowed-tools: Bash
---

Run ALL of the following, in order:

1. `git log --oneline --all -10`
2. `git status`
3. `git diff --cached --stat` (only if there are staged changes)

Before drawing any conclusions about missing or lost changes, CHECK whether they appear in the recent commits on ANY branch. Do NOT claim changes were lost or need re-staging if they were already committed.
