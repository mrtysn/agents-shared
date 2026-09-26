# Verify a terminal UI by rendering it

**A change to anything drawn in a terminal — an fzf menu, a TUI, a status line,
a table a script prints — is not done until you have read its rendered screen.**
Render it with `render-terminal-screen` (the `tools` repo, in `~/bin`) and read
the grid it prints:

    render-terminal-screen --size 120x40 --type <keys> --key enter -- <command>

- **At two widths**, e.g. 120 and 90 columns. Truncation and wrapping hide at
  one width and show at the other.
- **Read it as the user would**: can each row be told apart, does the part
  that matters survive truncation, is anything cut, misplaced or mostly empty?
- **Fix and re-render** until it reads well; report what the screen showed.

## Grepping output does not count

A program's raw output is cursor moves and redraws. Finding the expected words
in it proves the data is there, not that anyone can read it: every layout bug
passes that check. Only the rendered screen shows layout.

## Provenance

Sep 2026: clo's search and recent-sessions views were reported done after tests
that grepped a pseudo-terminal's output for session names. On screen, a 60%
side pane cut every topic to twelve characters and the header ran off the
edge; the user found it from a screenshot.
