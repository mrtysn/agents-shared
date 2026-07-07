---
description: Report what work remains outstanding in the current session — tasks discussed but not done, implemented but not committed, or deferred. Use when the user asks "any outstanding tasks?", "any outstanding work we haven't covered?", or "remind me what's left".
argument-hint: [optional scope hint, e.g. "just code" or "include deploy"]
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep
---

The user wishes to know what remains unfinished. Survey the work of this session and render a clean account of every outstanding item — nothing more, nothing less.

$ARGUMENTS

## What counts as outstanding

An item is outstanding if any of these hold:

1. **Discussed, not done** — a task, fix, or feature raised in this conversation that was never carried out.
2. **Started, not finished** — work begun but left partial (a stubbed function, a half-migrated pattern, a TODO left in the path).
3. **Done, not committed** — changes made but not staged, committed, pushed, or deployed.
4. **Deferred by decision** — something explicitly postponed ("later", "not now", "next pass") — record it so it is not forgotten.

Do NOT invent work. If nothing is outstanding, say so plainly.

## Procedure

1. **Scan this conversation** for the four categories above. Prefer the user's own framing of each task over your paraphrase.

2. **Check the working tree** for uncommitted or unpushed work (skip if not in a git repo, or if `$ARGUMENTS` scopes you away from it):

   ```bash
   git status --porcelain=v1 --branch 2>/dev/null
   ```

   Uncommitted changes → category 3. An `ahead` count → unpushed commits. Absence of a git repo is not an error; just omit this section.

3. **Honor the scope hint.** If `$ARGUMENTS` narrows the request (e.g. "just code", "ignore deploy"), filter accordingly. Absent a hint, report everything.

## Output format

Lead with a one-line verdict, then the itemized account. Group only if there are enough items to warrant it.

```
**Outstanding — <N> item(s)**

| # | Item | State | Next step |
|---|------|-------|-----------|
| 1 | <what it is, in the user's terms> | Not started / Partial / Uncommitted / Deferred | <the single concrete action> |
```

Rules for the table:
- **Item** — name it as the user named it. No embellishment.
- **State** — exactly one of: Not started, Partial, Uncommitted, Deferred.
- **Next step** — one concrete, actionable move. Not "finish it" — the actual command or edit.
- Order by readiness to act: Uncommitted first (cheapest to close), then Partial, Not started, Deferred last.

If a single item dominates (e.g. only uncommitted changes remain), skip the table and state it in a sentence with the exact command to close it.

## When nothing is outstanding

Do not manufacture a list. State it directly:

```
**Nothing outstanding.** Every task raised this session is done and the tree is clean.
```

If the tree is clean but the session is thin (no real tasks tackled), say that instead of implying completeness.

## Bearing

Direct and plain. The verdict comes first; the reader should know the count before reading a single row. No hedging, no padding, no "you might also consider" — only what genuinely remains.
