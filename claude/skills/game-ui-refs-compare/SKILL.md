---
description: Compare a screenshot of your own game UI against a /game-ui-refs brief — which patterns it already follows, concrete gaps with fixes, and ideas from the reference screens — and record the comparison under that brief in the ledger viewer. Use when the user wants a screen checked against references, asks how their screen compares with other games, or hands over a screenshot of their UI for critique against a brief.
context: fork
argument-hint: <screenshot path> [brief id] [label]
allowed-tools: Read, Bash
---

# game-ui-refs-compare

Compare: **$ARGUMENTS**

The first argument is the path of a screenshot of the user's own screen. An argument
shaped like a brief id (`20260914-153036-pause-menu`) names the brief; anything else is
a label for this iteration ("build 212", "after the redesign").

If no screenshot path was given, or the file does not exist, return immediately asking
for one. This skill never takes screenshots itself.

Everything it needs is already in the ledger — the `game-ui-refs` repo:

```bash
REF="${DEV_ROOT:?run agents-shared/scripts/init-global.sh to set it}/game-ui-refs"
REC="$REF/scripts/record.py"
```

If `$REC` does not exist, return `The ledger is not cloned here — clone mrtysn/game-ui-refs into $DEV_ROOT first.` and stop.

**Never open the reference websites.** Every reference picture needed is a local file
under `$REF/images/`. This skill makes no web requests at all.

## 1. Look at the screenshot

Read the screenshot. Name what screen it is in a few words (pause menu, level select,
daily reward popup) and note what is visible: layout, every control and its label,
hierarchy, what stays on screen behind it.

## 2. Pick the brief

- A brief id was given: use it.
- Otherwise run `"$REC" find <the screen's name> <platform, if known>` and take the top
  line at 100%.
- No match at 100%: return `No brief on <screen> yet — run /game-ui-refs <screen> first.`
  and stop. Do not compare against a brief about a different screen.

Then read it and its history:

```bash
"$REC" show <brief id>
"$REC" compare-list <brief id>
```

For earlier comparisons, `"$REC" compare-render <id>` shows their gaps — note which are
now fixed and which remain.

## 3. Look at the references

Read the pictures, from the brief's `screens[].image` (paths relative to `$REF`):

- every example's and every variation's screen (`screen` indexes into `screens`);
- then, for any pattern the screenshot seems to break, one or two of the screens that
  pattern names.

At most 20 pictures. They are the evidence; the brief's words are the summary.

## 4. Judge

Go pattern by pattern through the brief:

- **Follows** — the screenshot visibly does what the pattern describes. Cite the pattern's
  index.
- **Gap** — it does not, and the difference matters for this screen. Every gap names a
  concrete fix: which element, where it moves, what it says, what changes colour or
  size. Point at the reference screen that shows the fix best.
- **Idea** — a variation from the brief that would suit this game, with its screen.

Be specific to what is in the picture. No generic advice ("improve hierarchy"), and no
gap for something a still image cannot show — motion, sound, timing. A pattern that
does not apply to this game is neither followed nor a gap; leave it out.

The summary is two or three sentences: how close the screen is to the norm, the one
change that would matter most, and — when there are earlier comparisons — what has
improved since the last one.

## 5. Record

```bash
"$REC" compare-add - <<'JSON'
{
  "brief": "<brief id>",
  "subject": "<game> <screen>",
  "label": "<label, or omit>",
  "capture_file": "<absolute path of the screenshot>",
  "summary": "<two or three sentences>",
  "follows": [{"text": "<what it already does>", "pattern": 0}],
  "gaps":    [{"text": "<what is missing or off>", "fix": "<the concrete change>", "pattern": 2, "screen": 67}],
  "ideas":   [{"text": "<a variation worth trying here>", "screen": 27}]
}
JSON
```

`compare-add` stores a shrunk copy of the screenshot, commits, pushes and publishes. The
screenshot's path is not recorded. A `comparison rejected` message lists what to fix —
usually an index outside the brief's patterns or screens; fix the JSON and run it again.

## 6. Return

Return `"$REC" compare-render <id>` verbatim, then the status lines `compare-add`
printed. The viewer shows the comparison under its brief, beside the reference pictures.
