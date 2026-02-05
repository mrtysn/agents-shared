# CLAUDE.md

This repository contains shared Claude Code commands for use across multiple projects via git submodule.

## Project Structure

```
agents-shared/
├── claude/
│   ├── commands/          # Slash commands (single-file format)
│   │   ├── aristocrat.md
│   │   ├── cmt-msg.md
│   │   ├── handoff.md
│   │   ├── refocus.md
│   │   └── update-agents.md
│   └── skills/            # Skills (directory format, supports references/templates)
│       └── refactor/
│           └── SKILL.md
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

## Adding New Skills

1. Create `claude/skills/<skill-name>/SKILL.md`
2. Add frontmatter with description
3. Write clear, imperative instructions
4. Optionally add supporting files (references, templates)
5. Update README.md skills table

**Naming:** Use lowercase kebab-case (e.g., `my-skill/SKILL.md` → `/my-skill`).

Skills support additional features: reference files, templates, and advanced frontmatter (`context: fork`, `agent`, etc.).

## Adding New Commands

1. Create `claude/commands/<command-name>.md`
2. Add frontmatter with description
3. Write clear, imperative instructions
4. Update README.md command table

**Naming:** Use lowercase kebab-case (e.g., `my-command.md` → `/my-command`).

**Note:** Both formats create identical `/command` invocations. Use commands for simple single-file definitions; use skills when you need supporting files.

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

# Symlink skills
ln -s ../../.agents/claude/skills/refactor .claude/skills/refactor

# Symlink commands
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
