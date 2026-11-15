---
description: After a multi-step process has finished, find what went right and what the friction points were from its own record, get an independent opinion on what else the guidance needs, and write the agreed lessons into the repo's guidance. Runs only when the user asks for it. Use when the user invokes /learn-from-finished-process, or says "what went right, what were the friction points", "anything else we should add to the guidance", "learn from this process", or "make these lessons stick". Not for one trip just worked around (/fix-it-at-its-source), a habit across many chats (/pattern-discovery-agent-fix), or a plain opinion (/vet-fable).
argument-hint: [the process, e.g. "the 21 backend units"; empty means the work just finished in this session]
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep, Edit, Write, Skill, Agent
---

The user wants a finished process turned into guidance the next run starts from.

**Process for this run:** $ARGUMENTS

Empty means the work this session just finished.

## Procedure

1. **Mine the process's own record, not the session's memory.** Read what the process left:
   review logs, fix rounds, commits, the repo's guidance as it stood, and the user's
   corrections and questions (`extract-session-text.py`, per /mine-chat-logs; never a
   hand-written transcript parser). Cap what is read; say what was read.
2. **Split the findings.** *Went right*: what held and should be kept. *Friction points*:
   where work was redone, corrected, blocked or waited. One line each, with the evidence
   (commit, log line, the user's words) and the cause, not the symptom.
3. **Ask for an independent opinion** with /vet-fable, blind: the user's question, the
   record's paths and the repo's guidance paths, not these findings. Then send it the
   findings from step 2 for a critique, as /vet-fable says.
4. **Write the agreed lessons where the repo keeps them**, per
   `claude/rules/fix-what-tripped-you-at-its-source.md`: a guard or check in the tool
   first, then an error message, then a line in the repo's `CLAUDE.md` or Lessons table.
   Edit an existing line instead of adding a second one beside it. Show the exact wording
   before writing it.
5. **Commit each lesson on its own** per the commit rule, run the repo's tests first, and
   report one line per lesson: what tripped, what now prevents it, and the went-right items kept.
