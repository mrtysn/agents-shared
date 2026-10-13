# Fix what tripped you, at its source

**When a tool, script, pipeline, skill or doc trips you during work, fix it where
it lives as part of the task, so the next session does not hit it.** The
workaround you used today is not the fix: it leaves the trap set for whoever
comes next, and that session has none of your context.

A trip is a wrong assumption baked in, a check that fires only late, a confusing
output shape, a silent failure, a missing flag, or stale state left behind.

## Where the fix goes

In this order, taking the first that fits:

1. **A guard, or an earlier check, in the tool itself.** A rule enforced only
   after the expensive step is not enforced; move it before the step.
2. **A better error message** that says what is wrong and what to do.
3. **A doc line or Lessons-table row**, where the repo keeps one. Several repos
   have a Lessons table or a `REFUSALS.md`; use it.
4. **A memory entry**, last, and only for a fact with no repo home. See
   [memory hygiene](memory-hygiene.md).

## How far to go

- **Fix it in the repo that owns the tool**, under that repo's `CLAUDE.md` and
  tests, and commit it on its own per
  [commit atomically](commit-atomically-as-you-build.md).
- **Another session holds the file right now:** message that session instead of
  editing, per [messages between sessions](messages-between-sessions.md).
- **The fix is large, or changes behaviour others rely on:** propose it rather
  than build it, per [stated desires](stated-desires.md) and
  [asking for decisions](asking-for-decisions.md).

## Report it

One line per fix in the closing reply: what tripped, what now prevents it.

## Not for

- A one-off environment fluke that will not recur.
- A third-party service you do not own. Record the lesson where the repo records
  refusals, and change nothing else.
- The user's own creative or editorial choices.

## Provenance

Oct 13 2026, game-venture: one short's render hit, in order, a job-status JSON
shape the wait loop misread, a resume flag that silently re-ran an earlier step,
a channel art rule enforced only after voice was spent, background music shorter
than the short caught only at the final mix, one-sided source audio caught only
at the final mix, and stale claim files left by a cancelled job. Each was worked
around by hand and none fixed for the next session, until the user asked:
"while doing work, if you run into any problems, caveats --> automatically self
improve. think of the future claude code sessions and be helpful for all. maybe
this can be recorded as a rule? and you apply the rule now?"
