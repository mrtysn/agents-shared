# End every turn with a next step

**A turn ends in one of three ways: still working, asking, or with nothing left.**
Never with a bare report, an answer, or an offer in prose.

1. **Working.** Authorized work remains that you can do, including anything you just
   said you would do next ("I'll render…", "Now the record…"): do it in this turn.
   While a background job runs, work alongside it on anything else in scope.
2. **Asking.** Otherwise call AskUserQuestion: the open decisions, then the proceed
   question (multiSelect): one option per piece of work you could do next,
   recommended first; one per step only the user can do ("I'll do it now, walk me
   through it" / "Done, check it"); last, "Stop here". The ask-open-decisions skill,
   step 5, has the format.
3. **Nothing left** for you or the user: the last line is `Nothing left: <why>.`

**A step for the user is an item, not a reason to stop.** A list of them ends with
the proceed question like any other list. Check first that you cannot do it yourself.

**An answer that points at work still ends with the question.** Answering authorizes
no edits ([question handling](question-handling.md)); offering the work as an option
is what replaces stopping. A wish ends the same way: the proposal, then the question
([stated desires](stated-desires.md)).

Exceptions: the user said stop, an `/away` stretch (decide, never ask), or a
background job you are waiting on with nothing else to do.

`hooks/refuse-idle-end-of-turn.sh` (Stop) refuses, once, a turn that ends otherwise.

Provenance: [docs/provenance/end-every-turn-with-a-next-step.md](../../docs/provenance/end-every-turn-with-a-next-step.md).
