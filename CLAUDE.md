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
│       │   ├── SKILL.md    #   working copy (base + override)
│       │   ├── source.json #   provenance + file list
│       │   ├── .upstream/  #   pristine base (last-synced upstream)
│       │   └── override.patch  # local deviations (absent if verbatim)
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
├── SKILL.md        # Working copy (what runs) = base + local override applied
├── references/…    # Other vendored upstream files (multi-file skills)
├── source.json     # Provenance tracker + file list
├── .upstream/      # Pristine base: the last-synced upstream files, verbatim (committed)
└── override.patch  # Auto-generated diff(base → working); absent when verbatim
```

**Update model (borrowed from oh-my-zsh's `upgrade_oh_my_zsh_custom`).** Instead of
blindly overwriting `SKILL.md`, a sync keeps a pristine copy of the last-synced
upstream under `.upstream/` (the *base*) and does a 3-way merge of upstream's
base→HEAD change into the working files. Local edits are replayed on top, not
clobbered — the same guarantee oh-my-zsh gets from `git pull --autostash`. Every
local deviation is recorded, human-readable, in `override.patch`, regenerated on
each sync. A genuine conflict (upstream and local editing the same lines) is left
as conflict markers in the working file and reported — never silently lost.

**source.json format:**
```json
{
  "repo": "owner/repo",
  "path": "path/to/SKILL.md",
  "files": ["SKILL.md", "references/foo.md"],
  "commit": "<pinned SHA>",
  "updated": "YYYY-MM-DD"
}
```
- `path` — upstream-repo path of the primary file. Its dirname is the upstream skill directory.
- `files` — optional, skill-dir-relative list of every vendored file. Defaults to `["SKILL.md"]`. List only upstream-tracked files; local-only artifacts (`.venv/`, gitignored) are never listed and never touched.

**Adding a new external skill:**
1. Copy the upstream skill's files into `claude/skills/<name>/`
2. Create `source.json` with `repo`, `path`, the current `commit` SHA, and (if multi-file) `files`
3. Establish the pristine base: `bash scripts/sync-external-skills.sh --establish-base <name>` — fetches the files at the pinned commit into `.upstream/` and captures any local edits as `override.patch`
4. Update README.md skills table (mark as *(external)*)

**Updating external skills:**
```bash
bash scripts/sync-external-skills.sh            # all → upstream HEAD
bash scripts/sync-external-skills.sh <name>      # one
```

The script reads each `source.json`, resolves upstream HEAD via `git ls-remote`
(no clone — file contents come from raw.githubusercontent, so a huge upstream repo
costs a few GETs), 3-way merges each listed file, advances `.upstream/`, refreshes
`override.patch`, and bumps `commit`/`updated`. On conflict it stops for that skill,
leaves markers in the working file, and does not advance the base; resolve the
markers and re-run, or `git checkout` the skill dir to abort.

To (re)build a base + patch from the current pin without pulling HEAD:
```bash
bash scripts/sync-external-skills.sh --establish-base [<name>]
```

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
