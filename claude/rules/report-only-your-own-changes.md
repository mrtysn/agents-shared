# Report only your own changes

**Anything you did not create or change gets no row in any list you output** —
git status summaries, /outstanding tables, commit reports, cleanup summaries,
and pasted `ls` output alike.

A stranger's untracked file is not a loose end. Listed, it becomes a chore the
user never asked for and implies the tree is dirtier than your changes made it.
Labelling it "pre-existing, not mine" is still listing it.

- Filter listings before showing them; never print the raw directory and
  annotate the foreign rows.
- Pre-existing files may be mentioned in prose when genuinely relevant — no
  row, no state, no next step.
- Keep excluding them from staging, silently.

## Provenance

Corrected twice in Aug 2026: a pre-existing untracked script listed as an
outstanding item after a commit, and an unrelated personal file included in a
cleanup summary with a "not mine" label.
