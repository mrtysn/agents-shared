---
description: Get an independent second opinion from a fresh Fable subagent on a plan, a finished piece of work, an estimate, or a judgment call — briefed blind so it is not anchored on this session's view. Use when the user says "ask a fable subagent", "ask fable", "unbiased opinion", "vet this", "weigh in on this", "have a fable agent review the plan", or names another model for the same purpose (opus, sonnet). Runs only on the user's ask, never on its own.
argument-hint: [what to review, optional]
user-invocable: true
allowed-tools: Agent, SendMessage, AskUserQuestion, Read, Bash, Glob, Grep
---

The user wants a verdict from an agent that has not been talking to this one. Its value
is that it is not anchored on this session's plan, so every step below protects that.

**Subject for this run:** $ARGUMENTS

If that line is empty, the subject is what the user's last message points at: the plan,
output or question under discussion.

## 1. Spawn a fresh agent, never a fork

A `fork` inherits this conversation and therefore its bias. Use the `Agent` tool with a
non-fork `subagent_type` and set `model`: `fable` by default. A model the user names
(opus, sonnet) wins. Omit `effort` for `fable` and `opus`, per the sizing table the
Agent hook prints on a session's first spawn.

## 2. Write a blind brief

The brief can only be unbiased by omission: this session cannot neutrally summarise its
own position. It holds:

- **The question**, in the user's words, verbatim.
- **The artifact by absolute path** — the plan, the diff, the page, the file. Say what
  to read and let the reviewer read it. A paraphrase is where this session's stance
  leaks back in.
- **Constraints the user stated**, quoted, not restated: their exact words, or left out.
  A one-line summary of several of their rules is this session's reading, not a quote.
- **The task:** answer the user's question, finding what is wrong or missing first, then
  what holds. "Looks fine" is acceptable only with what was checked named. Do not name
  this session's suspect or hypothesis ("whether X is involved"): it steers the reviewer
  to the same place. Hypotheses go in the confront round.
- **Review only:** no edits, no file writes. Ranked findings, about 250 words,
  conclusions not file dumps.

It does **not** hold this session's conclusion, recommendation, "we decided", or why the
plan is good. Where the user wants the reviewer to know what already exists, point at the
files and let it check them itself.

**Read budget.** Name the exact files and line ranges the question turns on, and leave
out files it does not. A reviewer that reads a whole rules file or script it did not need
adds that file to every later request. Any command it is told to run gets a line range
or a size cap (`--since`, `head -n`, a result limit); an uncapped extraction of a large
transcript is the same cost. Neutral numbers this session already computed
(a count, a size) go in with how they were derived, so the reviewer can re-check them.
Never a summary of what a file says: that is this session's reading, and the stance
rides in with it.

**A question about which fix to build** (a rule, skill, trigger row, hook, mod or
script): add `$AGENTS_SHARED/docs/choose-the-fix-for-a-pattern.md` to the files to read,
resolved to its absolute path. It is a reference table, not this session's view, so it
does not breach the blind brief.

**A plan that exists only in chat** is saved to a file as this session's message, word
for word. Cut whole paragraphs, never sentences, and only paragraphs that address the
user (second person, or a decision put to them); keep every paragraph that describes the
plan. A recommendation on a decision ("build it together", "make it a nudge") is a
decision put to the user: cut it. When the plan sits inside a longer message, cut the
unrelated sections whole as well. Write nothing of this session's own into the file, not
a framing paragraph and not the open decisions. In the brief, say how many paragraphs
and sections were cut, counting the unrelated ones, and put each open decision as a
neutral question ("warn when a habit is older than the logs: yes or no"). The remaining
paragraphs were written to persuade; tell the reviewer the text is a message to the user
so it can discount the tone.

## 3. Confront, once

When the independent answer arrives, send this session's position to the same agent with
`SendMessage` and ask for a critique of it. Mark each claim in that position as
**checked** (and how) or **assumed**, so the reviewer spends its reads on the assumed
ones; a claim stated from memory is assumed. The agent has now given its unanchored read,
so the second round tests this session's view without contaminating the first. Stop there
unless the user asks for another round: each round spends Fable quota.

## 4. Relay both halves

The user has not read the subagent's report, per
[restate hidden output](../../rules/restate-hidden-output-in-replies.md). Write into the
reply:

- The reviewer's independent verdict and its main findings.
- The critique it gave of this session's position.
- Where it **disagrees** with this session: state the disagreement plainly, say which
  view this session now holds and why. Never "the fable agent agrees" as a summary, and
  never a blended answer that hides the split.
- Anything that remains a genuine fork goes to the user through `AskUserQuestion`, but
  only after both halves above are written out in prose. The question text quotes both
  views itself: a question that does not reads as "we agree". A closing "shall I make
  the change?" is also asked with `AskUserQuestion` after the relay, never as a sentence
  in prose.

Say uncertainty up front. The second opinion exists because an agent presented a guess
as a finding; the fix is stating the guess as one.

The reply holds, in order: the verdict, the critique, this session's stance, then any
question. A view this session changed because of the reviewer is named as changed.

## Measuring a run

When the user asks what a run cost, run
`agents-shared/scripts/report-subagent-token-use.py <session id> --match 'review|opinion|vet'`
(resolve the path through the `~/.claude/skills/vet-fable` symlink). It prints each
reviewer's requests, starting and ending context, and cache reads and creates. Do not
rebuild the numbers by hand from the transcripts.
