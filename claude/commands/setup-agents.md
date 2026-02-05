---
description: Set up agents-shared symlinks in current project
allowed-tools: Bash
---

Set up the shared Claude Code commands and skills from the `.agents` submodule.

**Prerequisites**: The `.agents` submodule must already be added to the project:
```bash
git submodule add <agents-shared-repo-url> .agents
```

**Steps:**

1. Verify `.agents/claude/commands/` exists. If not, error with instructions to add the submodule.

2. Create `.claude/commands/` directory if it doesn't exist.

3. For each `.md` file in `.agents/claude/commands/`:
   - If it's already a correct symlink, skip
   - If it's a regular file (repo-specific override), skip and note it
   - Otherwise, create a relative symlink: `ln -s ../../.agents/claude/commands/<file>.md .claude/commands/<file>.md`

4. Create `.claude/skills/` directory if it doesn't exist.

5. For each subdirectory in `.agents/claude/skills/`:
   - If it's already a correct symlink, skip
   - If it's a regular directory (repo-specific override), skip and note it
   - Otherwise, create a relative symlink: `ln -s ../../.agents/claude/skills/<dir> .claude/skills/<dir>`

6. Report:
   - How many command symlinks were created
   - How many skill symlinks were created
   - Any repo-specific overrides that were preserved
   - Any errors encountered

**Important**: Use relative symlinks (`../../.agents/...`) not absolute paths, for portability.

$ARGUMENTS
