# End every turn with a next step

**A turn ends in one of three ways: still working, asking, or with nothing left.**
Never with a bare report, an answer, or an offer in prose.

1. **Working.** Authorized work remains that you can do, including anything you just
   said you would do next ("I'll render…", "Now the record…"): do it in this turn.
   While a background job runs, work alongside it on anything else in scope.
2. **Asking.** Otherwise call AskUserQuestion: the open decisions, then the proceed
   question (multiSelect): one option per unfinished part of what the user asked for
   that you could do next, recommended first; last, "Stop here". The
   ask-open-decisions skill, step 5, has the format.
3. **Nothing left** of what the user asked for: the last line is
   `Nothing left: <what was delivered>.`

**Only the unfinished part of the request is an item.** What the user does with a
finished deliverable (upload it, paste it, send it, deploy it, tell someone) is the
point of the task, never an item: do not list it, offer it, or walk through it. A step
only the user can take counts only when your own remaining work waits on it (a login,
a device in hand, a reboot before a test), and only after checking you cannot do it
yourself. Work nobody asked for (restyling something to match, a related cleanup) is
not offered either.

**An answer that points at work still ends with the question.** Answering authorizes
no edits ([question handling](question-handling.md)); offering the work as an option
is what replaces stopping. A wish ends the same way: the proposal, then the question
([stated desires](stated-desires.md)).

Exceptions: the user said stop, an `/away` stretch (decide, never ask), or a
background job you are waiting on with nothing else to do.

`hooks/refuse-idle-end-of-turn.sh` (Stop) refuses, once, a turn that ends otherwise.

Provenance: [docs/provenance/end-every-turn-with-a-next-step.md](../../docs/provenance/end-every-turn-with-a-next-step.md).
