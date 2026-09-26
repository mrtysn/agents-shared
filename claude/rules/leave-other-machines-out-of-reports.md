# Leave other machines out of reports

**A session's scope is the machine it runs on.** Do not assume the user has other
machines, and do not hand them steps to carry out on one. "Pull and run
`init-global.sh` on your other machines" or "move it into `synced/` if you want it on
other machines" is never an outstanding item, a next step, or a closing line.

Routine propagation — `git pull`, re-running a repo's install or init script,
promoting a file to a synced folder — is how these repos work, and the user
already knows it. Repeating it after every change is noise.

## The rare exception

Say it **once, in prose, as a fact** — no table row, no next step — only when this
session's change will break or behave differently on another machine in a way a
pull does not fix: a permission grant or other state outside git, a gitignored
local config the change now requires, a one-time migration. If it would not surprise
the user on that machine, leave it out.

## Where a file syncs is the user's call

Where a repo separates local from synced content (the notebook's root vs
`synced/`), put new files where its instructions say and name the path. Moving
them across is the user's decision; do not offer it.

## Provenance

Sep 2026: 46 messages in 30 sessions told the user to act on "other machines", most
seeded by maintenance docs' "On other machines: pull, then run the script" and
the notebook's "worth having on every machine → `synced/`". The user: "there is no
other machine", and "this is NEVER in the scope of what we are doing but has been
reported to me MANY times".
