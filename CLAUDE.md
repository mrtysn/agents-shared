# CLAUDE.md

This repository contains shared Claude Code commands for use across multiple projects via git submodule.

## Project Structure

```
agents-shared/
├── claude/
│   └── commands/          # Slash command definitions
│       ├── aristocrat.md  # Communication style directive
│       ├── cmt-msg.md     # Commit message drafting
│       ├── handoff.md     # Session continuity handoffs
│       ├── refocus.md     # Focus reset when off-track
│       └── update-agents.md  # Submodule self-update
└── README.md
```

## Command File Format

Commands are markdown files with YAML frontmatter:

```markdown
---
description: Short description shown in command list
allowed-tools: Read, Glob, Grep  # Optional: restrict available tools
---

Command instructions here. Use $ARGUMENTS for user-provided arguments.
```

**Frontmatter Fields:**
- `description` — Required. Appears in `/help` and command listings.
- `allowed-tools` — Optional. Comma-separated list restricting which tools the command can use. Omit for full access.

## Adding New Commands

1. Create `claude/commands/<command-name>.md`
2. Add frontmatter with description
3. Write clear, imperative instructions
4. Update README.md command table

**Naming:** Use lowercase kebab-case (e.g., `my-command.md` → `/my-command`).

## Design Principles

- **Self-contained** — Commands should work without external dependencies
- **Consistent tone** — Favor the aristocratic bearing established in existing commands
- **Explicit instructions** — Tell Claude what to do, not what to think about
- **Format specifications** — Include output format when structure matters

## Integration Pattern

Projects integrate via submodule at `.agents`:

```bash
# Add to a project
git submodule add <repo-url> .agents

# Reference from .claude/commands/ via symlink or copy
ln -s ../../.agents/claude/commands/handoff.md .claude/commands/handoff.md
```

## Testing Commands

Test commands by invoking them in a Claude Code session:

```
/aristocrat
/handoff
/refocus
```

Verify the output matches expected behavior and tone.
