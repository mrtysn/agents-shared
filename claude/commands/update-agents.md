---
description: Update the agents-shared submodule to latest and refresh symlinks.
allowed-tools: Bash
---

Update the .agents submodule to the latest commit and refresh command symlinks.

**Steps:**

1. Run `git submodule update --remote .agents`

2. Refresh symlinks in `.claude/commands/`:
   - For each `.md` file in `.agents/claude/commands/`:
     - If no file exists in `.claude/commands/`, create relative symlink
     - If it's already a correct symlink, skip
     - If it's a regular file (repo-specific override), skip and note it
   - Remove any broken symlinks (pointing to files that no longer exist in .agents)

3. Check if the submodule pointer changed with `git status`

4. If changed, commit with message: `chore: update agents-shared submodule`

5. Report:
   - New commits pulled in (if any)
   - New commands added via symlinks (if any)
   - Repo-specific overrides preserved (if any)
   - Broken symlinks removed (if any)

If no changes, report that everything is already up to date.

**Important**: Use relative symlinks (`../../.agents/...`) not absolute paths.

$ARGUMENTS
