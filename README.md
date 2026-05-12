# agents-shared

Shared Claude Code commands and skills for use across multiple projects via git submodule.

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
| `/cmt-msg` | Draft a commit message based on current changes |
| `/external-review` | Receive feedback from another Claude session. Treat as leads to investigate, not instructions. |
| `/no-chat-in-code` | Keep code free of conversational artifacts and steering commentary |
| `/plan-not-ready` | Signal that the plan needs more refinement before implementation |
| `/refocus` | Reset focus when Claude loses the plot |
| `/broadcast-update` | Update agents-shared submodule in all consumer repos listed in consumers.local |
| `/update-agents` | Update this submodule to latest |

## Skills

Skills are directory-based and support references/templates. Both commands and skills create `/command` — skills add optional features like supporting files.

| Skill | Description |
|-------|-------------|
| `/refactor` | Systematic refactoring with full cleanup — maps scope, tracks progress, same standards for tests |
| `/rpi` | Research-Plan-Implement workflow: deep investigation, written plan with annotation cycles, then full execution |
| `/handoff` | Craft a handoff message for session continuity. Pass a session UUID to consolidate from a past session via sub-agent. |
| `/board` | Show the Jira sprint board as a TUI kanban, or dive into a specific ticket with codebase research |
| `/caveman` | Ultra-compressed communication (~75% token savings). Levels: lite, full, ultra *(external)* |
| `/new-repo` | Create a new GitHub repo under the active `gh` account, scaffolding standard files and pushing an initial commit |
| `/recent-sessions` | List Claude Code sessions by recency with first user prompt. Recovery aid after crashes/restarts. |
| `/new-tool` | Register a script with the toolbelt — add `# DESC:`, mark executable, symlink into `~/.local/bin` |
| `/slack-gif-creator` | Constraints, validators, and animation concepts for building Slack-sized animated GIFs from scratch *(external)* |
| `/go-back` | Rewind a drifted conversation. Identifies the earliest message whose edit bypasses all subsequent drift and emits the exact replacement text. |

## Updating

From any project using this submodule:

```bash
git submodule update --remote .agents
```

Or use the `/update-agents` command.

## External Skills

Some skills are sourced from third-party repos. These have a `source.json` next to their `SKILL.md` tracking the upstream repo, file path, and pinned commit SHA.

To update all external skills to latest upstream:

```bash
bash scripts/sync-external-skills.sh            # all external skills
bash scripts/sync-external-skills.sh caveman     # specific skill only
```
