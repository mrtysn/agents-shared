---
description: Stage all changes, commit, and push — no deliberation.
allowed-tools: Bash, Read
---

Stage everything, commit, and push.

1. Run `git log --oneline -10` to observe the commit message style
2. Run `git status` to see what's there
3. `git add -A`
4. Run `git diff --cached --stat` for a quick summary
5. Draft a commit message based on the staged diff

$ARGUMENTS

**Format constraint:** Single line, lowercase, no trailing period. Start with a verb (add/fix/update/refactor/implement). Join multiple changes with "and" or commas.

6. Commit with the drafted message
7. `git push` — if push fails (e.g. no upstream), set upstream and retry

Present ONLY the `git log --oneline -1` output and push result. No explanation, no validation, no commentary.
