# Provenance: Fix what tripped you, at its source

Why [the rule](../../claude/rules/fix-what-tripped-you-at-its-source.md) exists.

Oct 13 2026, game-venture: one short's render hit, in order, a job-status JSON
shape the wait loop misread, a resume flag that silently re-ran an earlier step,
a channel art rule enforced only after voice was spent, background music shorter
than the short caught only at the final mix, one-sided source audio caught only
at the final mix, and stale claim files left by a cancelled job. Each was worked
around by hand and none fixed for the next session, until the user asked:
"while doing work, if you run into any problems, caveats --> automatically self
improve. think of the future claude code sessions and be helpful for all. maybe
this can be recorded as a rule? and you apply the rule now?"
