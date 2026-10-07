---
description: Start a new repo of scripts or config files that get symlinked from the checkout into the home directory (a toolbelt into ~/bin, dotfiles, skills) on the project-lifecycle pipeline, then create its GitHub repo. Use when the user wants a home for several small scripts or files that should be on PATH or in a dot-directory on every machine.
argument-hint: [repo name]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
---

# New Symlinks-into-home Skill

Scaffold a repo whose deliverable is symlinks into the home directory with
`project-lifecycle init symlinks-into-home`, prove its install in a scratch home, then hand the
directory to `/new-repo`. The template lives in project-lifecycle (`project_lifecycle/init.py`);
any agent can run the command without this skill.

Before scaffolding, check whether the thing belongs in an existing repo of this kind: a
hand-invoked script for the dev machine goes into the `tools` repo's `bin/` (`/new-tool`), a
skill or rule into `agents-shared`. A new repo is for a set with its own scope.

## Required inputs (ask if missing)

Ask with AskUserQuestion only for what the user will see or type:

1. **Repo name** — what the directory and the first script are called (`backup-scripts`).
   The tool slug derives from it.
2. **Where the links go** — `~/bin/` (scripts on PATH, the default the template writes) or
   another dot-directory the user names; the template's `links` entry is edited to match.

## Steps

1. **Directory**: the current directory if it has none of `project-lifecycle.json`, `bin/`,
   `CLAUDE.md`; otherwise `mkdir` the slug under the current directory and `cd` into it.
   `init` refuses to overwrite and names what is in the way: stop and report, never delete.
2. **Scaffold**:

       project-lifecycle init symlinks-into-home --name "<Repo Name>" [--tool <slug>]

   Relay the files it wrote: the manifest (`links: bin/* → ~/bin/`), `bin/<slug>` (a
   placeholder zsh script with a DESC line), `CLAUDE.md`.
3. **Prove it**: `project-lifecycle test` must pass, then an install into a scratch home:
   `HOME=$(mktemp -d) project-lifecycle install --json` must report ok with the link count;
   remove the scratch directory by its absolute path afterwards. Do not install into the
   real home here; the user does that with `project-lifecycle install` once the scripts exist.
4. **Repo**: invoke `/new-repo` with the Skill tool, passing the slug and a one-line
   description.
5. **Report**: the directory (absolute path), the slug, where to add scripts (`bin/`), and
   the commands `project-lifecycle install` and `project-lifecycle status`.

## What the scaffold already does

- `install` links every match of `links` into the target directory, repairs a link that
  points elsewhere, refuses to replace a real file, and prunes links into this checkout whose
  target is gone; `uninstall` removes the links; `status` reports ok, missing, elsewhere,
  file and stale counts, which `fleet` shows. A repo with an installer of its own names it
  as `install_command` and the driver runs that instead.

## Pitfalls

- **Never link with `ln -s` by hand**; a hand-made link is state no repo records. The manifest
  and `install` are the record.
- **A real file in the way is never replaced**; the install stops and names it, and the user
  decides.
