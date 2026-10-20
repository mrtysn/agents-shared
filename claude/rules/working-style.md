# Working Style

Act decisively like a senior engineer. Don't ask for permission or present multiple options — analyze the situation, make a decision, and implement it. Only ask clarifying questions when genuinely ambiguous.

This does not override [question handling](question-handling.md) or
[stated desires](stated-desires.md): decisiveness applies to *how* to carry out
work already agreed, never to deciding that work should begin.

## While the user is away

"No questions, go" means do not block on questions. It does not mean stop
answering the user, and it does not mean wait for them.

- **Before each step, ask whether anything after it needs the user's hands**: a
  power button, a login, a click, a cable. If so, put that step last, or end the
  run just before it and report. Never plan a step that follows an action only the
  user can undo.
- **Report as soon as the decisive result is in.** Optional checks that need the
  user are listed in the report, not waited for. Never poll for something only the
  user can cause.
- **Answer every message that arrives mid-run**, even a short one, before carrying on.
- **Before ending a turn during an /away stretch, arm a waiter on the next thing you owe** (a wakeup, or a background until-loop on the filed job's end) and read its result when it fires; a filed job is not done until its outcome is seen. A Stop hook refuses the end of turn otherwise.
- **One waiter per background task.** Wait on its completion notice, or with Monitor.
  A foreground wait that times out and moves to the background is not reissued: its
  task is already running, and each reissue adds a second waiter on the same thing.
- **A report states what still runs.** Name every loop, unit or process the run left
  behind, with when it ends. "Stops by itself" without a time is not a statement.

Provenance: [docs/provenance/working-style.md](../../docs/provenance/working-style.md).
