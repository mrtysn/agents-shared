# Asking for decisions

**When a decision is genuinely the user's, ask with the AskUserQuestion tool.**
Never bury the ask in prose — no "say the word", "let me know if you'd like me to",
"I can do X if you want". A decision buried in a paragraph is a decision the user
has to re-type by hand.

## Each question must stand alone

The user should be able to decide from the question and its options alone, without
scrolling back through the transcript.

- **Explain each option inside the option**, briefly — what it means and what
  follows from picking it. Not "A or B?" but one line of substance per choice.
- **Put the recommended option first** and mark it `(Recommended)`.
- **Batch related decisions** into one call rather than asking serially.

## When not to ask

Routine judgment calls, conventional defaults, and anything answerable by reading
the code — decide those and say what was decided. Asking is for cases where
different answers produce materially different work.

## The one required ask

Outward-facing or hard-to-reverse actions still need confirmation before running:
publishing, pushing to a remote that doesn't exist yet, sending anything to a third
party, deleting or overwriting. Confirming these is not hedging and does not
conflict with [chasing the ideal](chase-the-ideal.md) — but ask for that
confirmation with the tool, not with a sentence.
