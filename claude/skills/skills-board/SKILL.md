---
name: skills-board
description: Show every installed skill as a board — managed skills, trial skills grouped by source repo, how long each has gone unused, and what each costs in context. Use when the user asks what skills are installed, which are stale or unused, what the skills are costing, or wants to decide what to remove, pin, or promote.
---

# skills-board

Run `scripts/skills-view.py --html` in agents-shared, open the page it writes,
and give the user its path. Never reimplement the board inline, and never read
the skills directory directly to answer — the script and `trial-skill.sh` are
the single implementation, and a hand-rolled answer will disagree with them.

The board is a page rather than chat output because it is a decision aid over
dozens of entries: it needs the full descriptions, dates and copyable commands,
and it has to stay open while the user acts in the terminal. Chat can do none
of that, and a text board pasted into a pane of unknown width shears.

## Locating the script

No hardcoded paths. This skill directory is a symlink into the agents-shared
clone; resolve it:

```zsh
SKILL_DIR="$(readlink -f "$(dirname "$(readlink -f ~/.claude/skills/skills-board/SKILL.md)")")"
VIEW="$SKILL_DIR/../../../scripts/skills-view.py"
FOCUS="$SKILL_DIR/../../../hooks/focus-policy.sh"
```

Honor `$CLAUDE_CONFIG_DIR` over `~/.claude` if set. Verify `$VIEW` exists before
use; if not, say so rather than guessing paths.

## Mapping the request

- **"what skills do I have" / "show the skills" / "/skills-board"** → `$VIEW --html`
- **"what's stale" / "what am I not using"** → `$VIEW --stale --html`

Both print the path of the page they wrote. Then:

```zsh
PAGE="$($VIEW --html)"
"$FOCUS" --check && open "$PAGE"
```

The `open` is gated on the machine's focus policy: a browser tab steals focus,
and on a DENY machine the user gets the path instead and opens it themselves.

## What to say

One or two lines: the absolute path of the page on its own line, and the
headline the page's footer gives — the stale count, or that nothing is stale.
Do not reprint the board, and do not summarise the cards; the page is the
summary.

The plain-text board (`$VIEW` with no flag) still exists for the user's own
shell, where it sizes itself to the real terminal. It is not for pasting into
chat.

## After showing it

The page names its own actions under each group, with a copy button on every
command, and selecting cards composes one `rm`, `pin`, `unpin` or `promote`
line for the set. If the user then wants to act, hand off to
[trial-skill](../trial-skill/SKILL.md) — `rm`, `rm --repo`, `promote`,
`promote --repo`, `pin`, `unpin`, `restore`. Do not run a removal without being
asked to; the board exists so the user can decide, not so the decision gets
made for them.

Two things worth saying when they come up, because neither is visible on the
board:

- **Removal is cheap.** `rm` writes repo, commit and file list to a ledger
  before deleting, so `trial-skill.sh restore <name>` refetches the exact same
  bytes. Nobody needs to agonize over removing a trial.
- **A repo is one decision.** Trials are sectioned by where they came from, so
  eleven skills pulled from one repo come and go with `rm --repo <owner/repo>`
  rather than eleven commands.
