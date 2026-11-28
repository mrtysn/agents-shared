# Commit atomically as you build

**Commit and push your own work as each piece of it is finished. Do not wait to be
asked.** This overrides Claude Code's built-in "commit or push only when the user
asks" and its "if on the default branch, branch first".

**It holds only in the user's own repos**: those whose `origin` is under
`github.com/mrtysn`, or that have no remote. Check with `git remote get-url origin`
before the first commit in a repo. In any other repo (an employer's, a client's, an
open-source project), Claude Code's defaults apply: branch first, commit when asked,
and never push to a branch others share without asking.

The user's own repos are all tracked in git; any commit can be reverted. Work
left uncommitted is what costs something: it tangles with the next change, it is
lost when a session dies, and it has to be asked for by hand — across many repos
and many parallel sessions, that ask is repeated all day.

## What to do

- **One commit per finished logical change**, made when that change is done — not
  one commit at the end of the session, and not one per file. A fix, a feature, a
  doc update: each is its own commit, landing as the work moves on.
- **Stage only what you changed**, the way `/stg-msg-cmt` does: files and hunks you
  wrote, never someone else's uncommitted work. Commit with a pathspec
  (`git commit -m "…" -- paths`): the index is shared between sessions, and a bare
  `git commit` takes what another session staged. A pathspec commit takes each
  named file **from the working tree**, ignoring what you staged, so a file that
  also holds another session's lines never goes in a pathspec: stage your hunks
  alone (`git add -p`, or a blob built from `HEAD` via `git update-index
  --cacheinfo`), check `git diff --cached --name-only` lists only your files, then
  commit without a pathspec.
- **Message** in the `/stg-msg-cmt` style: one short lowercase clause starting with
  a verb, no trailing period.
- **Push after each commit.** A rejected push is never forced and no other work is
  merged in. When your own unpushed commits are all that is behind, replay them with
  `git pull --rebase` and push if it applies with no conflict and the repo's tests pass
  after it. A conflict, a branch others share, or a failing test is reported to the
  owner. `hooks/require-fetch-before-commit.sh` (PreToolUse) fetches before a
  `git commit` and refuses it once when the branch is behind its upstream.
- **Commit on the branch the repo is on**, `main` included. No branch or worktree
  made only in order to commit.
- **The repo's own gate comes first.** If its `CLAUDE.md` says tests must pass
  before a commit, run them; a failing change is not finished and is not committed.

## When not to

- A repo whose `CLAUDE.md` says to ask before committing: ask, as it says.
- Work the user has said is exploratory, or told you not to commit.
- A change being tried out (a layout, wording or UI adjustment the user is iterating
  on, "lets try X") is finished when the user settles on it, not at each try: commit
  the settled version.
- Anything that should never be in git — secrets, local config, generated output
  the repo ignores — stays out regardless.

## A public repo waits for approval

**Pushing to a public repo publishes, and a force-push does not take it back.** New
personal information goes to one only after the user approves each item: names of
people or companies, contact addresses, clients, business terms or prices, unreleased
projects, private repos described, pictures of private work. A private tool repo's bare
name is fine. A name that is itself a company, client, person or unreleased project is
never pushed to a public repo: the local denylist read by agents-shared's `githooks/pre-push`
refuses it. Commit it locally, show
the user the list, ask with AskUserQuestion, and push only what they approve; the rest
waits on a branch with no upstream. `hooks/require-approval-before-public-push.py`
refuses a push to a public GitHub repo whose command carries neither
`# public-push: no personal content` (refused anyway when an image or other media goes
out) nor `# public-push: user approved "<their words>"`.

Provenance: [docs/provenance/commit-atomically-as-you-build.md](../../docs/provenance/commit-atomically-as-you-build.md).
