---
description: Decide whether now is a good time to run /compact — nothing mid-edit, nothing that only this conversation holds and a summary would lose — and end with a ready /compact message naming what the summary must keep. Read-only: it writes no file and makes no commit. Use when the user asks "is this a good time to run compact", "should I compact", "can I compact now", "what should the compact message say", or is about to run /compact.
argument-hint: [optional scope, e.g. "just the message"]
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, ListAgents
---

The user is considering `/compact`. A compact is not a close: the session stays, and only
the conversation text is replaced by a summary. So nothing is stopped here. This skill
reports whether anything would be lost or broken, and ends with the message to compact with.

**Scope for this run:** $ARGUMENTS

If that line is empty, run every check.

**Read-only.** Every step changes nothing: no file is written, nothing is committed, and
no handoff note is made. What only the conversation holds goes into the `/compact`
message, not into a file.

## What a compact keeps and loses

From the Claude Code docs (context-window page, "What survives compaction"):

| After a compact | Kept how |
|---|---|
| Project-root `CLAUDE.md`, unscoped rules, auto memory | Re-injected from disk |
| Invoked skill bodies | Re-injected, capped at 5,000 tokens each and 25,000 in total, oldest dropped first |
| Files read or edited | Up to five re-read, most recently modified first |
| Background shells and background subagents | Keep running; the model is reminded which |
| Path-scoped rules, nested `CLAUDE.md` | Not re-injected; they load again when a matching file is touched |
| Context hooks added earlier (once-per-session rule notices) | Summarized with the conversation |
| Everything said in the conversation | Summarized |

Not documented: whether `Monitor`, `/loop` and `ScheduleWakeup` survive. Say so for each
one this session has; never claim they survive.

The text after `/compact` is documented only as "focus instructions for the summary". It
steers the summary; it is not kept verbatim, and no length limit or file argument is
documented.

## Procedure

1. **Live work.** Run `list-session-background-shells.sh --session <this session's id>`
   (agents-shared `scripts/`; the id is the UUID in the scratchpad path) and `ListAgents`.
   Name each running shell and agent of this session, with its pid or id and what its
   result will do: a shell or agent keeps running through a compact. Name every `/loop`,
   `Monitor` and wakeup this session set up, marked "survival not documented".

2. **Work in flight.** In the working directory and every other repo this session edited,
   run `git status --porcelain=v1 --branch`. Only changes this session made count; a
   stranger's file gets no row. Own changes that are finished but uncommitted are named;
   an edit or tool call that is half done is a reason to wait.

3. **What only the conversation holds.** List what a summary would lose and a fresh
   reading of the repo would not give back: job ids and output paths, the next concrete
   step, decisions waiting on the user, corrections the user gave in this conversation,
   rule notices a hook showed once, a path-scoped rule in force, an agent id to continue
   with `SendMessage`. Skip what is in `CLAUDE.md`, rules files, memory, git history or a
   committed doc: those come back by themselves.

4. **Verdict.** Decided by these conditions, not by feel.

   `Wait:` if any one is true, with the reason and when it ends:
   - an edit or tool call is mid-flight, or own work is half written;
   - a result is due within about ten minutes and reading it needs this conversation's
     context to interpret.

   Otherwise `Good time.` A running background shell or agent is not a reason to wait.
   Auto-compaction ignores `Wait`; near the threshold, the message matters more than the
   verdict.

## Output

Lead with the verdict, one line. Then only what the user needs:

- `Good time.` or `Wait:` and the reason.
- Live work that survives, one line each; anything with survival not documented, marked.
- Finished own work that is uncommitted, named with its repo (the commit rule covers it;
  this skill does not commit it).

The last thing in the reply is the message, in a code block:

    /compact <one or two lines naming what the summary must keep>

- Names only what step 3 found: ids, paths, the next step, waiting decisions, corrections.
- Stays one or two lines, because a long line wraps and breaks when copied. If it will not
  fit, keep the ids, the next step and the waiting decisions, and drop the rest; a summary
  does not need every detail.
- Never written to the clipboard, and never offered.
- Nothing to keep that git, rules or memory do not hold: say "nothing is lost" and give
  a bare `/compact`.

Never run `/compact` yourself.
