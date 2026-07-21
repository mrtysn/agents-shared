---
description: Recap the current session — what got done, what remains outstanding, and where each item stands. Use when the user asks "any outstanding tasks?", "are there any outstanding tasks we have not covered / finished yet?", "any outstanding work we haven't covered?", "remind me what's left", "where were we", "recap what you did", or "did it work or not".
argument-hint: [optional scope hint, e.g. "just code" or "include deploy"]
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep
---

The user wishes to know where this session stands. Survey the work and render a clean account: what was accomplished, and every item still outstanding — nothing more, nothing less.

**Scope for this run:** $ARGUMENTS

If that line is empty, report everything. If it narrows the request ("just code", "ignore deploy"), filter to it.

## What counts as outstanding

An item is outstanding if any of these hold:

1. **Discussed, not done** — a task, fix, or feature raised in this conversation that was never carried out.
2. **Started, not finished** — work begun but left partial (a stubbed function, a half-migrated pattern, a TODO left in the path).
3. **Done, not committed** — changes made but not staged, committed, pushed, or deployed.
4. **Blocked on you** — the next move needs a decision, credential, or answer only the user can give.
5. **Deferred by decision** — something explicitly postponed ("later", "not now", "next pass") — record it so it is not forgotten.

An item is **not** outstanding if:

- **A later decision removed it** — rescoped, replaced, or explicitly dropped ("HTTP only for now"). Dropped is not Deferred; it does not appear at all.
- **It comes from project docs, roadmaps, or TODOs** rather than this conversation. Doc-derived backlog resurfacing in every session's report is noise; only work raised or touched in this session qualifies.

Do NOT invent work. If nothing is outstanding, say so plainly.

## Procedure

1. **Scan this conversation** for the five categories above, and for completed work worth recalling. Prefer the user's own framing of each task over your paraphrase.

2. **Check the working tree** for uncommitted or unpushed work (skip if not in a git repo, or if `$ARGUMENTS` scopes you away from it):

   ```bash
   git status --porcelain=v1 --branch 2>/dev/null
   ```

   Uncommitted changes → category 3. An `ahead` count → unpushed commits. Absence of a git repo is not an error; just omit this section.

3. **Verify before asserting.** Conversation memory is a hypothesis, not evidence — items get closed out-of-band while this session sits idle. Before listing an item, check it against current state: `git log --oneline -15` for work committed since it was discussed, and re-read the actual file for any "still stubbed / still missing" claim. A state you could not verify is written as `Partial?` with a note, never asserted flat. The inverse also holds — before declaring "nothing outstanding" or "we are done", re-check the categories against the tree, not against your recollection.

4. **Surface anything blocked on the user first.** If closing an item needs a decision or answer only the user can give (category 4), it leads the report — the user is the bottleneck and should see it before anything they can't act on.

## Output format

Lead with a one-line verdict, then the account.

**If the ask includes a verdict question** ("did it work or not", "is it implemented", "is it ready to commit/deploy") — answer it in the first line, plainly: worked or didn't, committed or not, deployed or not. The itemized account follows.

**Done** — when the session accomplished real work, open with a short `**Done**` list before the outstanding items: one line per completed item, past tense, no elaboration. Skip the section entirely if nothing meaningful was completed or the user only asked what's left.

Then the outstanding items. Group only if there are enough items to warrant it.

```
**Outstanding — <N> item(s)**

| # | Item | State | Next step |
|---|------|-------|-----------|
| 1 | <what it is, in the user's terms> | Blocked / Uncommitted / Partial / Not started / Deferred | <the single concrete action> |
```

Rules for the table:
- **Item** — name it as the user named it. No embellishment.
- **State** — exactly one of: Blocked, Uncommitted, Partial, Not started, Deferred.
- **Next step** — one concrete, actionable move, anchored to where the work lives: a `file.cs:line`, a branch name, or the exact command. Not "finish it" — the actual edit or invocation. For a Blocked item, name the exact decision or answer you need.
- Order by what the user should see first: Blocked (needs them), then Uncommitted (cheapest to close), Partial, Not started, Deferred last.
- **Self-contained** — no session-local shorthand: no "option B", "the fix", bare codes, or truncated links. Full repo-relative paths, full URLs, and enough words that each row reads cold, weeks later, without this conversation open.
- **Ownership** — if the user asks who does what ("which of these are you taking on yourself?"), split the report: **Mine** (items you will execute, and then execute them) vs **Yours** (decisions, commits, external steps). Never answer that question with an unowned task list.
- **No deferral framing** — never soften an item with "latent", "can wait", "if it goes live", "nice to have". Every item is either outstanding or it isn't; if it's in the table, it's real work to be finished.

If a single item dominates (e.g. only uncommitted changes remain), skip the table and state it in a sentence with the exact command to close it.

## When nothing is outstanding

Do not manufacture a list. State it directly:

```
**Nothing outstanding.** Every task raised this session is done and the tree is clean.
```

If the tree is clean but the session is thin (no real tasks tackled), say that instead of implying completeness.

## Bearing

Direct and plain. No hedging, no padding, no "you might also consider" — only what genuinely remains. Produce the recap yourself, inline, in your reply — never hand it off to a subagent or point at a summary elsewhere; the user asked *you*, and the answer is the message. This skill reports; it does not act. List the work, then stop — wait for an explicit instruction before touching any of it.
