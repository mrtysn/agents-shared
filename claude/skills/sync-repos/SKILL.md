---
description: Bring every repo under the dev root up to date with its remote. Runs `repo-survey --pull`, which fast-forwards each repo that can move with no conflict, then settles the repos it held back (diverged, uncommitted files in the way, a rebase in progress), asks which installed tools to rebuild and which apps to relaunch, and wires hooks a pull of agents-shared brought into the settings they are built from. Use when the user says "sync with git", "pull everything", "sync my repos", "update all repos", or invokes /sync-repos.
argument-hint: "[root folder, default $DEV_ROOT]"
allowed-tools: Bash, Read, AskUserQuestion
---

# Sync repos

The script does the safe part on its own; this session does the rest and asks only what is the
user's to decide.

## 1. Pull what moves safely

```bash
repo-survey --pull --json "${ARGUMENTS:-$DEV_ROOT}"
```

With no argument and no `$DEV_ROOT`, ask which folder holds the repos. One JSON object per repo:
`name`, `path`, `branch`, `upstream`, `ahead`, `behind`, `state` (`clean`, `dirty`, `staged`,
`untracked`, `NO REMOTE`, an operation marker), `action` (`pulled`, `held`, `none`), `reason`
for a held repo, `pulled.from`/`pulled.to` for a moved one. The script fast-forwards only a repo
that is only behind, on a branch, with no operation in progress, whose incoming commits touch none
of its uncommitted or untracked files. It never merges, rebases, stashes or resets.

For each pulled repo, read what came in: `git -C <path> log --oneline <from>..<to>`.

## 2. Settle the held repos

Read the repo's `CLAUDE.md` before running anything in it. Never stash, reset, check out over,
or discard anything: uncommitted files may be another session's live work, and the hooks refuse
those commands anyway.

| Reason | What to do |
|---|---|
| diverged, tree clean | The local commits are unpushed work. In a repo the commit rule calls the user's own, `git pull --rebase`; on a conflict, `git rebase --abort` and report the files. Run the repo's tests if its `CLAUDE.md` gates commits on them, then push. Elsewhere, report and leave it. |
| diverged, tree dirty | Replay in a worktree: `git worktree add --detach <scratch> <upstream>`, cherry-pick the local commits, test, push from there; then fast-forward the checkout with `git read-tree -m -u <old> <new>` and `git update-ref refs/heads/<branch> <new> <old>`, which refuse rather than overwrite a local edit. Remove the worktree. |
| uncommitted files the incoming commits change | Report the files and who holds them if a live session's cwd is that repo. Never move the repo; ask whether to leave it. |
| a git operation is in progress | Another session is probably mid-rebase or mid-merge. Report it; never abort or continue it. |
| fetch failed | Report the repo and the remote; check the network or the remote's name once, do not retry in a loop. |
| no upstream branch, detached HEAD | Report only. |

A repo the session settled is pulled again with `repo-survey --pull --json` on its parent folder,
so the record matches the tree.

## 3. Rebuilds and relaunches

```bash
project-lifecycle fleet --json --root "${ARGUMENTS:-$DEV_ROOT}"
```

Keep the rows whose `manifest` sits in a pulled or settled repo and whose `up_to_date` is
`false`: their installed copy is behind the source now on disk. A row of a repo that did not
move is not this run's business.

Ask with AskUserQuestion (multiSelect): one option per stale tool, `install <tool>` with its kind
and what came in, recommended first; last, "Install nothing". Then install the picked ones with
`project-lifecycle -C <repo> install` (`--no-hooks` only where the repo's docs say so), and run
`project-lifecycle fleet` again to confirm they read `current`.

Relaunch follows `rebuild-and-restart-local-tools-after-changes.md`: an install restarts a
background agent or menu bar app itself; a windowed app the user is not working on is left
running and named once ("rebuilt; quit and reopen X"); a repo whose `CLAUDE.md` reserves
relaunching to the user wins. Never relaunch with a plain `open`.

## 4. Hooks a pull brought

A hook runs only once a `settings.json` names it, and an install does not add the entry. When
agents-shared was pulled or settled, check the live settings against its README's hooks table:

```bash
"$AGENTS_SHARED/scripts/check-hooks-wired.py"
```

Exit 0 is silent. On exit 1, each line is one gap: `not wired: hooks/<name> under <event>`, or
`missing script: <event> runs hooks/<name>` for a hook the pull removed or renamed. Settle them
in the file the live settings are built from, never in the live file alone, which the next build
overwrites. On the owner's machines that is dev-env's `agents/claude/settings.json` (or a
profile overlay under `agents/claude/overlays/`; the README row says "personal profile only"
when the hook belongs in the personal one):

1. Read dev-env's README section on `settings.json` before editing it.
2. Add one entry per gap in the form the neighbouring entries use: the same
   `paths.local.sh` / `$AGENTS_SHARED_DIR` guard, `exec` of the script, `exit 0`, a 5 s
   timeout. Remove the entry of a missing script.
3. Rebuild the live file from it with dev-env's own step, `./import.sh --steps 12
   --non-interactive` from the dev-env folder (it backs up and rewrites each config folder's
   `settings.json` as base plus that folder's profile overlays). Then confirm
   `agents/claude/settings-profile.sh check "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"` exits 0
   and `check-hooks-wired.py` exits 0.
4. Commit and push dev-env per the commit rule.

Where no such source exists (`settings-profile.sh` is absent), the live file is the source:
edit it, and say so in the report. The new entry takes effect in sessions started afterwards.

## 5. Report

One line per repo that changed or needs something: pulled (`from..to`, commit count), settled
(how), held (why, and what was asked), installed. Repos that were already current and clean get
no row. End per `end-every-turn-with-a-next-step.md`.
