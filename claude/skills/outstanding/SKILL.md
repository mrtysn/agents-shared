---
description: Report what work remains outstanding in the current session — tasks discussed but not done, implemented but not committed, or deferred. Use when the user asks "any outstanding tasks?", "any outstanding work we haven't covered?", or "remind me what's left".
argument-hint: [optional scope hint, e.g. "just code" or "include deploy"]
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep
---

The user wishes to know what remains unfinished. Survey the work of this session and render a clean account of every outstanding item — nothing more, nothing less.

**Scope for this run:** $ARGUMENTS

If that line is empty, report everything. If it narrows the request ("just code", "ignore deploy"), filter to it.

## What counts as outstanding

An item is outstanding if any of these hold:

1. **Discussed, not done** — a task, fix, or feature raised in this conversation that was never carried out.
2. **Started, not finished** — work begun but left partial (a stubbed function, a half-migrated pattern, a TODO left in the path).
3. **Done, not committed** — changes made but not staged, committed, pushed, or deployed.
4. **Blocked on you** — the next move needs a decision, credential, or answer only the user can give.
5. **Deferred by decision** — something explicitly postponed ("later", "not now", "next pass") — record it so it is not forgotten.

Do NOT invent work. If nothing is outstanding, say so plainly.

## Procedure

1. **Scan this conversation** for the five categories above. Prefer the user's own framing of each task over your paraphrase.

2. **Check the working tree** for uncommitted or unpushed work (skip if not in a git repo, or if `$ARGUMENTS` scopes you away from it):

   ```bash
   git status --porcelain=v1 --branch 2>/dev/null
   ```

   Uncommitted changes → category 3. An `ahead` count → unpushed commits. Absence of a git repo is not an error; just omit this section.

3. **Surface anything blocked on the user first.** If closing an item needs a decision or answer only the user can give (category 4), it leads the report — the user is the bottleneck and should see it before anything they can't act on.

## Output format

Lead with a one-line verdict, then the itemized account. Group only if there are enough items to warrant it.

```
**Outstanding — <N> item(s)**

| # | Item | State | Next step |
|---|------|-------|-----------|
| 1 | <what it is, in the user's terms> | Blocked / Uncommitted / Partial / Not started / Deferred | <the single concrete action> |
```

Rules for the table:
- **Item** — name it as the user named it. No embellishment.
- **State** — exactly one of: Blocked, Uncommitted, Partial, Not started, Deferred.
- **Next step** — one concrete, actionable move. Not "finish it" — the actual command or edit. For a Blocked item, name the exact decision or answer you need.
- Order by what the user should see first: Blocked (needs them), then Uncommitted (cheapest to close), Partial, Not started, Deferred last.

If a single item dominates (e.g. only uncommitted changes remain), skip the table and state it in a sentence with the exact command to close it.

## When nothing is outstanding

Do not manufacture a list. State it directly:

```
**Nothing outstanding.** Every task raised this session is done and the tree is clean.
```

If the tree is clean but the session is thin (no real tasks tackled), say that instead of implying completeness.

## Bearing

Direct and plain. No hedging, no padding, no "you might also consider" — only what genuinely remains. This skill reports; it does not act. List the work, then stop — wait for an explicit instruction before touching any of it.
