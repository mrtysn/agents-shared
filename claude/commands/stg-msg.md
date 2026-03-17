---
description: Stage only your own changes, leave the rest untouched, and draft a commit message.
allowed-tools: Bash, Read
---

Stage your changes and draft a commit message.

1. Run `git log --oneline -15` to observe the commit message style
2. Run `git status` and `git diff` to identify all current changes
3. Categorize each changed/untracked file:
   - **Yours** — files you created or modified in this session (you have clear memory of changing them)
   - **Uncertain** — files you cannot confidently attribute to yourself (modified before your session, or context was compacted)
4. Stage all files you are confident are yours using `git add`
5. For uncertain files: **ask the user** whether to include them. List the files and their changes briefly.
6. Do NOT unstage anything that was already staged before your changes
7. After the user responds (or if there are no uncertain files), run `git diff --cached` to confirm

Then draft a commit message for the staged changes.

$ARGUMENTS

**Format constraint:** Single line, lowercase, no trailing period. Start with a verb (add/fix/update/refactor/implement). Join multiple changes with "and" or commas.

Present ONLY the proposed message after staging. No explanation, no validation, no commentary. Do NOT commit.
