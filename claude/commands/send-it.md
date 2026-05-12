---
description: Stage all changes, commit, and push — no deliberation.
allowed-tools: Bash, Read
---

Stage everything, commit, and push.

1. Run `git status` to see what's there
2. `git add -A`
3. Run `git diff --cached --stat` for a quick summary
4. Draft a commit message based on the staged diff

$ARGUMENTS

**Style:** One short clause naming the single thing the commit accomplishes. Lowercase, no trailing period, under 50 characters, starting with a verb. Do not enumerate sub-changes or implementation details — implementation goes inside the commit body if it goes anywhere. Enumeration with "and" or commas is the exception, not the norm; use it only when two changes are genuinely inseparable.

Examples:
  add notifications to gamehub calls
  fix port bindings for alb
  enable remote command execution on ecs tasks
  approve team join requests if private team goes public
  improve slack messages

5. Commit with the drafted message
6. `git push` — if push fails (e.g. no upstream), set upstream and retry

Present ONLY the `git log --oneline -1` output and push result. No explanation, no validation, no commentary.
