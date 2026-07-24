# agents-shared

Shared Claude Code commands and skills for use across multiple projects via git submodule.

## Usage

Add as a submodule at `.agents`:

```bash
git submodule add <repo-url> .agents
```

Then symlink or reference commands from `.claude/commands/`.

### Install globally (one machine, every project)

Instead of wiring each repo up individually, symlink everything into the
user-level Claude dirs (`~/.claude/commands` and `~/.claude/skills`) so every
project on the machine sees these commands and skills:

```bash
bash scripts/init-global.sh           # sync ~/.claude with this repo
bash scripts/init-global.sh --unlink  # remove the symlinks it created
```

Idempotent — re-run after adding, renaming, or removing a command/skill. New
sources are linked, wrong-target links repaired, orphaned links (renamed/deleted
upstream) pruned, and real local override files left untouched. Honors
`CLAUDE_CONFIG_DIR` if set.

### Install local-only (per project, no repo footprint)

Symlink chosen skills from a standalone clone and hide them via
`.git/info/exclude` — no submodule, nothing in git status:

```bash
mkdir -p <repo>/.claude/skills
ln -s <clone>/claude/skills/handoff <repo>/.claude/skills/handoff
echo ".claude/skills/handoff" >> <repo>/.git/info/exclude
```

`git pull` in the clone updates all such repos at once. Exclude links by name,
not all of `.claude/`, so committed skills can coexist. Machine-local — for a
setup that travels with the repo, use the submodule. Not automated by the
scripts.

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
| `/handoff` | Craft a handoff message for session continuity. Pass a session UUID to consolidate from a past session via sub-agent. |
| `/board` | Show the Jira sprint board as a TUI kanban, or dive into a specific ticket with codebase research |
| `/caveman` | Ultra-compressed communication (~75% token savings). Levels: lite, full, ultra *(external)* |
| `/new-repo` | Create a new GitHub repo under the active `gh` account, scaffolding standard files and pushing an initial commit |
| `/recent-sessions` | List Claude Code sessions by recency with first user prompt. Recovery aid after crashes/restarts. |
| `/new-tool` | Register a script with the toolbelt — add `# DESC:`, mark executable, symlink into `~/.local/bin` |
| `/slack-gif-creator` | Constraints, validators, and animation concepts for building Slack-sized animated GIFs from scratch *(external)* |
| `/go-back` | Rewind a drifted conversation. Identifies the earliest message whose edit bypasses all subsequent drift and emits the exact replacement text. |
| `/grill-me` | User-triggered kickoff for a grilling session (delegates to `/grilling`) *(external)* |
| `/grilling` | Interview the user relentlessly about a plan or design to stress-test it before building *(external)* |
| `/socratic-quiz` | Guide the user to understanding through adaptive one-at-a-time questioning instead of direct answers *(external)* |
| `/homelab-connect` | Fetch the node01 operator runbook from its private repo before any Hetzner/Caddy/Docker/self-hosted deploy work |
| `/improve` | Survey a codebase as a senior advisor and write self-contained implementation plans for other agents to execute — read-only, never edits source *(external)* |
| `/i-have-adhd` | Shape output for an ADHD reader — lead with the next action, number steps, restate state, suppress tangents *(external)* |

## Updating

From any project using this submodule:

```bash
git submodule update --remote .agents
```

Or use the `/update-agents` command.

## External Skills

Some skills are sourced from third-party repos. Each keeps a `source.json` (upstream repo, path, file list, pinned commit) alongside a `.upstream/` pristine base and, if we've adapted it, an `override.patch`.

Updates preserve local edits the way oh-my-zsh's `upgrade_oh_my_zsh_custom` does: rather than overwriting `SKILL.md`, the sync 3-way merges upstream's change into the working files against the stored base, replaying our edits on top. Conflicts are surfaced as markers, never silently dropped.

```bash
bash scripts/sync-external-skills.sh            # all external skills → upstream HEAD
bash scripts/sync-external-skills.sh caveman     # specific skill only
bash scripts/sync-external-skills.sh --establish-base [name]  # (re)build base + patch from the pin
```

See CLAUDE.md → *External (Third-Party) Skills* for the full model.
