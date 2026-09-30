---
description: Ask the user every decision still open in this session with the AskUserQuestion tool — one self-contained question per decision, your recommendation first — instead of leaving them listed in prose or a table. Use when the user invokes /ask-open-decisions, says "ask me the questions", "ask me the open questions", "ask them via the ask user question tool", or when a long reply listed decisions the user now has to answer by hand. /outstanding runs it as its last step.
argument-hint: [optional scope hint, e.g. "just the deploy ones"]
user-invocable: true
allowed-tools: AskUserQuestion, Bash, Read, Glob, Grep
---

The user wants the open decisions put to them as questions they can answer by
picking, not as text they have to read, parse, and answer by hand.

**Scope for this run:** $ARGUMENTS

If that line is empty, cover every open decision. If it narrows the request, ask only those.

## Assume the user read nothing else

This is the governing constraint. The user skims or skips long replies, including the
one just above. Each question is read **alone**, possibly weeks from now, with nothing
else on screen. So each question carries everything the decision turns on:

- **What the thing is.** Name the file, feature, tool, service, or number in full. No
  session shorthand: no "option B", "the fix", "the second approach", "as above", bare
  codes, or names coined earlier in this conversation without restating them.
- **Why it is being asked now.** The finding or constraint that makes it a decision.
- **What each option does and what follows from picking it.** One line of substance per
  option, in the option's description. Not "A or B?".

A question that makes sense only to someone who read the conversation has failed, however
accurate it is.

## Procedure

1. **Collect every open decision** in this session: anything whose next move needs a
   choice, an approval, a value, a credential, or an answer only the user can give.
   Sources: your recent replies (tables, "your call", "want me to…", "say the word",
   "open questions", "needs you"), proposals the user has not answered, and Blocked items.
   Do **not** filter out decisions you could have settled yourself. Ask them too, with
   your recommendation first: the user sees what you would do and still decides.

2. **Drop what is already answered.** Re-read the user's messages after each decision
   was raised; a decision they already made is not open. Check current state (git log,
   the file) for any decision the work itself has since settled.

3. **Write one question per decision.**
   - `question` — the full context from the section above, ending in a question mark.
     Two to four sentences is normal. Length is fine; missing context is not.
   - `header` — at most 12 characters, naming the subject (`Deploy`, `Cache TTL`,
     `Tailscale`), not the question type.
   - `options` — two to four, mutually exclusive. **Your recommendation is first, with
     `(Recommended)` at the end of its label.** Each description says what happens if
     picked. Include "leave it as is" / "drop it" when that is a real choice. Never add an
     "Other" option; the tool provides one.
   - `multiSelect` — only when the choices genuinely combine.
   - `preview` — when options are concrete artifacts to compare side by side (a layout,
     a snippet, a config), put each one in its option's preview.

4. **Ask in rounds of at most four questions** (the tool's limit), most consequential
   first: decisions that block other work, then irreversible or outward-facing ones,
   then the rest. Continue with the next round after each answer until none are left.
   A question the user answered with a counter-question or a note is still open: answer
   it and ask it again, rewritten with what was learned.

5. **Close with a record** of what was decided: a short table, one row per decision,
   `Decision | Chosen | What happens next`. Then carry out the chosen actions that
   belong to this session's work. A pick is an instruction, and the user already chose.
   Outward-facing or irreversible actions were themselves the question, so an explicit
   pick of one is the confirmation.

## When there is nothing to ask

Say so in one line: `No open decisions in this session.` Do not invent questions to
have something to ask.

## Bearing

Plain, direct, peer to peer. No preamble before the first question beyond one line
saying how many decisions are open. The questions are the deliverable, not a summary of
them.
