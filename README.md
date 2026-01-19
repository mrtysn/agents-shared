# agents-shared

Shared Claude Code commands for use across multiple projects via git submodule.

## Usage

Add as a submodule at `.agents`:

```bash
git submodule add <repo-url> .agents
```

Then symlink or reference commands from `.claude/commands/`.

## Commands

| Command | Description |
|---------|-------------|
| `/cmt-msg` | Draft a commit message based on current changes and repository style |
| `/handoff` | Craft a handoff message for session continuity |
| `/refocus` | Reset focus when Claude loses the plot |
| `/update-agents` | Update this submodule to latest |

## Updating

From any project using this submodule:

```bash
git submodule update --remote .agents
```

Or use the `/update-agents` command.
