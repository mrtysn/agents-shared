---
description: Update the agents-shared submodule to latest and commit the change.
allowed-tools: Bash
---

Update the .agents submodule to the latest commit from the remote repository.

**Steps:**

1. Run `git submodule update --remote .agents`
2. Check if the submodule pointer changed with `git status`
3. If changed, commit with message: `chore: update agents-shared submodule`
4. Report what was updated (show the new commits pulled in)

If no changes, report that the submodule is already up to date.

$ARGUMENTS
