---
name: skills
description: Show every installed skill as a board — managed skills, trial skills grouped by source repo, how long each has gone unused, and what each costs in context. Use when the user asks what skills are installed, which are stale or unused, what the skills are costing, or wants to decide what to remove, pin, or promote.
---

# skills

Run `scripts/skills-view.py` in agents-shared and show the user its output.
Never reimplement the board inline, and never read the skills directory
directly to answer — the script and `trial-skill.sh` are the single
implementation, and a hand-rolled answer will disagree with them.

## Locating the script

No hardcoded paths. This skill directory is a symlink into the agents-shared
clone; resolve it:

```zsh
SKILL_DIR="$(readlink -f "$(dirname "$(readlink -f ~/.claude/skills/skills/SKILL.md)")")"
VIEW="$SKILL_DIR/../../../scripts/skills-view.py"
```

Honor `$CLAUDE_CONFIG_DIR` over `~/.claude` if set. Verify `$VIEW` exists before
use; if not, say so rather than guessing paths.

## Mapping the request

- **"what skills do I have" / "show the skills" / "/skills"** → `$VIEW`
- **"what's stale" / "what am I not using"** → `$VIEW --stale`
- **"show everything as cards"** → `$VIEW --all`

The board is ANSI art. Print it verbatim in a code block rather than
summarizing it into prose — the layout is the point, and a table rebuilt from
it loses the grouping that makes the decision obvious.

## After showing it

The board names its own actions in the footer of each group. If the user then
wants to act, hand off to [trial-skill](../trial-skill/SKILL.md) — `rm`,
`rm --repo`, `promote`, `promote --repo`, `pin`, `unpin`, `restore`. Do not
run a removal without being asked to; the view exists so the user can decide,
not so the decision gets made for them.

Two things worth saying when they come up, because neither is visible on the
board:

- **Removal is cheap.** `rm` writes repo, commit and file list to a ledger
  before deleting, so `trial-skill.sh restore <name>` refetches the exact same
  bytes. Nobody needs to agonize over removing a trial.
- **A repo is one decision.** Trials are sectioned by where they came from, so
  eleven skills pulled from one repo come and go with `rm --repo <owner/repo>`
  rather than eleven commands.
