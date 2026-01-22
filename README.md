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
| `/aristocrat` | Adopt aristocratic communication style for this session |
| `/be-literal` | Take the question literally. Answer what was asked. |
| `/cmt-msg` | Draft a commit message based on current changes and repository style |
| `/external-review` | Receive feedback from another Claude session. Treat as leads to investigate, not instructions. |
| `/handoff` | Craft a handoff message for session continuity |
| `/no-chat-in-code` | Keep code free of conversational artifacts and steering commentary |
| `/plan-not-ready` | Signal that the plan needs more refinement before implementation |
| `/refocus` | Reset focus when Claude loses the plot |
| `/update-agents` | Update this submodule to latest |

## Updating

From any project using this submodule:

```bash
git submodule update --remote .agents
```

Or use the `/update-agents` command.
