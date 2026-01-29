---
description: Set up agents-shared symlinks in current project
allowed-tools: Bash
---

Set up the shared Claude Code commands from the `.agents` submodule.

**Prerequisites**: The `.agents` submodule must already be added to the project:
```bash
git submodule add <agents-shared-repo-url> .agents
```

**Steps:**

1. Verify `.agents/claude/commands/` exists. If not, error with instructions to add the submodule.

2. Create `.claude/commands/` directory if it doesn't exist.

3. For each `.md` file in `.agents/claude/commands/`:
   - Check if a file with the same name exists in `.claude/commands/`
   - If it's already a symlink pointing to the correct location, skip
   - If it's a regular file (repo-specific override), skip and note it
   - Otherwise, create a relative symlink: `ln -s ../../.agents/claude/commands/<file>.md .claude/commands/<file>.md`

4. Report:
   - How many symlinks were created
   - Any repo-specific overrides that were preserved
   - Any errors encountered

**Important**: Use relative symlinks (`../../.agents/...`) not absolute paths, for portability.

$ARGUMENTS
