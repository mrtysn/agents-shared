---
description: Update the vendored third-party skills from upstream, preserving local overrides through a 3-way merge. Use when the user asks to update, sync, or refresh external skills, or asks which skills are behind upstream.
argument-hint: [skill-or-group-name]
allowed-tools: Bash, Read, Edit
---

# Update external skills

Run from the `agents-shared` repo root. The mechanism is `scripts/sync-external-skills.sh`;
the model (`.upstream/` base, `override.patch`, 3-way merge) is in CLAUDE.md under
*External (Third-Party) Skills*. This skill is the procedure around it.

`$ARGUMENTS` is an optional skill name or group (`gamedev`, `interface:better-ui`).
Empty means every external skill.

## Traffic first

These are requests to GitHub from the user's IP. Before the first run, say the count:
one blobless fetch per distinct upstream repo (about 26 for everything), plus the blobs
of files that actually changed. Never loop the script to test; run each mode once.
A 429, 403 or any refusal ends the run: stop and report.

## Procedure

1. **Clean tree.** `git status` must show no uncommitted change under `claude/skills/`.
   Otherwise a sync's diff cannot be told from earlier work. Stop and say so.
2. **Preview.** `bash scripts/sync-external-skills.sh --dry-run $ARGUMENTS`. Writes nothing.
   Report the counts and the behind skills, conflicts first. If nothing is behind, stop.
   The summary's **Listing drift** section names skills where upstream added or deleted files
   compared with `source.json`'s `files`. A listed file deleted upstream makes that skill fail
   until the list is adopted. Whether to adopt is the user's decision, per skill: ask with
   AskUserQuestion, naming the files added and removed. On yes:
   `bash scripts/sync-external-skills.sh --adopt-listing <name>`.
3. **Sync.** `bash scripts/sync-external-skills.sh $ARGUMENTS`. For a very large set, sync
   by group so each commit stays reviewable.
4. **Resolve conflicts.** A conflicted skill has markers (`<<<<<<< local`, `=======`,
   `>>>>>>> upstream@<short sha>`) in the working file and an un-advanced base. Read both
   sides and keep our `<!-- LOCAL -->` intent. When upstream rewrote the section so the
   markers cannot be merged line by line, fetch upstream's new file into the scratchpad,
   take it whole, and re-apply our local edits onto it. Never leave markers committed and
   never drop a local override to make a conflict go away.
   **Re-running the script does not finish a conflict**: the working file already holds
   upstream's change, so the merge would repeat it. Advance the skill by hand instead:
   set `source.json`'s `commit` to the full SHA (`git ls-remote` it; it must start with the
   short sha in the markers, else upstream moved and the merge must be redone) and `updated`
   to today, then `bash scripts/sync-external-skills.sh --establish-base <name>`. That
   refetches the files at the new pin into `.upstream/` and regenerates `override.patch`
   from the resolved working files.
5. **Check.** Read the diff of each updated skill that carries an `override.patch`:
   the local change must still be present and still make sense against the new text.
   If upstream renamed or removed a file, `source.json`'s `files` list needs the matching edit.
6. **Wire.** If a skill directory was added or removed upstream-driven, run
   `bash scripts/init-global.sh`. A pure content edit needs nothing.
7. **Commit atomically** per skill or group, in the repo's style, and push. Message e.g.
   `update caveman skill from upstream`. Stage only paths you changed.

## Report

Say per skill: updated, already current, conflicted-and-resolved, or failed, and name any
override that needed manual merging. Failures (a failed fetch or a missing upstream file) are
listed with the reason and left alone.
