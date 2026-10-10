# Decide where a file lives, and what it is, by who will read it

**Before writing a file, ask who reads it. The answer sets its place and its
format.**

| Reader | Where | Format |
|---|---|---|
| this agent, during this task | the session scratchpad, `/tmp` | anything |
| the user | the repo the work belongs to, or the notebook | an HTML page from `/new-html-page` |
| a later session, a sub-agent, a rerun | the repo | Markdown, JSON, whatever it parses |
| a consumer with its own format (a blog post, a GitHub README, a CLAUDE.md) | where it reads from | its format |

The session scratchpad, `/tmp`, `/private/tmp` and `/var/folders` hold only the
first row. The test: if this session ended now, would anyone want this file —
including an agent picking the work up tomorrow? If yes, it does not go in
scratch. "Copy it out if they ask" is the failure, not the plan: by the time
someone asks, the session may be gone, and a path under `/private` is not even
Cmd+clickable in iTerm.

## The user reads pages, not Markdown

The user reads in the browser and the terminal, never a `.md` file. A report,
survey, comparison, plan or write-up for them is a page made with
`/new-html-page`, its mode chosen by the content. A short answer belongs in the
reply, not a file.

**A skill's own output format does not override this.** When a skill writes its
report as Markdown (`deep-research` saves `reports/{title}.md`), that file is an
intermediate: run `project-lifecycle page-new --from-markdown <file> --mode
<mode>`, finish the page with the mode's components, render-check it, and hand
over the page. The `.md` stays beside it as its source.

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

A sub-agent's brief names the repo path for any file it hands back, and its
format: a page if it writes for the user, Markdown if it writes for you. A brief
that says "write it to the scratchpad" produces exactly the failure above; so
does leaving it unsaid, since a sub-agent defaults to the scratchpad and to
Markdown.

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

Oct 10 2026, notebook: a deep-research session handed over its report as the
`.md` the skill writes. The user: "I would rather have them use these templates
and do an html output for me … i dont really read md files anymore, browser and
terminal it is".
