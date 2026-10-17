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
   memory hygiene, which the first memory write in a session brings up.

The mechanism of a fix (rule, trigger row, hook, skill, script, mod) is chosen from
`docs/on-demand/choose-the-fix-for-a-pattern.md` in agents-shared, which shows itself
the first time a session writes one.

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

Provenance: [docs/provenance/fix-what-tripped-you-at-its-source.md](../../docs/provenance/fix-what-tripped-you-at-its-source.md).
