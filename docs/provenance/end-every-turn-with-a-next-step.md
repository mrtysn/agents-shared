# Provenance: End every turn with a next step

Why [the rule](../../claude/rules/end-every-turn-with-a-next-step.md) and
`hooks/refuse-idle-end-of-turn.sh` exist.

2026-10-28, music-playground. A feature was built, committed and installed, and the turn
ended on a report whose open items were all the user's hardware steps. The user asked a
research question; the answer pointed at the obvious next work (an accuracy harness
against ground truth) and the turn ended. "Why have you stopped?" got "a question gets an
answer, not a build" and "the choice that shapes it is where the answer key comes from",
in prose, and the turn ended again. Asked why it had not run `/ask-open-decisions`, the
agent said nothing triggers it and the remaining items were "steps for your hands, not
choices, so there was nothing to ask".

The rules were loaded and were read as permission to stop: question handling ("answer,
do not act"), stated desires ("Stop. Wait for the build order."), the outstanding
skill's "If nothing needs the user, skip this step", and the split between decisions
(asked) and the user's own steps (listed). Asking for decisions forbade the prose ask but
nothing checked it at the end of a turn; the only Stop check, `log-buried-go-ahead.sh`,
had logged since 2026-10-13 and never blocked.

Mined logs, 2026-09-25 to 2026-10-28: 122 typed nudges ("continue", "proceed", "why did
you stop", "why are you idle") in 66 sessions, and `/ask-open-decisions` typed by hand 408
times and `/outstanding` 472 times in 34 days. Of 47 last turns before a nudge that were
not connection losses, the shapes were: announced the next step then ended, a bare report,
permission asked in prose for settled work, a choice posed in prose, a list of the user's
steps, and idling beside a running background agent.

So the fix is one Stop detector that blocks, replacing the log-only one, plus wording:
the user's own steps are items of the proceed question, an answer that points at work ends
with the question, and the proceed question is never skipped.
