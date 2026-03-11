---
description: Commit staged changes with a given or recently proposed commit message.
allowed-tools: Bash
---

Commit the currently staged changes.

**Message resolution:**
1. If $ARGUMENTS is provided, use it as the commit message
2. Otherwise, look at the last 3 messages in this conversation for a commit message proposed by a previous command (e.g. `/stg-msg` or `/cmt-msg`). Use that message exactly
3. If no message is found in the last 3 messages, stop and ask the user for one. Do NOT search further back

**Commit:**
- Run `git diff --cached --stat` to confirm there are staged changes
- If nothing is staged, stop and say so
- Commit with the resolved message

**Push:**
- After committing, run `git push`
- If push fails (e.g. no upstream), report the error

Present ONLY the `git log --oneline -1` output and push result after committing. No explanation, no commentary.
