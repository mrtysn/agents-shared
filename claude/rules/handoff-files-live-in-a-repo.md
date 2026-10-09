# Files the user will open live in a repo, never in the scratchpad

**A file handed to the user — notes, a report, a screenshot, a render, a page —
is written inside a repo the work belongs to, never under the session
scratchpad, `/tmp`, `/private/tmp` or `/var/folders`.**

The scratchpad is deleted with the session, so the file is lost. iTerm also
does not make a `/private/...` path Cmd+clickable, so the user cannot even open
it while it exists. "For temporary files" means temporary to the agent: an
intermediate result, a scratch script, a download. Anything named in a reply
for the user to open is not temporary.

## Where it goes

- **Committed reference** (research notes, a write-up about the project): the
  project repo's `docs/`, then commit it.
- **Generated output** (screenshots, renders, check images): the project
  repo's gitignored output folder (e.g. `staging/`), so it stays out of git
  and still survives the session.
- **Not tied to one project**: the notebook, named per its conventions.

Name it by absolute path in the reply, per
[absolute paths for handoff](absolute-paths-for-handoff.md).

## Briefing a sub-agent

A sub-agent's brief names the repo path for any file it hands back. A brief
that says "write it to the scratchpad" produces exactly this failure; so does
leaving it unsaid, since a sub-agent defaults to the scratchpad.

## Provenance

Oct 9 2026, asset-pipeline: a research sub-agent was told to write its notes
under the session scratchpad, and another left its screenshots there. The
user: "your path choice is not good i would lose the file and i cannot even
cmd+click on the path from my iterm if it is under private path. have a fix
so that the agents dont repeat such a mistake".
