# Decide where a file lives by who will read it

**Before writing a file, ask who reads it. The session scratchpad, `/tmp`,
`/private/tmp` and `/var/folders` are only for files whose sole reader is this
agent, during this task.** Anything with another reader starts life in a repo:
the user, a later session, a sub-agent, a rerun, a reviewer.

The test: if this session ended now, would anyone want this file — including
an agent picking the work up tomorrow? If yes, it does not go in scratch.
"Copy it out if they ask" is the failure, not the plan: by the time someone
asks, the session may be gone, and a path under `/private` is not even
Cmd+clickable in iTerm.

## Scratch is for

Intermediates nobody else will open: a render read once to check a layout, a
fetched response parsed offline, a throwaway one-liner script, a download
being unpacked. When one turns out to have a reader, move it then and say so.

## Everything else goes to

- **Committed reference** (notes, write-ups, examples of how a tool behaves):
  the project repo's `docs/`, committed.
- **Generated output someone will look at** (screenshots, renders, sample
  pages): the project repo's gitignored output folder (e.g. `staging/`), so it
  stays out of git and still survives the session.
- **Not tied to one project**: the notebook, named per its conventions.
- **Scripts worth running again**: see
  [persist useful tooling](persist-useful-tooling.md).

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

Oct 10 2026, notebook: sample pages for every page-new mode were built in the
scratchpad as the agent's own render checks. When the user asked to see them
in Firefox they had to be copied out; had the session ended first, they were
gone. The rule had covered only files handed over, not files that would
plausibly be asked for.
