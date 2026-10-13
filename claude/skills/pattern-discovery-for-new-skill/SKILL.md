---
description: Find out whether something the user keeps typing deserves a skill. Scours recent transcripts for prompts like the one they give, reports how often and how fast it is growing, explains why they do it, and says what a skill would need to contain. Use when the user says "scour my recent chats for my patterns", "how often do I ask for X", "I got tired of asking the same thing", or wants to know if a repeated request should become a skill.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: <the message or habit to look for>
---

# pattern-discovery-for-new-skill

The user types the same request again and again. This skill measures it, explains
it, and says whether it earns a skill. It builds nothing: the report is the
deliverable, and a skill is built only when they say so.

## Steps

1. **State the habit in one line**, from their example prompt: what they ask for,
   of whom, at what moment. Ask nothing; take the example as given.

2. **Write two or three regexes** that every instance would contain: one for the
   thing asked for, one for the purpose. Use alternation inside each. Run:

   ```bash
   python3 "${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/scripts/find-repeated-user-prompts.py" \
     --days 30 --pattern 'REGEX' --pattern 'REGEX' --skip-prefix 'Reply with exactly'
   ```

   It prints matches per week, per project, busiest days, then one line per
   match. `--full` shows whole prompts, `--json` gives them as data.
   Transcripts reach back about 30 days, so `--days 60` adds nothing.

3. **Fix the pattern, then count again.** Read the match lines. Drop false hits
   (the session you are in, test harness prompts, pasted logs) and look for near
   misses the regexes lack: phrasings with the same intent but other words. Search
   those with a looser pattern and merge them. Report the corrected count, not the
   raw one.

4. **Read the contexts.** For a sample of about eight matches, read what came
   before the prompt (`extract-session-text.py <session-id> --kinds user,assistant
   --grep '<phrase>'`). Look for what triggered the ask: a plan just written, an
   answer the user doubted, finished work, a mistake.

5. **Group the instances** into two to four kinds by moment or purpose, with a
   count each and one verbatim example.

6. **Explain the pattern** in the user's words: quote the prompt where they say
   why, if one exists ("you got biased").

7. **Say whether it earns a skill.** It does when the phrase repeats weekly or
   more, the instances share a purpose, and the right response has steps worth
   fixing (a brief to write, a model to choose, a way to read the result). It does
   not when each instance needs different judgment. Name what the skill would
   hold, and who owns any skill already covering it (`ls claude/skills`).

## Report

Plain words, short. In order: count and window; trend; the kinds with counts; why
the user does it; verdict on a skill and what it would contain; the command line
used, so the count can be repeated. Quote prompts verbatim; give the count of
sessions beside the count of prompts.

Offer nothing beyond the verdict. Building the skill is a separate ask.
