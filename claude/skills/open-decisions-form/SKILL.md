---
description: Put every decision still open in this session on one HTML decision form, each question carrying the context to decide from, so the form alone is enough. Runs only when the user asks for it. Use when the user invokes /open-decisions-form, or says "walk me through the outstanding items one by one", "make a form page for the open items", "put the decisions on a form", or "give me a document I can decide from". Not for a plain recap or a quick ask: /outstanding and /ask-open-decisions stay the default.
argument-hint: [optional scope hint, e.g. "just the node01 ones"]
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep, Write
---

The user wants every open decision on one page they can read and answer alone, one
item after another.

**Scope for this run:** $ARGUMENTS

Empty means every open decision in this session.

## Procedure

1. **Collect the decisions** the way /ask-open-decisions steps 1 and 2 do: everything whose
   next move needs a choice, an approval, a value or a credential, minus what the user
   already answered or the work has since settled. Decisions you could settle yourself are
   included, with your recommendation.
2. **Gather the context from the sources, not from memory of the session.** Per item, read
   the files, state and the user's own words on it again; check each fact the question
   rests on. A form already open for an item is reused as that item's question, never
   opened twice.
3. **Write one spec** per /new-html-page, decision-form mode: one question per item, in
   the order the user would want to decide them. Each carries what the thing is, why it is
   asked now, what is at stake, what each option does (`consequence`), one `recommended`
   option, and `multi` set.
4. **Scaffold, open, wait** as /new-html-page says: write the form in the repo the
   decisions concern (the notebook when several), run `decision-wait` in the background,
   give the form's absolute path on its own line, and stop.
5. **On submit, act on the answers** as on AskUserQuestion answers, and report what was
   done per item.
