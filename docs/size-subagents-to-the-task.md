# Size sub-agents to the task

> **This file is in `docs/`, not `claude/rules/`, on purpose.** It is no longer loaded
> into every session. `hooks/require-subagent-sizing.sh` reads the table under
> "## Pick by the work" and prints it on a session's first `Agent` call, and again on
> any call that sets no `model`. Keep that table's shape: the hook parses it.

**Every `Agent` call sets `model`, and `effort` for every row below except the last.**
Omitting them runs the sub-agent at the parent's size, which spends tokens the task
does not need. Token efficiency is a hard constraint, not a preference. The hook
`hooks/require-subagent-sizing.sh` refuses a call with no `model` and fills in the
row's `effort` when it is missing, and refuses once an `opus` or `fable` spawn (a full
model id containing either counts) whose description opens with a build verb (Build, Fix,
Implement, Offload, ...) because that is the sonnet row: re-issuing the call unchanged
passes, and on a session's first call the one refusal carries both reasons. `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`
in settings catches a spawn that reaches the tool another way, but is only a default: an
explicit `model` on the call overrides it.

## Pick by the work

| The sub-agent does | `model` | `effort` |
|---|---|---|
| Read-only work: a search or survey of more than about five tool calls, cataloguing, a report from files already named; a search or survey goes as `subagent_type: Explore`, which starts at ~19k context instead of ~52–60k | `haiku` | low |
| Ordinary implementation, mechanical edits, formatting, a page from a finished spec, a review of a diff under about 200 changed lines | `sonnet` | medium; high for a bug fix or where edge cases matter |
| Design, review of a larger change, judgment across a codebase or between options | `opus` (`fable` only for the hardest cross-codebase judgment) | omit |

Explore skips CLAUDE.md and the global rules (it keeps the skill list), so a brief for it
carries anything those would have said. It reads excerpts rather than whole files, so a
review or a report on named files stays a general-purpose agent.

`low` is Anthropic's level for work a human checks step by step; a sub-agent's edits
are not checked mid-run, so edits never go in the haiku row. `medium` is the model
default on Sonnet; `high` is their level for fixing a bug in an existing codebase.

An omitted `effort` resolves for the sub-agent's own model, not the parent's: an
`opus` spawn with no effort from a Fable session at high ran at medium (verified
2026-10-12 from the sub-agent transcript, which records model and effort per request).
Every model is pinned to medium in settings, so "omit" means medium.

Where a task could sit in two rows and its difficulty is a genuine unknown, start in
the lower row: its report is the evidence that settles it, and you move up only if the
report falls short. A task you can already tell is hard goes straight to the higher
row. `fork` ignores `model` and `effort`: use it only when the task needs this
session's full context.

## Keep it small while it runs

- **Size, not time, is the cost.** A sub-agent pays its whole context on every request, and again in full at the cache-write price when it wakes after more than 5 minutes idle: sub-agents cache for 5 minutes.
- **Long-running is fine while small.** A watcher or poller under ~100k context may wait as long as the job takes.
- **Above ~100k, do not idle.** Poll a running job at most every 4 minutes, or hand back with the job id and let a fresh agent pick up the result.
- **Hand back past ~200k.** Finish the current step and return a report a fresh agent can continue from.
- **Past ~300k, only with a reason.** Continue only when close to the end of a diagnosis a report would lose, and say so in the report.

## Do not spawn at all

A lookup or edit of up to about five tool calls is done in this session. A sub-agent
costs a brief, a report and a context of its own.

## What goes in the brief

- **This sizing table, the size limits above and the report cap below**, copied in, so
  the sub-agent keeps itself small and its own spawns are sized too.
- **A word cap on the report** (about 250 words) and a request for conclusions, not
  file dumps. A report is read once and then discarded.
- **An instruction to stop what it started**: a `Monitor` it arms is stopped with `TaskStop`
  before it hands back. A monitor outlives the sub-agent and keeps the session from closing
  cleanly until its timeout (up to 30 minutes).
- **Where any file it produces goes**, per
  [decide file location and format by reader](on-demand/decide-file-location-and-format-by-reader.md).

## Provenance

Week of 2026-10-12, measured with `scripts/report-token-use.py`: in asset-pipeline's heaviest
session, 1,772 sub-agent requests ran on `opus` at about 290k context for tasks described
"Build GNM hand-puppet body", "Fix brow motion and sheet framing", "Offload fit work to
Steam Deck": 127M of the session's 144M weighted tokens, 16% of the week's total. The
spawns named `opus` explicitly, so the settings default did not apply and the hook, which
allowed `opus`, did not object.

Same window, measured with `report-token-use.py`'s rewrite count (2026-10-17): idle cache
rewrites were $408 of the week's $1,856 at list price. Sub-agents wrote no 1-hour cache, and
the gap before their 176 rewrites had a median of 10.1 minutes. One Opus agent ran 16.8 hours,
reached 877k context and rewrote it 78 times. Of 447 sub-agents, the 17% that passed 200k made
73% of sub-agent cache reads and the 6% past 300k made 47%; small agents that ran 40 minutes
under ~110k were cheap, so the limits are on size, not duration.

2026-10-17, `report-subagent-token-use.py`: Explore sub-agents started at 18.6–19.4k context
in asset-pipeline and notebook sessions, against 52–69k for general-purpose ones; a probe
Explore agent reported seeing the skill list but no rules and no CLAUDE.md.

The same constraint typed by hand onto prompts, Sep–Oct 2026:

- "spawn models that use lower tokens for smaller tasks if you are to spend many tokens"
- "for smaller work, spawn sub-agents of smaller quality. use tokens efficiently. this is a hard constraint"
- "always be efficient token-wise and instruct your subagents to do the same. try to use lower complexity models when you can for subagents and effort level as well"
- "choose subagent model complexity adequately, while optimizing token use and task complexity mapping"
