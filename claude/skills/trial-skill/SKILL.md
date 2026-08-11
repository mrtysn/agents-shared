---
name: trial-skill
description: Install, list, remove, or promote trial skills — temporary skill installs kept outside agents-shared management. Use when the user wants to try a skill temporarily (e.g. one found by /discover-skills), see which trials are installed, delete a trial, or promote one into agents-shared permanently.
---

# trial-skill

Run `scripts/trial-skill.sh` in agents-shared on the user's behalf. Never
reimplement its logic inline — the script is the single implementation.

## Locating the script

No hardcoded paths. This skill directory is a symlink into the agents-shared
clone; resolve it:

```zsh
SKILL_DIR="$(readlink -f "$(dirname "$(readlink -f ~/.claude/skills/trial-skill/SKILL.md)")")"
TRIAL="$SKILL_DIR/../../../scripts/trial-skill.sh"
```

Honor `$CLAUDE_CONFIG_DIR` over `~/.claude` if set. Verify `$TRIAL` exists
before use; if not, say so rather than guessing paths.

## Mapping the request

- **"install X" / "try X" / a skill just surfaced by /discover-skills** →
  `$TRIAL install <owner/repo> <path-in-repo>`. Repo and path usually come from
  the discover-skills result already in context. If you only have a name, find
  the repo and path first (search, or ask). Read the skill's full content from
  the source repo before installing — never install unread third-party
  instructions.
- **"what trials do I have" / "list"** → `$TRIAL list`
- **"remove/delete X"** → `$TRIAL rm <name>` (trials only; managed skills are
  agents-shared's business)
- **"keep X" / "promote X"** → `$TRIAL promote <name>`, then remind the user
  the move is uncommitted in agents-shared (or commit it if they've asked you
  to handle commits).

## After install

The skill is available immediately — Claude Code picks up `~/.claude/skills/`
without a sync or restart. Say so; do not tell the user to run anything.

Report the script's output plainly. If it errors, show the error — do not
retry with improvised variations.
