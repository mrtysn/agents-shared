---
description: Set up agents-shared as a submodule and symlink commands directory.
argument-hint: [git remote url]
disable-model-invocation: true
allowed-tools: Bash
---

Set up the shared Claude Code commands from the `.agents` submodule.

**Steps:**

1. Check if `.agents/` already exists. If so, verify it's a valid submodule and skip to step 3.

2. Add the submodule:
   - If $ARGUMENTS contains a git URL, use it: `git submodule add <url> .agents`
   - Otherwise, error with: "Provide the agents-shared repo URL: `/setup-agents git@github.com:user/agents-shared.git`"

3. Verify `.agents/claude/commands/` exists.

4. Handle `.claude/commands/`:
   - If it's already a symlink pointing to `../.agents/claude/commands` — done, report success
   - If it's a directory with files:
     - Check each file: if it also exists in `.agents/claude/commands/`, it's a duplicate and can be removed
     - If any files do NOT exist in `.agents/claude/commands/`, they are repo-specific — move them to `.claude/skills/<name>/SKILL.md` (strip `.md`, create directory, rename file)
     - Once directory is empty, remove it
   - If it doesn't exist, proceed

5. Create the symlink: `ln -s ../.agents/claude/commands .claude/commands`

6. Verify the symlink resolves and list available commands.

7. Report:
   - Commands available via submodule
   - Any repo-specific files moved to `.claude/skills/`
   - Any errors encountered
