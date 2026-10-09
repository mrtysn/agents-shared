---
description: Recap the current session — what got done, what remains outstanding, and where each item stands. Use when the user asks "any outstanding tasks?", "are there any outstanding tasks we have not covered / finished yet?", "any outstanding work we haven't covered?", "remind me what's left", "where were we", "recap what you did", or "did it work or not". Scope is this session only — for sessions killed by an iTerm relaunch, point the user at /iterm-revive instead.
argument-hint: [optional scope hint, e.g. "just code" or "include deploy"]
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep, Skill, AskUserQuestion
---

The user wishes to know where this session stands. Survey the work and render a clean account: what was accomplished, and every item still outstanding — nothing more, nothing less.

**Scope for this run:** $ARGUMENTS

If that line is empty, report everything. If it narrows the request ("just code", "ignore deploy"), filter to it.

## What counts as outstanding

Every item raised or touched in this session goes in exactly one of two lists. Nothing
raised is ever silently omitted — a misjudged classification must still be visible.

**Outstanding** — the only list the user glances at, so zero noise: next targets and open
decisions, nothing else.

1. **Discussed, not done** — a task, fix, or feature raised in this conversation that was never carried out.
2. **Started, not finished** — work begun but left partial (a stubbed function, a half-migrated pattern, a TODO left in the path).
3. **Done, not committed** — changes made but not staged, committed, pushed, or deployed.
4. **Blocked on you** — the next move needs a decision, credential, or answer only the user can give.

**Set aside** — everything raised that is *not* a next target, reported separately below the
outstanding items so that a wrong call is caught at a glance rather than lost:

- **Deferred** — the user postponed it in their own words ("later", "not now", "next pass", "after X"). Your guess that they will want it someday is not a postponement.
- **Decided, not doing** — "leave it", "keep it", "no", "not needed", or an offer of yours they turned down. A settled decision, not a postponement.
- **Dropped** — a later decision rescoped or replaced it ("HTTP only for now").

When unsure whether an item is a next target or set aside, it is a next target: a false
entry in Outstanding costs a glance, a missed task costs the task.

Not reported at all: backlog that comes only from project docs, roadmaps, or TODOs rather
than this conversation. Doc-derived backlog resurfacing in every session's report is noise.

Do NOT invent work. If nothing is outstanding, say so plainly.

## Procedure

1. **Scan this conversation** for every item in both lists above, and for completed work worth recalling. Prefer the user's own framing of each task over your paraphrase.

2. **Check the working tree** for uncommitted or unpushed work (skip if not in a git repo, or if `$ARGUMENTS` scopes you away from it):

   ```bash
   git status --porcelain=v1 --branch 2>/dev/null
   ```

   Uncommitted changes → category 3. An `ahead` count → unpushed commits. Absence of a git repo is not an error; just omit this section.

3. **Check for background shells.** Run `list-session-background-shells.sh --session <this session's id>` (in agents-shared `scripts/`, found by resolving the `~/.claude/skills/<this skill>` symlink) (the id is the UUID in the scratchpad path). Each line it prints is a still-running shell: list it as a `Running` item (pid, elapsed, command) whose next step is to stop it or confirm it is still wanted. No output, no item.

4. **Verify before asserting.** Conversation memory is a hypothesis, not evidence — items get closed out-of-band while this session sits idle. Before listing an item, check it against current state: `git log --oneline -15` for work committed since it was discussed, and re-read the actual file for any "still stubbed / still missing" claim. A state you could not verify is written as `Partial?` with a note, never asserted flat. The inverse also holds — before declaring "nothing outstanding" or "we are done", re-check the categories against the tree, not against your recollection.

5. **Surface anything blocked on the user first.** If closing an item needs a decision or answer only the user can give (category 4), it leads the report — the user is the bottleneck and should see it before anything they can't act on.

## Output format

Lead with a one-line verdict, then the account.

**If the ask includes a verdict question** ("did it work or not", "is it implemented", "is it ready to commit/deploy") — answer it in the first line, plainly: worked or didn't, committed or not, deployed or not. The itemized account follows.

**Done** — when the session accomplished real work, open with a short `**Done**` list before the outstanding items: one line per completed item, past tense, no elaboration. Skip the section entirely if nothing meaningful was completed or the user only asked what's left.

