---
description: Extract learnings from a source into confirmed principles and spread the general ones to their homes. The source is a repo with build sessions, or a page given by URL or saved file. Use when the user says "extract learnings", "what can we learn from X", "survey this page for design principles", "survey this repo for what we learned", "turn this into principles", or points at a page or project they admire and wants its lessons kept. For someone else's page it extracts principles to apply in the user's own work and never copies the page's look or text.
argument-hint: [repo path, URL or saved page]
user-invocable: true
allowed-tools: Agent, AskUserQuestion, Skill, Read, Write, Edit, Bash, Glob, Grep
---

Turn a source into learnings the user has confirmed one by one, then put the general ones
where future sessions meet them. Every step below ends in something on disk.

**Source for this run:** $ARGUMENTS

## 1. Source

**A repo with build sessions.** Read the code and the full git history, reversals
included (`git show` on each revert or rewrite). Read the user's typed messages from its
build sessions only through `$AGENTS_SHARED/scripts/extract-session-text.py`, never a
parser of your own ([never hand-roll a transcript parser](../../rules/never-hand-roll-a-transcript-parser.md);
the `mine-chat-logs` skill has the recipe).

**A page by URL or saved file.** Keep a saved copy and fetch it once, under
[no unprompted account traffic](../../rules/no-unprompted-account-traffic.md). Take
headless screenshots at 375 and 1280 px, light and dark, and record each interaction
(hover, focus, scroll, open, drag). Open it in the user's browser only per
[window focus](../../rules/window-focus.md).

## 2. Survey with subagents

Split the source into areas and give each a subagent. Where an independent read matters,
brief it blind as `vet-fable` does: the source and the question, not your view. Each item
returns the format in `references/survey-item.md`: the principle, the lesson from any
reversal, the evidence, and whether it is specific to this source or general.

Evidence is a file and line, a commit, the user's quote with its session id, or a page
region with its screenshot. An item with none is dropped.

For someone else's page, the item is the principle behind the choice (why the spacing
works, what the interaction teaches), never its look or text.

## 3. Decision form

Load `new-html-page`, decision-form mode. One question per learning: keep, keep as
principle only (drop the source-specific parts), or drop, each with a note box. Reversals
are one multi-select with every box ticked. Add one question per design fork. Wait for
the answers file before writing anything.

## 4. Learnings page

Write the page in the notebook as `YYYY-MM-DD-<slug>-learnings/`, from a Markdown file
with `project-lifecycle page-new --from-markdown`. Layout and section order are in
`references/page-layout.md`. One topic per page: a later survey of a related source adds
a section to the existing page and is not a new file.

## 5. Spread the general ones

Only learnings the user kept as general. Map each to its home, extending the doc that
exists and never duplicating it:

| The learning is about | Home |
|---|---|
| how an interface behaves | `docs/on-demand/interface-behaviour.md` |
| a tool that changes the user's data | `docs/on-demand/tools-that-change-the-owners-data.md` |
| the checks for one kind of page or tool | that kind's own docs (`web-shared` DESIGN.md, `project-lifecycle` docs/STYLE.md) |
| the one project | its `CLAUDE.md` |
| how agents behave | a rule or trigger row, chosen by `docs/on-demand/choose-the-fix-for-a-pattern.md` |

This repo is public: no quotes, private names, paths or hashes, and only made-up
examples. Run `scripts/check-personal-split.zsh` and `scripts/check-skills.zsh`. Commit
each home's change on its own ([commit atomically](../../rules/commit-atomically-as-you-build.md));
a push to a public repo waits for the user's approval.

## 6. Optional review

When the user asks, run `vet-fable` on the page and the spread, giving it the files and
not your conclusions.

Close with what each learning became and where it now lives.
