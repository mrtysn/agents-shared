---
description: Find out whether something the user keeps typing, or a failure they keep correcting, deserves a skill or rule (a repeated request, a repeated failure, or a tone cue such as "more than one ?"). Counts the matching prompts in recent transcripts, reads their context, groups them, explains why the user does it, and gives a verdict. Use when the user says "scour my recent chats for my patterns", "how often do I ask for X", "find the times this happened", "I got tired of asking the same thing", or asks whether a repeated request should become a skill.
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
  assistant's text and the user's reaction after it. Get the candidates and the
  batch classification from the `mine-chat-logs` skill (its steps 3 and 4: rows with
  the user's next message, small read-only agents), then read the turn before each
  (step 4 below). `scripts/find-listed-unasked-decisions.py` is a worked example.
- **A tone cue**: a marker the user says signals a mood ("messages with more than
  one question mark mean I was frustrated"). The marker is the whole search, so
  the question is what share of the matches carry the mood and what provoked it.
  Step 3 classifies tone; no keyword is ANDed in.

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
visible". Get the date from
`python3 "$AGENTS_SHARED/scripts/extract-session-text.py" --all --window`.
Never claim a habit is older than the logs, and never say it is new.

## 3. Clean the count

Match lines are too thin to judge. For more than about 30 matches, run `--json` and
classify the full prompts in batches as `mine-chat-logs` step 4 describes (haiku, low
effort, read-only, a verdict file), asking each batch to split real instances from
lookups ("find the chat where we set this up"), the current session's own prompts,
pasted logs and test harnesses. Fewer matches: read them yourself. Then search once more with a looser
pattern for phrasings of the same intent and merge. Report the corrected count with
its session count, never the raw one: pastes and noise are subtracted before the
number is stated.

**A tone cue** is classified by the same batches, one label per prompt (for example
frustrated, calm question, numbered reply to a list, paste). A keyword filter
(`wtf`, `I said`, `man`) is a quick estimate with false positives and false
negatives; say "estimate" and never call it a lower or upper bound.

## 4. Read the context

For about eight instances, read what came before the prompt. Draw them from every
group, at least two each, not only the group the pattern is suspected in, with
`extract-session-text.py <session-id> --kinds user,assistant --around <time> --context 6`
(`mine-chat-logs` step 5). Use the full session id (`ls ~/.claude/projects/*/<prefix>*.jsonl`).
Look for the trigger: a plan just written, an answer the user doubted, finished work, a mistake.

## 5. Group and explain

- Two to four kinds, by moment or purpose, each with a count and one verbatim prompt.
  Every kind gets a quote, the calm ones too; a share claimed without a quoted
  example is unsupported.
- The trend: matches per week from step 2 with the busiest days, and a rate per
  active day (days with at least one prompt of any kind), since a quiet day says
  nothing about the habit. Mark a partial week as partial. When the daily counts
  jump around, say "spiky, no readable trend" rather than "steady" or "rising".
- Why the user does it, in their own words where a prompt says it. Quote it, and say
  what the quote explains (the repetition, the punctuation, the failure).
- Whether rules, skills or memory already cover it: search the names and
  descriptions in `claude/rules/` and `claude/skills/`, and the memory buckets
  (`~/.claude/projects/*/memory/`, their `MEMORY.md` indexes and files). Name the file
  you found, and check that it addresses the instance, not just a shared keyword. A
  keyword hit in a rule that is about something else is not coverage.

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