Then the outstanding items as **one continuous numbered markdown list** — never a table,
never a fenced code block. A table too wide for the terminal renders as stacked rows; a code
block paints every character in the code colour and still wraps long lines to column 0. A
markdown list wraps with a hanging indent, and inline code colours only what it wraps:

```
**Outstanding: 4**

1. `Blocked    ` Delete the safety copy ~/Downloads/elements-safety-copy (30 GB)
    - Needs your go-ahead. Both items in it were re-verified against Elements.
2. `Uncommitted` repair-ntfs-drive/README.md, the added "Pitfalls" section
    - git -C ~/dev/repair-ntfs-drive commit -am "document pitfalls" && git push
3. `Partial    ` Move the takeout zip (50 GB) to Elements pictures/photo-archive/
    - The byte check is running. The original is deleted only on a match.
4. `Not started` Delete the old UTM VM elements-chkdsk
    - utmctl delete elements-chkdsk
```

Layout, exactly:
- The state is the only inline code in an item, so it is the only colour on the line and
  the eye can run down the states. Paths, commands and URLs are written plain; backticks
  on them would compete with it.
- Pad the state with spaces *inside* the backticks to 11 characters, the width of
  `Not started` and `Uncommitted`, so every description starts in the same column. Claude
  Code keeps those spaces.
- The next step is a nested `- ` bullet under its item, indented four spaces — three is
  enough for `1.` to `9.`, but from `10.` on a three-space bullet falls out of the item. No
  `→`: the nesting already says it belongs to the item above.
- One list, numbered 1 to N. Never split it under per-state headings: Claude Code drops the
  nested indent on the first item of a list that starts at any number but 1, and the
  numbers are how the user and `ask-open-decisions` refer back to items.
- The same shape at every size, one item included — never switch to a sentence or a table.

Rules for the items:
- **Item** — name it as the user named it. No embellishment.
- **State** — exactly one of: Blocked, Uncommitted, Partial, Running, Not started. Never Deferred: deferred items belong to Set aside.
- **Next step** — one concrete, actionable move, anchored to where the work lives: a `file.cs:line`, a branch name, or the exact command. Not "finish it" — the actual edit or invocation. For a Blocked item, name the exact decision or answer you need.
- Order by what the user should see first: Blocked (needs them), then Uncommitted (cheapest to close), Partial, Running, Not started.
- **Self-contained** — no session-local shorthand: no "option B", "the fix", bare codes, or truncated links. Full repo-relative paths, full URLs, and enough words that each row reads cold, weeks later, without this conversation open.
- **Ownership** — if the user asks who does what ("which of these are you taking on yourself?"), split the report: **Mine** (items you will execute, and then execute them) vs **Yours** (decisions, commits, external steps). Never answer that question with an unowned task list.
- **No deferral framing** — never soften an item with "latent", "can wait", "if it goes live", "nice to have". Every item is either outstanding or it isn't; if it is in the Outstanding list, it is real work to be finished.

Then the set-aside list, after a blank line: a bold heading and one plain bullet per item,
no state tag and no next step, so it never reads as work:

```
**Set aside**
- <item, self-contained>. Decided, not doing: "<the user's words>"
- <item>. Deferred: "<the user's words>"
- <item>. Dropped: <what replaced it>
```

Quote the user's own words for Deferred and Decided, not doing, so a misreading is visible.
Skip the section when nothing was set aside.

## When nothing is outstanding

Do not manufacture a list. State it directly:

```
**Nothing outstanding.** Every task raised this session is done and the tree is clean.
```

If the tree is clean but the session is thin (no real tasks tackled), say that instead of implying completeness.

## Bearing

Direct and plain. No hedging, no padding, no "you might also consider" — only what genuinely remains. Produce the recap yourself, inline, in your reply — never hand it off to a subagent or point at a summary elsewhere; the user asked *you*, and the answer is the message. This skill reports; it does not act on the list by itself. After the report, run the last step below, then stop and wait for an explicit instruction before touching anything the user did not decide.

## Last step: ask the open decisions

The list records every item, Blocked ones included. Stop there and the user has to parse a
list and answer its decisions by hand. So once the report is written, if anything in it
needs a decision, approval, value, or answer from the user (Blocked rows, and any other row
whose next step is theirs), invoke the `ask-open-decisions` skill with the Skill tool. It
puts each one to the user through AskUserQuestion, self-contained, with your recommendation
first. If nothing needs the user, skip this step.
