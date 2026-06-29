---
description: Stage your changes, draft a commit message, commit, and push.
allowed-tools: Bash, Read
---

Stage the appropriate changes, draft a commit message, then commit and push.
Run `git status` and `git diff` first to see everything.

The user's instruction for this invocation (may be empty):

> $ARGUMENTS

## What to stage — resolve in order, stop at the first that applies

1. If the instruction above gives a scope ("your changes only", "the API files", "everything"), it is authoritative: stage exactly what it names, exclude the rest, and ask nothing. Any other directive it gives also overrides the defaults below.
2. Otherwise, stage the files you changed this session (clear memory of editing them).
3. Only for files you cannot attribute (changed before your session, or context was compacted) **and** that no scope covers — list them briefly and ask the user whether to include them.

**Safety (always):**
- Never unstage anything that was staged before you started.
- Never use `git checkout`, `git restore`, or any destructive command to revert or clean files — uncommitted changes you didn't make are the user's work.
- For files with mixed (yours + theirs) hunks, use `git add -p` to stage only your hunks; if that's not feasible, ask how to proceed.
- After staging, run `git diff --cached` to confirm.

## Commit message

**Style:** One short clause naming the single thing the commit accomplishes. Lowercase, no trailing period, under 50 characters, starting with a verb. Do not enumerate sub-changes or implementation details — implementation goes inside the commit body if it goes anywhere. Enumeration with "and" or commas is the exception, not the norm; use it only when two changes are genuinely inseparable.

Examples:
  add notifications to gamehub calls
  fix port bindings for alb
  enable remote command execution on ecs tasks
  approve team join requests if private team goes public
  improve slack messages

## Commit & push

- Commit with the drafted message.
- Run `git push`; if it fails (e.g. no upstream), report the error.

Present ONLY the `git log --oneline -1` output and push result. No explanation, no validation, no commentary.
