---
description: Stage your changes, draft a commit message, commit, and push.
allowed-tools: Bash, Read
---

Stage your changes, draft a commit message, then commit and push.

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

**Commit:**
- Commit with the drafted message

**Push:**
- After committing, run `git push`
- If push fails (e.g. no upstream), report the error

Present ONLY the `git log --oneline -1` output and push result. No explanation, no validation, no commentary.
