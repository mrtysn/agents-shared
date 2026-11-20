# Tools that change the owner's data

**A tool that sorts, tags, moves or deletes the owner's files, links or records must never
lose a decision and never destroy by surprise.** This holds for a script, a Mac app, a game
save and a web tool alike. Examples below are made up: a photo folder, saved links, a save file.

## Decisions

- **Write each decision to an append-only log at once**, before the next item shows. Lists
  and counts are derived from the log; an undo is one more line. Closing the window or
  killing the process loses nothing.
- **Key an item by its path or URL, and give it a short stable id from that key.** Never
  by its place in a sorted list: after a file is added the same number names another file.
- **One writer per state folder.** A second process on the same folder refuses to write.
- **Back up before any rewrite**, and keep dated copies of the decisions (a month is
  enough).
- **Keep state outside the folder being judged**, and treat that folder as read-only.

## Acting on decisions

- **Acting is its own command, a dry run unless told otherwise,** that re-checks each item
  just before acting (still listed, inside the folder, a regular file, the same size) and
  skips what fails.
- **Trash before delete.** Move to the Trash by default; delete for good only when the
  review exists to free space, and say so. Act on one copy unless told otherwise.
- **A mark that is the only record of an action is never bulk-edited.**

## Guesses

- **A guess and a hand label are kept apart.** The hand label wins, the guess survives
  under it and returns when the field is cleared; saving one field never freezes another
  field's guess into the data.
- **Guess only from evidence** (seen in two items, or in a structural slot). When unsure,
  leave it unnamed: a wrong merge is worse than a miss.
- **A bulk accept states the count and where each guess came from, and asks first.** Every
  change is logged with its origin (hand, guess, bulk, undo) and a batch id before it is
  applied, so one batch undoes exactly and nothing else.

## Restarting a tool that serves a port

Stop only the listener: `lsof -tiTCP:PORT -sTCP:LISTEN`. `lsof -ti:PORT | xargs kill` also
matches every client connected to the port, a browser included, and kills them.

## In an existing repo

A new tool starts with `project-lifecycle init` and its conventions; a repo that already
has a state folder follows what it does before adding its own. How the screens behave is
[how an interface behaves](interface-behaviour.md).
