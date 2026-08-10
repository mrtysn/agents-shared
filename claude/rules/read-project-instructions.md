# Read a repo's instructions before acting in it

**Before the first command that runs a repo's own scripts or modifies its files,
read that repo's `CLAUDE.md`** — whenever the repo is *below* the directory the
session launched from.

## Why this is a real trap, not a platitude

CLAUDE.md files in the launch directory and its ancestors load at startup.
Files in **subdirectories load lazily — only when Claude reads a file in that
subdirectory.** A `Bash` call is not a read. So this sequence looks fine and isn't:

    session launched in ~/dev
    Bash: cd ~/dev/some-repo && ./scripts/do-thing.sh     ← instructions NOT loaded
    Read: ~/dev/some-repo/something.md                    ← instructions arrive, too late

The project's rules show up in context *after* the command that violated them.
A repo forbidding exactly that script, or requiring a flag, or reserving the
action for the user, is invisible until something reads a file there.

## The habit

When the task moves into a repo other than the launch directory, and before the
first Bash command that builds, deploys, installs, symlinks outside the repo, or
runs anything in `scripts/`:

    Read <repo>/CLAUDE.md        (also .claude/CLAUDE.md if present)

One read. Batch it with whatever else that step needs. Skip it for read-only
inspection — `git status`, `ls`, `grep` — which cannot violate anything.

## The structural fix

Launch the session from the repo root. Then its CLAUDE.md, `.claude/rules/`, and
`.claude/settings.local.json` all load at startup and this cannot happen. Launching
from a parent directory that merely *contains* repos is for cross-repo work, and it
is precisely the case where this rule has to be applied by hand.
