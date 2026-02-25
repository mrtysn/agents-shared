---
description: Update the agents-shared submodule to latest.
disable-model-invocation: true
allowed-tools: Bash
---

Update the `.agents` submodule to the latest remote commit.

**Steps:**

1. Verify `.agents/` exists and is a submodule. If not, error with instructions to run `/setup-agents`.

2. Pull latest in the submodule:
   ```bash
   git -C .agents pull
   ```

3. Verify `.claude/commands` is a symlink to `../.agents/claude/commands`. If not, warn that the setup may be outdated and suggest running `/setup-agents`.

4. List any new or removed commands compared to before the update.

5. Check if the submodule pointer changed with `git diff .agents`.

6. Report:
   - New commands added (if any)
   - Commands removed (if any)
   - Whether the submodule pointer needs committing

$ARGUMENTS
