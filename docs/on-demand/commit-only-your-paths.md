# Commit only your own paths

**Commit with a pathspec: `git commit -m "msg" -- path1 path2`.** A plain `git commit` takes the
whole index, and the index is shared with every other session in the same repo: anything another
session staged, a rename or a deletion included, goes into your commit under your message.

- Before committing, run `git diff --cached --name-only`. If it lists a file you did not change,
  do not commit with a bare `git commit`.
- `git add` followed by `git commit` in one command does not give you the chance to look. Check
  first, or use the pathspec form, which commits only the named paths whatever else is staged.
- If it already happened: the commit is pushed history, so do not rewrite it. Tell the session
  whose work it was (what was included, the commit, how to restore), per
  [messages between sessions](messages-between-sessions.md).

## Provenance

Oct 20 2026, link-keeper: a session added its own files and ran `git commit` in one chain. The index
also held two file deletions staged by another session (a rename in progress); they went into the
commit and were pushed. The user: "fix the problems you have caused claude and make sure you never
repeat them again".
