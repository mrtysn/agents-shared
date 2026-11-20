# One surveyed item

Each subagent returns a list of items in this shape.

- **Principle:** one sentence, general enough to apply to another project.
- **In this source:** where it lives (file:line, commit, or page region and screenshot).
- **Reversal (repos):** what was built, what replaced it, and why. Read from the diff
  and the user's message that caused it.
- **Evidence:** the user's quote with its session id, or the screenshot name.
- **Open tension:** what the principle leaves unsolved.
- **Scope:** `general` or `specific to this source`, with one line of reason. When
  specific, say what would make it general (reword, drop a name).
- **Privacy:** anything that could not go in a public repo (names, quotes, paths).

Rules for the brief: ask for counts of how many items are general; forbid invented
evidence; for a third-party page, ask for the principle and never its text or styling.
