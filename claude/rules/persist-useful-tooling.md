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

No new repo. Pick by *who invokes it*:

| Scope | Home | Notes |
|---|---|---|
| Useful only inside one project | that repo's `scripts/` or `tools/` | Default. Most tools are this. |
| Operates on Claude sessions, memory, or the agent setup | `agents-shared/scripts/` | Alongside `blame-session.py`, `search-history.py`, `update-consumers.sh`. |
| Hand-invoked shell tool for the dev machine | `dev-env/bin/` | Synced by `dev-env`; symlinked into `~/bin`. Register with `/new-tool`. |

If a tool genuinely fits none of these, say so and propose a home — do not default
to leaving it in scratch.

## Before it lands

A scratch script becomes repo code, so it has to meet the bar:

- `#!/bin/zsh` unless it must be portable — see [shell scripts](shell-scripts.md)
- **No hardcoded paths** — see [no hardcoded paths](no-hardcoded-paths.md). A scratch
  script almost always has one baked in; take an argument or derive it instead.
- A `# DESC: <one-liner>` line under the shebang, per the toolbelt convention
- `set -euo pipefail`, quoted expansions, and a `--help` if it takes arguments
