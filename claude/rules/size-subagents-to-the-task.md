# Size sub-agents to the task

**Every `Agent` call sets `model`, and `effort` for every row below except the last.**
Omitting them runs the sub-agent at the parent's size, which spends tokens the task
does not need. Token efficiency is a hard constraint, not a preference. The hook
`hooks/require-subagent-sizing.sh` refuses a call with no `model` and fills in the
row's `effort` when it is missing; `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` in settings
catches a spawn that reaches the tool another way.

## Pick by the work

| The sub-agent does | `model` | `effort` |
|---|---|---|
| Read-only work: a search or survey of more than about five tool calls, cataloguing, a report from files already named | `haiku` | low |
| Ordinary implementation, mechanical edits, formatting, a page from a finished spec, a review of a diff under about 200 changed lines | `sonnet` | medium; high for a bug fix or where edge cases matter |
| Design, review of a larger change, judgment across a codebase or between options | `opus` (`fable` only for the hardest cross-codebase judgment) | omit |

`low` is Anthropic's level for work a human checks step by step; a sub-agent's edits
are not checked mid-run, so edits never go in the haiku row. `medium` is the model
default on Sonnet; `high` is their level for fixing a bug in an existing codebase.

Where a task could sit in two rows and its difficulty is a genuine unknown, start in
the lower row: its report is the evidence that settles it, and you move up only if the
report falls short. A task you can already tell is hard goes straight to the higher
row. `fork` ignores `model` and `effort`: use it only when the task needs this
session's full context.

## Do not spawn at all

A lookup or edit of up to about five tool calls is done in this session. A sub-agent
costs a brief, a report and a context of its own.

## What goes in the brief

- **This sizing table and the report cap below**, copied in, so the sub-agent's own
  spawns are sized too.
- **A word cap on the report** (about 250 words) and a request for conclusions, not
  file dumps. A report is read once and then discarded.
- **Where any file it produces goes**, per
  [decide file location and format by reader](decide-file-location-and-format-by-reader.md).

## Provenance

The same constraint typed by hand onto prompts, Sep–Oct 2026:

- "spawn models that use lower tokens for smaller tasks if you are to spend many tokens"
- "for smaller work, spawn sub-agents of smaller quality. use tokens efficiently. this is a hard constraint"
- "always be efficient token-wise and instruct your subagents to do the same. try to use lower complexity models when you can for subagents and effort level as well"
- "choose subagent model complexity adequately, while optimizing token use and task complexity mapping"
