# Restate hidden output in your own reply

**A task notification, monitor event, agent hand-back, or the full output of a
command is not something the user has read; it exists only in this session's
context.** Before writing "as reported", "as shown above", or any reference to
it, restate the finding in your own reply. Never point at a transcript entry the
user cannot open.

What the user sees of a tool call is a collapsed line and, for a command, at most
a few lines of its output. A subagent's report, a background task's result and a
monitor's event reach only the model. So "the result is above" names something
that is not on their screen, and the answer to their question is still missing.

## What to do

- **Relay, don't reference.** The numbers, the table, the file path, the verdict:
  write them into the reply. One line of substance beats a pointer.
- **Long command output counts as hidden.** If the reply depends on it, quote the
  lines that matter.
- **A relayed report is still yours to shape.** Filter it to what the user asked;
  the subagent's wording and length are not the deliverable.

## Provenance

Sep 2026: after a discovery agent's report, the reply said "the result is above",
and the user answered with a screenshot: "what is 'above'?". A transcript survey
(`scripts/find-invisible-output-claims.py`) found the same shape earlier that
month: a background agent's findings referenced but never shown, until "show me
what you grabbed so far".
