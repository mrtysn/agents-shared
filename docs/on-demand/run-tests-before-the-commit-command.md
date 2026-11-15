# Run the tests before the commit command, not inside it

**A commit is never chained after a test run that is piped through `tail`, `head` or `grep`.**
A pipeline exits with the status of its last command, so `run-tests | tail -1 && git commit …`
commits whether the tests passed or failed.

- Run the tests as their own command and read the result.
- Then run `git status --short` on the paths you are about to commit: a pathspec commit takes each
  named file from the working tree, another session's uncommitted lines included
  ([commit only your paths](commit-only-your-paths.md)).
- Then commit, as a command of its own.
- An edit step in the same command is checked the same way: a script that failed its own assert
  changed nothing, and the commit after it takes whatever the file already held.

## Provenance

Nov 15 2026, agents-shared: one command ran a Python edit, `run-…-tests.sh | tail -1 && git commit
-- <hook>` and a push. The edit failed its assert because another session had rewritten the hook,
the tests reported 9 of 78 failing, `tail` exited 0, and the commit published that session's
unfinished rewrite under the wrong message (7503561).
