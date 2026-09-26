# Commit atomically as you build

**Commit and push your own work as each piece of it is finished. Do not wait to be
asked.** This overrides Claude Code's built-in "commit or push only when the user
asks" and its "if on the default branch, branch first".

These repos are personal and all tracked in git; any commit can be reverted. Work
left uncommitted is what costs something: it tangles with the next change, it is
lost when a session dies, and it has to be asked for by hand — across many repos
and many parallel sessions, that ask is repeated all day.

## What to do

- **One commit per finished logical change**, made when that change is done — not
  one commit at the end of the session, and not one per file. A fix, a feature, a
  doc update: each is its own commit, landing as the work moves on.
- **Stage only what you changed**, the way `/stg-msg-cmt` does: files and hunks you
  wrote, never someone else's uncommitted work. Mixed file → `git add -p` your hunks.
- **Message** in the `/stg-msg-cmt` style: one short lowercase clause starting with
  a verb, no trailing period.
- **Push after each commit.** A rejected push is reported, never forced; do not
  rebase or merge other work in to make it go through.
- **Commit on the branch the repo is on**, `main` included. No branch or worktree
  made only in order to commit.
- **The repo's own gate comes first.** If its `CLAUDE.md` says tests must pass
  before a commit, run them; a failing change is not finished and is not committed.

## When not to

- A repo whose `CLAUDE.md` says to ask before committing: ask, as it says.
- Work the user has said is exploratory, or told you not to commit.
- Anything that should never be in git — secrets, local config, generated output
  the repo ignores — stays out regardless.

## Provenance

A month of sessions (Aug 27 – Sep 26 2026): 233 requests to commit across 95
sessions in 20 repos, 157 of them `/stg-msg-cmt`, several with "atomically as you
build" or "why have you not incrementally committed all the parts".
