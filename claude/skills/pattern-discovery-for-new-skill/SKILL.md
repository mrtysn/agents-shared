---
description: Find out whether something the user keeps typing, or a failure they keep correcting, deserves a skill or rule. Counts the matching prompts in recent transcripts, reads their context, groups them, explains why the user does it, and gives a verdict. Use when the user says "scour my recent chats for my patterns", "how often do I ask for X", "find the times this happened", "I got tired of asking the same thing", or asks whether a repeated request should become a skill.
user-invocable: true
allowed-tools: Bash, Read, Agent
argument-hint: <the message, habit or failure to look for>
---

# pattern-discovery-for-new-skill

The user repeats a request or keeps correcting the same failure. This skill measures
it, explains it, and says whether it earns a skill or rule. **It builds nothing**: the
report is the deliverable, and the verdict ends the job. A skill or rule is built
only when the user says so afterwards.

## 1. Say which kind of pattern

From the user's example, state in one line what is hunted:

- **A repeated request**: their own prompts ("ask a fable subagent for their opinion").
  Counted in their prompts, steps 2-6 below.
- **A repeated agent failure**: something an agent did that they then corrected
  ("connection dropped, I had to say continue"). The evidence is in the
  assistant's text and the user's reaction after it. Search the user's follow-ups
  for the correction, then read the turn before each (`--around`, step 4).
  `scripts/find-listed-unasked-decisions.py` is the worked template for this kind:
  candidates, small-model classification in batches, aggregate.

## 2. Search

Write two or three regexes every instance would contain (alternation inside each,
patterns are ANDed). Take any keywords the user gave and use them first.

```bash
python3 "${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/scripts/find-repeated-user-prompts.py" \
  --days 30 --pattern 'REGEX' --pattern 'REGEX' --skip-prefix 'Reply with exactly'
```

It prints matches per week, per project, busiest days, and one 160-character line per
match. `--full` prints whole prompts and `--json` gives them as data.

If the user named a frustration cue ("messages with more than one question mark
mean I was frustrated"), run it as a separate search, not ANDed with the keywords:
`--pattern '\?.*\?'`.

State the window edge in the report: "transcripts begin <date>; nothing earlier is
visible". Find the date from the oldest `.jsonl` under `~/.claude/projects/`.
Never claim a habit is older than the logs, and never say it is new.

## 3. Clean the count

Match lines are too thin to judge. For more than about 30 matches, run `--json` and
hand the full prompts to `haiku` subagents (effort low, read-only, about 250 words
back) in batches, asking each to split real instances from lookups ("find the chat
where we set this up"), the current session's own prompts, pasted logs and test
harnesses. Fewer matches: read them yourself. Then search once more with a looser
pattern for phrasings of the same intent and merge. Report the corrected count with
its session count, never the raw one.

## 4. Read the context

For about eight instances, read what came before the prompt:

```bash
python3 "${AGENTS_SHARED}/scripts/extract-session-text.py" <session-id> \
  --kinds user,assistant --around <YYYY-MM-DDTHH:MM> --context 6
```

Use the full session id (`ls ~/.claude/projects/*/<prefix>*.jsonl`). Look for the
trigger: a plan just written, an answer the user doubted, finished work, a mistake.

## 5. Group and explain

- Two to four kinds, by moment or purpose, each with a count and one verbatim prompt.
- The trend: matches per week from step 2, and the busiest days.
- Why the user does it, in their own words where a prompt says it. Quote it.
- Whether rules or skills already cover it: `grep` the rule names and descriptions in
  `claude/rules/` and `claude/skills/` first.

## 6. Verdict

Say whether it earns a skill or rule. It does when it repeats weekly or more, the
instances share a purpose, and the right response has steps worth fixing (a brief to
write, a model to pick, a way to read the result). It does not when each instance
needs different judgment. Name what the skill would hold, and give the command lines
used so the count can be repeated.

Do not offer to build it.

## Report

A short answer goes in the reply. A long one (more than about 15 rows) is a page from
`/new-html-page` named `YYYY-MM-DD-slug.html` in the notebook repo. Plain words, in
this order: count, sessions and window edge; trend; kinds; why; verdict.

Do not leave the search commands in scratch if they would be run again: a search
script worth keeping goes in `agents-shared/scripts/`.
