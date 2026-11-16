---
description: Put the open items of this session on one HTML form that is enough on its own to decide the action points: a question per open decision, a do/defer/drop question per item that needs an action, the rest listed in the intro, and a free text box at the end. Runs only when the user asks for it. Use when the user invokes /open-decisions-form, or says "walk me through the outstanding items one by one", "make a form page for the open items", "put the decisions on a form", or "give me a document I can decide from". Not for a plain recap or a quick ask: /outstanding and /ask-open-decisions stay the default.
argument-hint: [optional scope hint, e.g. "just the server ones"]
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep, Write, Skill
---

The user wants every open item on one page they can read and answer alone, one after
another.

**Scope for this run:** $ARGUMENTS

Empty means every open item in this session.

## Procedure

1. **Collect the items** from the session's open work: what /ask-open-decisions
   ("Procedure", collect and drop-answered steps) and /outstanding list.
   - A **decision** (a choice, approval, value or credential only the user can give) gets a
     question with options. Decisions you could settle yourself are included, with your
     recommendation.
   - An **action item with no choice** (Not started, Partial, Yours) gets one question:
     do it now, defer it, or drop it, with what doing it involves in the context.
   - An item that **needs nothing from the user** (Running, Uncommitted) goes in
     `intro_html`, one line each, so the page is the sole document.
2. **Context from the sources.** Read the files, state and the user's own words on each
   item again; check each fact the question rests on. Follow /new-html-page decision-form
   step 1 and /ask-open-decisions "Assume the user read nothing else": the item named in
   full, no session shorthand, screenshots where the choice turns on something seen.
3. **An item that already has a form open** stays on that form: page-new never overwrites
   a file, so adding to it in place is not possible. Leave the item off the new page and
   name that form's absolute path in `intro_html`.
4. **Last question, free text.** A question with no options and `allow_other` left on is a
   text box. Heading "Anything to add or wrap up", skippable.
5. **Scaffold, open, wait** as /new-html-page says: write the spec and form in the repo the
   decisions concern (the notebook when several), run `decision-wait` in the background
   with no `--timeout`, give the form's absolute path on its own line, and stop. Nothing
   open: say so in one line and build no form.
6. **On submit, act in the order of the form.** A pick is acted on; free text that is an
   instruction is acted on; free text that asks something is answered and the item stays
   open; a note beside a pick is read with it; skipped and unanswered items are listed back
   as still open. Report one line per item: what the answer was and what was done.
