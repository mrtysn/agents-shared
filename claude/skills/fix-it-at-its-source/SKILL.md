---
name: fix-it-at-its-source
description: Fix what just tripped at its source, now, in the repo that owns it. A typed nudge: it does not search chat logs.
disable-model-invocation: true
argument-hint: [what tripped; empty means the trip just discussed in this session]
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

The user is telling you a trip was worked around instead of fixed. Fix it where it lives,
as `claude/rules/fix-what-tripped-you-at-its-source.md` says, so the next session does
not hit it.

$ARGUMENTS

1. **Name the trip in one line**: what went wrong, from the argument or, with none, the
   last failure discussed in this session. Do not search chat logs; measured evidence
   across sessions is `/pattern-discovery-agent-fix`.
2. **Find the owner**: the tool, script, pipeline, skill, doc or rule that let it happen,
   and the repo it lives in. Read that repo's `CLAUDE.md` before changing anything in it.
   Another session holds the file: message it instead of editing.
3. **Pick the first fix that fits**, in this order: a guard or earlier check in the tool
   itself; a better error message that says what is wrong and what to do; a doc line or
   Lessons-table row where the repo keeps one; a memory entry, last, only for a fact with
   no repo home. A rule, hook, skill or script is chosen from
   `$AGENTS_SHARED/docs/on-demand/choose-the-fix-for-a-pattern.md`.
4. **Words an agent reads** (a rule, skill, doc line or memory) are shown first: the exact
   lines in a visible reply, then written once the user agrees. A rule says what to do; it
   does not list what is fine or narrate the incident. A code guard or error message is
   made directly.
5. Run the repo's tests, commit with a pathspec as one atomic commit, and push.
6. Report one line: what tripped, what now prevents it.

Not for a one-off environment fluke, a third-party service you do not own (record the
lesson where the repo keeps refusals), or the user's own creative choices.
