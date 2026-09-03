# Persist tooling that turned out to be useful

Scratch scripts written to a temp/scratchpad directory during a task are deleted
with the session. **If a script would be worth running again, move it into a repo
before the task ends** — do not leave a useful tool in `/tmp`, and do not silently
delete it.

This applies to anything built to answer a question that will be asked again:
survey scripts, migration helpers, checkers, one-off analyses that became routine.
It does not apply to genuinely single-use scratch (a regex applied to four files
once) — say that it was throwaway and let it go.

## Where it goes

Every tool gets a container. Pick by *who invokes it*:

| Scope | Home | Notes |
|---|---|---|
| Useful only inside one project | that repo's `scripts/` or `tools/` | Default. Most tools are this. |
| Operates on Claude sessions, memory, or the agent setup | `agents-shared/scripts/` | Alongside `blame-session.py`, `search-history.py`, `standup-collect.sh`. |
| Hand-invoked tool for the dev machine | `tools/bin/` | Then `/new-tool` to symlink it into `~/bin`. `tools/install.sh` does the same in bulk. |
| Substantial enough to carry its own README, assets, or build | its own repo | Precedent: `make-icon`, `launchpad-map`, `ff-profile-diff`. |

**Never `dev-env`.** That repo is dotfiles — configuration plus the bootstrap
that places it. A program you invoke is neither, however convenient its
`import.sh` machinery looks. Ten tools accumulated there before this rule was
corrected; do not restart the pile.

A new repo is right when a tool has real scope; the shared `tools` repo is right
for everything smaller. Do not leave it in scratch either way.

## Before it lands

A scratch script becomes repo code, so it has to meet the bar:

- `#!/bin/zsh` unless it must be portable — see [shell scripts](shell-scripts.md)
- **No hardcoded paths** — see [no hardcoded paths](no-hardcoded-paths.md). A scratch
  script almost always has one baked in; take an argument or derive it instead.
- A `# DESC: <one-liner>` line under the shebang, per the toolbelt convention
- `set -euo pipefail`, quoted expansions, and a `--help` if it takes arguments
