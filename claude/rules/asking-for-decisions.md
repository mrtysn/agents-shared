# Asking for decisions

**When a decision is genuinely the user's, ask with the AskUserQuestion tool.**
Never bury the ask in prose — no "say the word", "let me know if you'd like me to",
"I can do X if you want". A decision buried in a paragraph is a decision the user
has to re-type by hand.

## Each question must stand alone

The user should be able to decide from the question and its options alone, without
scrolling back through the transcript.

**Assume the prompt is the only thing that gets read.** In a long session the user
skims or skips the prose around a question and decides from the prompt alone. So the
question text itself carries the facts the decision turns on — what was found, what
is at stake, what was already assumed and why — not a pointer to "the table above".
If a finding matters to the choice and appears only in the surrounding message, it
has not been communicated.

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

## Naming: ask only for what the user types or sees

**Ask** for names the user will type or look at: slash commands and CLI tools they
invoke by hand, repo names, an app's visible name (Spotlight, menu, window title),
and folders in their home directory. This holds even mid-implementation.

**Pick without asking** everything only agents use — scripts agents run,
subcommands and flags agents call, modules, config keys, rule and doc filenames,
internal folders — and state the chosen name in the report. Optimize for an agent
reading it cold.

**Every name, picked or offered, says what the thing does** — verb-object where it
fits, two to four words, length no objection: `count-manual-commit-requests`,
`render-terminal-screen`. Never a short metaphor noun (`beat`, `desk`, `scout`,
`beacon`); descriptive beats ambiguous. Offered options meet the same bar, so the
user is not sent round again for "more descriptive".

**Name only what has been agreed.** A naming question is never the first the user
hears of a folder, command, or tool; settle that it exists and what it does first,
per [stated desires](stated-desires.md).

### Provenance

Sep 2026: 143 naming questions in 30 days; in 73 the user took none of the options.
The answers repeated: "optimize for agent use", "agents will use it, pick whatever
is best", "none of these are descriptive enough", "descriptive beats ambigious",
and "what data folder??? no way" for a name asked before the thing was agreed.
