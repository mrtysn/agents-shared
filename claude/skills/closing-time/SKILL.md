---
description: Decide whether this session is safe to close — background shells, running agents, uncommitted work, and whether the notes and handoff files let a fresh session pick up the remaining work. Fixes documentation gaps, then ends with one verdict line. Use when the user asks "is it safe to close", "can I close this session", "closing time", "did you leave handoffs", "can a fresh session pick this up", "why do you have N shells running", or says they are about to leave or go.
argument-hint: [optional scope, e.g. "just the shells"]
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent, ListAgents
---

The user is about to close this session. Establish whether that loses anything, repair what it would lose, and say so in one line.

**Scope for this run:** $ARGUMENTS

If that line is empty, run every check.

## Procedure

1. **Background shells.** Run `list-session-background-shells.sh --session <this session's id>` (in agents-shared `scripts/`; the id is the UUID in the scratchpad path). Each line is a live shell: report pid, elapsed time and what it is doing in plain words, and whether closing the session will kill it. A shell that still matters is a blocker; one that is finished or stray is stopped by absolute pid after saying so.

2. **Running agents and scheduled work.** Use `ListAgents` for sub-agents and teammates this session spawned that are still working, and any wakeup, loop or cron this session scheduled. Name each and what it will do if left. A running agent whose result matters is a blocker.

3. **Uncommitted and unpushed work.** For the working directory and every other repo this session edited, run `git status --porcelain=v1 --branch`. Only changes this session made count; a stranger's file gets no row. Commit and push your own finished work per the commit rule, unless the repo's `CLAUDE.md` says to ask. Work that is not ready stays listed.

4. **What remains, and where it is written down.** List every item still outstanding from this conversation: unfinished work, agreed next steps, decisions waiting on the user, things only the user can do. For each, find where a fresh session would read about it: the repo's `CLAUDE.md`, a plan or TODO file, a handoff file, `docs/`. An item that lives only in this conversation is a gap.

5. **Close the gaps.** For each gap, write it into the existing document where it belongs, with the Edit tool (never open a file for writing before reading it). If no document fits, write a handoff in the repo the work belongs to (Markdown, because its reader is a later session), using what `/handoff` would contain: the matter at hand, what was established, the current state, the next concrete step, and anything that is not obvious from the code. Name files by absolute path. Commit and push it where the repo is tracked; a notebook file stays local.

6. **Check that a fresh session can use it.** Spawn one `general-purpose` sub-agent, `model: haiku`, `effort: low`, briefed with only the paths of the documents and this question: "From these files alone, what is the next step of this work, what is already done, and what would you need that is not written down?" Report cap about 150 words, text only, no files written. Compare its answer with step 4. A mismatch or a missing piece is a gap: fix it and check once more. Skip this step when nothing remains outstanding.

## Output

Lead with the verdict, one line, then only what the user needs:

- `Safe to close.` when there is no blocker, followed by one line naming where the remaining work is written down, as an absolute path.
- `Not yet:` and the blockers, each one line with its next step (a shell to stop, an agent to wait for, a decision only the user can make).

Then a short list: shells (or "none"), agents (or "none"), changes committed, documents written or updated (absolute paths). No table. Items owned by someone else are not listed.

Never close or stop the session yourself.
