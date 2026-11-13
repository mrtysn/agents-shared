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
yourself. A step of the user's with a later date is not an item: write it where the repo
keeps open items, and name it on the closing line: `Nothing left: <delivered>. Yours by
<date>: <step>, recorded in <file>.` Never ask whether a step is done in the turn that
introduced it; ask when the user raises it or a later session reads the record. Work nobody asked for (restyling something to match, a related cleanup) is
not offered either. Work handed to another session at the user's direction is not an item
either, unless your own remaining work waits on it.

**The deliverable is the end state the request names.** "A button in my Finder toolbar" is
delivered when it is in the toolbar, not when the app exists. While that state is not reached,
the last line is never `Nothing left`: the unreached step is the item, and a step only the
user can take (a drag, a login) stays in it once you have checked you cannot do it yourself.
The Stop hook passes any `Nothing left` line without judging it, so this check is yours.

**Content the user asked to see is the last text of a turn with no tool call.** List, show,
give me, repeat, where is, table mean the content itself, not a summary or a decision. Text
written before a tool call (AskUserQuestion, Skill, Agent or any other) can be collapsed on
the user's screen to one summary line, so deliver it in a turn that ends in text only; that
turn needs no proceed question, which comes in the next turn.

**An answer that points at work still ends with the question.** Answering authorizes
no edits ([question handling](question-handling.md)); offering the work as an option
is what replaces stopping. A wish ends the same way: the proposal, then the question
([stated desires](stated-desires.md)). A question whose every option does nothing (a "wait" and a "stop")
is not asked: end the turn in text, saying in one line what is unfinished.

Exceptions: the user said stop, an `/away` stretch (decide, never ask), a background job you
are waiting on with nothing else to do, or a slash command the user queued (a hook says so):
Claude Code runs it only once the turn ends, so finish the current step and end in text,
never asking and never invoking it yourself. When your next step needs a slash command only
the user can type, end the turn in text naming it and continue once its output appears; never
ask for it through AskUserQuestion, whose answer arrives first. The user rejected or answered your last question: do not ask
it again, reworded or not, even when a Stop hook refuses the turn; say in one line what is unfinished and end in text (the hook passes such a turn).

`hooks/refuse-idle-end-of-turn.sh` (Stop) refuses, once, a turn that ends otherwise, and lets
a text-only turn through when the user asked to see content, unless the prompt said "and continue" ("show X and continue"): then the turn must also arm a ScheduleWakeup or start the remaining work in the background, so the work resumes;
`hooks/refuse-requested-content-before-tool-call.sh` (PreToolUse) refuses, once, that content
written ahead of a question, skill or agent call, and a copy-ready draft (a fenced block) written ahead of any tool call; it also refuses, once, the first Edit, Write or state-changing Bash call of a turn whose prompt asked to see content that is not delivered yet (a one-line announcement is not delivery; reads that gather the data are fine); `hooks/end-turn-for-queued-slash-command.py`
says when a slash command is queued and refuses the question or the skill call meanwhile.

Provenance: [docs/provenance/end-every-turn-with-a-next-step.md](../../docs/provenance/end-every-turn-with-a-next-step.md).
