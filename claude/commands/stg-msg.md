---
description: Stage only your own changes, leave the rest untouched, and draft a commit message.
allowed-tools: Bash, Read
---

Stage your changes and draft a commit message.

1. Run `git status` and `git diff` to identify all current changes
2. Categorize each changed/untracked file:
   - **Yours** — files you created or modified in this session (you have clear memory of changing them)
   - **Uncertain** — files you cannot confidently attribute to yourself (modified before your session, or context was compacted)
3. Stage all files you are confident are yours using `git add`
4. For uncertain files: **ask the user** whether to include them. List the files and their changes briefly.
5. Do NOT unstage anything that was already staged before your changes
6. After the user responds (or if there are no uncertain files), run `git diff --cached` to confirm

Then draft a commit message for the staged changes.

$ARGUMENTS

**Style:** One short clause naming the single thing the commit accomplishes. Lowercase, no trailing period, under 50 characters, starting with a verb. Do not enumerate sub-changes or implementation details — implementation goes inside the commit body if it goes anywhere. Enumeration with "and" or commas is the exception, not the norm; use it only when two changes are genuinely inseparable.

Examples:
  add notifications to gamehub calls
  fix port bindings for alb
  enable remote command execution on ecs tasks
  approve team join requests if private team goes public
  improve slack messages

Present ONLY the proposed message after staging. No explanation, no validation, no commentary. Do NOT commit.
