---
description: Draft a commit message based on current changes.
argument-hint: [optional context or scope]
allowed-tools: Bash, Read
---

Examine the repository and draft an appropriate commit message.

1. Run `git status` and `git diff` to see all current changes
2. Draft a commit message per the style below

$ARGUMENTS

**Style:** One short clause naming the single thing the commit accomplishes. Lowercase, no trailing period, under 50 characters, starting with a verb. Do not enumerate sub-changes or implementation details — implementation goes inside the commit body if it goes anywhere. Enumeration with "and" or commas is the exception, not the norm; use it only when two changes are genuinely inseparable.

Examples:
  add notifications to gamehub calls
  fix port bindings for alb
  enable remote command execution on ecs tasks
  approve team join requests if private team goes public
  improve slack messages

Present ONLY the proposed message. No explanation, no validation, no commentary. Do NOT commit.
