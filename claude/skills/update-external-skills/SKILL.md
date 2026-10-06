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
one `ls-remote` per distinct upstream repo, plus one GET per vendored file of each
skill that is behind. Never loop the script to test; run each mode once.
A 429, 403 or any refusal ends the run: stop and report.

## Procedure

1. **Clean tree.** `git status` must show no uncommitted change under `claude/skills/`.
   Otherwise a sync's diff cannot be told from earlier work. Stop and say so.
2. **Preview.** `bash scripts/sync-external-skills.sh --dry-run $ARGUMENTS`. Writes nothing.
   Report the counts and the behind skills, conflicts first. If nothing is behind, stop.
3. **Sync.** `bash scripts/sync-external-skills.sh $ARGUMENTS`. For a very large set, sync
   by group so each commit stays reviewable.
4. **Resolve conflicts.** A conflicted skill has markers (`<<<<<<< local`, `||||||| base`,
   `>>>>>>> upstream`) in the working file and an un-advanced base. Read both sides,
   keep our `<!-- LOCAL -->` change and take upstream's intent, remove the markers,
   re-run the script for that skill to advance the base and regenerate `override.patch`.
   Never leave markers committed and never overwrite a local override to make a conflict go away.
5. **Check.** Read the diff of each updated skill that carries an `override.patch`:
   the local change must still be present and still make sense against the new text.
   If upstream renamed or removed a file, `source.json`'s `files` list needs the matching edit.
6. **Wire.** If a skill directory was added or removed upstream-driven, run
   `bash scripts/init-global.sh`. A pure content edit needs nothing.
7. **Commit atomically** per skill or group, in the repo's style, and push. Message e.g.
   `update caveman skill from upstream`. Stage only paths you changed.

## Report

Say per skill: updated, already current, conflicted-and-resolved, or failed, and name any
override that needed manual merging. Failures (`ls-remote` or missing upstream file) are
listed with the reason and left alone.
