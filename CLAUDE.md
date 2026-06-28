# CLAUDE.md

This repository contains shared Claude Code commands for use across multiple projects via git submodule.

## Project Structure

```
agents-shared/
├── claude/
│   ├── commands/          # Slash commands (single-file format)
│   │   ├── aristocrat.md
│   │   ├── be-literal.md
│   │   ├── broadcast-update.md
│   │   ├── cmt-msg.md
│   │   ├── external-review.md
│   │   ├── no-chat-in-code.md
│   │   ├── plan-not-ready.md
│   │   ├── refocus.md
│   │   ├── setup-agents.md
│   │   ├── standup.md
│   │   └── update-agents.md
│   └── skills/            # Skills (directory format, supports references/templates)
│       ├── caveman/       # (external) Token-compressed communication
│       │   ├── SKILL.md
│       │   └── source.json
│       ├── handoff/
│       │   └── SKILL.md
│       ├── refactor/
│       │   └── SKILL.md
│       └── rpi/
│           └── SKILL.md
├── scripts/
│   ├── init.sh            # Bootstrap submodule + per-repo .claude/ symlinks (one consumer repo)
│   ├── init-global.sh     # Symlink into user-level ~/.claude (every project on the machine)
│   ├── sync-external-skills.sh  # Fetch latest from upstream repos
│   └── update-consumers.sh  # Broadcast updates to all consumer repos
├── consumers.local        # (gitignored) Absolute paths of consumer repos
├── README.md
└── CLAUDE.md
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

**Note:** Commands and skills both create `/command` invocations. Per the [Anthropic docs](https://code.claude.com/docs/en/skills), commands are merged into skills and skills are recommended (commands are not deprecated and keep working). **New extensions here go in `claude/skills/<name>/SKILL.md`.** Existing commands stay as-is.

## External (Third-Party) Skills

Skills sourced from external repos follow a convention:

```
claude/skills/<skill-name>/
├── SKILL.md        # Copied from upstream
└── source.json     # Provenance tracker
```

**source.json format:**
```json
{
  "repo": "owner/repo",
  "path": "path/to/SKILL.md",
  "commit": "<pinned SHA>",
  "updated": "YYYY-MM-DD"
}
```

**Adding a new external skill:**
1. Clone the source repo, locate the SKILL.md
2. Create `claude/skills/<name>/SKILL.md` with the content
3. Create `claude/skills/<name>/source.json` with repo, path, and current commit SHA
4. Update README.md skills table (mark as *(external)*)

**Updating external skills:**
```bash
bash scripts/sync-external-skills.sh            # all
bash scripts/sync-external-skills.sh <name>      # one
```

The script clones each source repo at HEAD, compares the commit SHA, and copies the updated file if changed.

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
ln -s ../../.agents/claude/commands/aristocrat.md .claude/commands/aristocrat.md
```

## Testing Commands

Test commands by invoking them in a Claude Code session:

```
/aristocrat
/handoff
/refocus
```

Verify the output matches expected behavior and tone.
