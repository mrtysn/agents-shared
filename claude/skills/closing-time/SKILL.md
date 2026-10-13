---
description: Decide whether this session is safe to close — background shells and the servers they started, running agents, uncommitted work, and whether the notes and handoff files let a fresh session pick up the remaining work. Stops what this session left running, fixes documentation gaps, then ends with one verdict line. Use when the user asks "is it safe to close", "can I close this session", "closing time", "did you leave handoffs", "can a fresh session pick this up", "why do you have N shells running", or says they are about to leave or go.
argument-hint: [optional scope, e.g. "just the shells"]
user-invocable: true
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, Agent, ListAgents, TaskStop
---

The user is about to close this session. When you are done, nothing this session started is still running, nothing it did is lost, and the last line says so. "Closing time" means the machine is left as it was found, plus the work.

**Scope for this run:** $ARGUMENTS

If that line is empty, run every check.

## What is ours

Ours: the processes `list-session-background-shells.sh` prints for this session's id, every process this conversation started another way (`nohup`, `setsid`, `launchctl`, `open`, `docker run`, `tmux`; you know these from the conversation, the script cannot see them), the agents `ListAgents` shows as spawned by this session, and any `/loop`, `Monitor` or `/schedule` this session set up. Nothing else is touched: other sessions' shells and agents, the user's own apps and terminals, services that were running before this session. The `ListAgents` rows for peer sessions are not ours.

## Procedure

1. **Processes.** Run `list-session-background-shells.sh --session <this session's id>` (agents-shared `scripts/`; the id is the UUID in the scratchpad path). Each block is one process tree this session started: the shell on the first line, its children indented with any `LISTEN addr:port`, and `orphan` blocks for children whose shell is already gone. Printed nothing: go to step 2. For each block, in order:
   1. Say what it is doing in plain words.
   2. Check what stopping it loses. A server holding input the user typed (a decision form, an editor): look for its saved copy beside the file it serves (`FORM.answers.json`, a draft file; `--help` of the command says where) and read it. A job writing results: check the output file is complete. If stopping loses something that rerunning the command cannot bring back, do not stop it; it is a blocker.
   3. Otherwise stop it: `kill <pid> <pid> …` with every pid of the block typed as a literal number, the children included. No `pkill`, no pattern, no `$(…)`, no pid the script did not print. Wait two seconds; if a pid is still alive, `kill -KILL <pid>` once.
   4. Verify: run the listing again; the block must be gone. For each port the block was listening on, `lsof -nP -iTCP:<port> -sTCP:LISTEN` must print nothing. A tree that survives this is a blocker, named with its pids.
   5. Record what the user needs to run to bring it back (the command, the file it served), for the handoff in step 5.

   Then processes this conversation started outside a background shell: find each by the pid or name recorded when it was started, stop and verify the same way. One the user asked, in so many words, to keep running after the session is left alone and named in the output; a background shell cannot be kept this way, since the session's end kills it, so that one is a blocker.

2. **Agents and scheduled work.** `ListAgents`. A running agent of this session whose result is still needed is a blocker; one whose result is no longer needed is stopped with `TaskStop` and said so. A `/loop` or `Monitor` of this session ends with the session: needed, blocker; not needed, nothing to do, say so. A `/schedule` routine runs in the cloud and survives; name it, it is not a blocker.

3. **Uncommitted and unpushed work.** For the working directory and every other repo this session edited, run `git status --porcelain=v1 --branch`. Only changes this session made count; a stranger's file gets no row. Commit and push your own finished work per the commit rule, unless the repo's `CLAUDE.md` says to ask. Own work left uncommitted on purpose (not ready, or the repo says to ask) is named in the handoff with the reason; it is not a blocker once written down.

4. **What remains, and where it is written down.** List every item still outstanding from this conversation: unfinished work, agreed next steps, decisions waiting on the user, things only the user can do, anything stopped in step 1 that the user will want back. For each, find where a fresh session would read about it: the repo's `CLAUDE.md`, a plan or TODO file, a handoff file, `docs/`. An item that lives only in this conversation is a gap. A decision waiting on the user is not a blocker once it is written down with how to resume it.

5. **Close the gaps.** For each gap, write it into the existing document where it belongs, with the Edit tool (never open a file for writing before reading it). If no document fits, write a handoff in the repo the work belongs to (Markdown, because its reader is a later session), using what `/handoff` would contain: the matter at hand, what was established, the current state, the next concrete step, the command that restarts anything stopped in step 1, and anything that is not obvious from the code. Name files by absolute path. Commit and push it where the repo is tracked; a notebook file stays local.

6. **Check that a fresh session can use it.** Spawn one `general-purpose` sub-agent, `model: haiku`, `effort: low`, briefed with only the paths of the documents and this question: "From these files alone, what is the next step of this work, what is already done, and what would you need that is not written down?" Report cap about 150 words, text only, no files written. Compare its answer with step 4. A mismatch or a missing piece is a gap: fix it and check once more. Skip this step when nothing remains outstanding.

7. **Last look.** Run the listing from step 1 once more. It must print nothing.

## Verdict

The verdict is decided by these conditions, not by judgment. Every one true: `Safe to close.` Any one false: `Not yet:`.

- The listing in step 7 printed nothing, and nothing this conversation started another way is alive (except a process the user asked to keep, named in the output).
- No running agent, loop or monitor of this session is still needed.
- Own changes are committed and pushed, or named in the handoff as left on purpose.
- Every outstanding item is written down somewhere a fresh session reads, and step 6 confirmed it (or nothing is outstanding).

A process that is alive and ours is never left out of the verdict: it was stopped and verified gone, or it is a `Not yet:` line.

## Output

Lead with the verdict, one line, then only what the user needs:

- `Safe to close.` followed by one line naming where the remaining work is written down, as an absolute path (or "nothing outstanding").
- `Not yet:` and the blockers, each one line with its next step (a tree that would not die, with its pids; an agent to wait for; a process the user must decide about).

Then a short list: processes stopped (pid, what it was, how to bring it back) or "none"; agents (or "none"); changes committed; documents written or updated (absolute paths). No table. Items owned by someone else are not listed.

Never close or stop the session yourself.
