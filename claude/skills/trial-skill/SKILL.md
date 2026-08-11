---
name: trial-skill
description: Install, remove, pin, restore, or promote trial skills — temporary skill installs kept outside agents-shared management. Use when the user wants to try a skill temporarily (e.g. one found by /discover-skills), delete or bring back a trial, stop one aging out, or promote one into agents-shared permanently. For seeing what is installed and what has gone stale, use /skills instead.
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
  When installing several skills from one repo in one go, pass the same
  `--group <owner/repo>` to each. A group is removed or promoted with one
  command later, which is the difference between one decision and eleven.
- **"what trials do I have" / "list"** → prefer the [skills](../skills/SKILL.md)
  board, which shows trials, managed skills, idle age and context cost together.
  `$TRIAL list` is the plain fallback; `$TRIAL list --json` is the board's data
  source, not something to show a human.
- **"remove/delete X"** → `$TRIAL rm <name>`, or `$TRIAL rm --group <g>` for a
  set (trials only; managed skills are agents-shared's business). Mention that
  `restore` brings it back — removal is not a decision worth agonizing over.
- **"bring back X" / "I removed X by mistake"** → `$TRIAL restore <name>`,
  which refetches at the commit recorded when it was removed.
- **"stop nagging me about X" / "I'll want X later"** → `$TRIAL pin <name>`.
  A pinned trial never reports stale. `unpin` reverses it.
- **"keep X" / "promote X"** → `$TRIAL promote <name>` (or `--group <g>`), then
  remind the user the move is uncommitted in agents-shared (or commit it if
  they've asked you to handle commits).

## After install

The skill is available immediately — Claude Code picks up `~/.claude/skills/`
without a sync or restart. Say so; do not tell the user to run anything.

## Staleness

A trial's `last_used` is stamped by the `Skill` PostToolUse hook, so idle age
means "unused for N days", not "installed N days ago". Past 30 days idle
(`TRIAL_STALE_DAYS`) a trial is reported stale by the board. Nothing deletes it
— the view is the pressure to clean up, and the decision stays the user's.

Report the script's output plainly. If it errors, show the error — do not
retry with improvised variations.
