# How an interface behaves

**A screen someone uses for hours (a Mac app, a game menu, a web page that is a tool) is
judged on whether it tells the truth and stays put.** These rules hold for every kind of
interface; the measurable ones are checked in the kind's own repo (below). A one-read
report page is not a tool: only the first and last rule apply to it.

## Rules

1. **Say what is true.** A label states the exact state ("missing", not "being made" when
   nothing is being made) and, where a command fixes it, names the command. A lost server
   and a broken page read differently.
2. **One state, many views, one navigation bar.** A card view, a list and a totals table
   read and write the same record, so a value changed in one shows in the others. The bar
   sits in the same place at the same size on every screen.
3. **A new way to look is a mode, not a page.** Another order, filter or pass is an option
   on the screen that exists. A mode that only browses (a random order) records nothing.
4. **A position badge shows this item's place** ("3 of 3"), never how many were already
   judged, so the last item of a group does not read "2 of 3".
5. **Progress counts what is left in the pass you are in.** A second pass over the kept
   items starts from its own total and cannot pass 100%.
6. **One verb, one meaning.** A word that removes in one place does not hide in another;
   the same action keeps its name on every screen.
7. **Each switch is a remembered mode or a one-shot action, and says which.** A toggle
   that stays on looks like one; a button that does something once looks like one.
8. **A failed save keeps the item on screen and says so.** Nothing falls out silently: an
   item that cannot be shown still gets a card that says why.
9. **Nothing moves unless the user moved it:** a state changes colour, never size, and the
   controls keep their place when the view changes.
10. **What lights up is what a press acts on.** A row whose highlight spans its width acts
    on a press anywhere in that width, not only on its label.
11. **A thing that can be touched answers every ordinary gesture the way the hand expects**
    (drag, throw, tap, scroll past it) and turns none of them into a side effect such as a
    selection.
12. **Kept state comes back before it is drawn.** A position or mode remembered across a
    reload is in place on the first frame; it never shows the default and then jumps.

## Where the measurable ones are checked

- Web pages and apps: the rules in web-shared's `DESIGN.md`, run with
  `project-lifecycle page-check`; read the renders too ([check a visual change against the
  user's own words](verify-visual-ui-against-the-request.md)).
- Mac apps: `docs/STYLE.md` in project-lifecycle and its self-test and convention checks.
- Godot games and other native screens: no automatic check; render the screen and read it
  ([verify a terminal UI by rendering it](../../claude/rules/verify-terminal-ui-by-rendering.md) for the habit).

What changes the user's own data (a log, a delete, a bulk accept) is a separate doc:
[tools that change the owner's data](tools-that-change-the-owners-data.md).
