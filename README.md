# agents-shared

Shared Claude Code behavioural rules, skills, and commands — installed machine-wide
via `~/.claude/` symlinks, reaching every project on the machine.

**Maintaining this across several machines:** see
[docs/MAINTAINING-RULES.md](docs/MAINTAINING-RULES.md) — new-machine setup, keeping
machines in sync, and where a new rule belongs versus a skill, a project CLAUDE.md, or a
hook.

## Usage

### Install globally (one machine, every project)

Symlink everything into the user-level Claude dirs (`~/.claude/commands`,
`~/.claude/skills`, `~/.claude/rules`) so every project on the machine sees
these commands, skills, and rules:

```bash
bash scripts/init-global.sh           # sync ~/.claude with this repo
bash scripts/init-global.sh --unlink  # remove the symlinks it created
```

Idempotent — re-run after adding, renaming, or removing a command/skill. New
sources are linked, wrong-target links repaired, orphaned links (renamed/deleted
upstream) pruned, and real local override files left untouched. Honors
`CLAUDE_CONFIG_DIR` if set.

### Install local-only (per project, no repo footprint)

Symlink chosen skills from a standalone clone and hide them via
`.git/info/exclude` — no submodule, nothing in git status:

```bash
mkdir -p <repo>/.claude/skills
ln -s <clone>/claude/skills/handoff <repo>/.claude/skills/handoff
echo ".claude/skills/handoff" >> <repo>/.git/info/exclude
```

`git pull` in the clone updates all such repos at once. Exclude links by name,
not all of `.claude/`, so committed skills can coexist. Rarely needed — the
global install already reaches every project. Not automated by the scripts.

## Commands and skills

Not listed here — they are self-describing. Every command (`claude/commands/*.md`)
and skill (`claude/skills/*/SKILL.md`) carries its description in frontmatter,
which is exactly what Claude Code loads into each session. Browse the
directories; skills sourced from third-party repos carry a `source.json`.

Both create `/name` invocations. Skills are directory-based and may carry
references and templates; new extensions go in `claude/skills/`.

## Hooks

Not skills — shell scripts wired by hand into the `settings.json` of the Claude
config dir (`$CLAUDE_CONFIG_DIR`, else `~/.claude`).

| Hook | Event | Description |
|------|-------|-------------|
| `hooks/block-tree-discard.sh` | PreToolUse | Refuses git commands that discard uncommitted work; only `git checkout -- <one tracked file>` passes |
| `hooks/focus-policy.sh` | SessionStart | Tells the session whether this machine tolerates a window stealing keyboard focus |

### focus-policy.sh

Agents open windows: a Godot capture, a browser, a simulator. On a machine the
user is working on, that grabs focus mid-sentence, and an iteration loop does it
repeatedly. Whether it is acceptable depends on the **machine**, not the task, so
the answer belongs in the environment rather than in each session's judgement.

```bash
hooks/focus-policy.sh            # SessionStart — injects the verdict + guidance
hooks/focus-policy.sh --verdict  # "allow" | "deny"
hooks/focus-policy.sh --check    # exit 0 = allowed, 1 = denied
```

**Fails closed.** An unknown machine is `deny`: forgetting to allow one costs a
little convenience, forgetting to deny one costs the user their attention.

The allow-list is `focus-allow` in the Claude config dir (`$CLAUDE_CONFIG_DIR`,
else `~/.claude`) — one hostname or glob per line, `#` comments ignored. There is
no list in the script: machine names are local configuration, not shared source,
so a missing or empty file denies everywhere.

Wire it up in that same directory's `settings.json`:

```json
{ "type": "command", "command": "<abs-path>/hooks/focus-policy.sh", "timeout": 5 }
```

The matching standing rule lives in the user-level `CLAUDE.md` — the hook
reports the verdict, the rule says what to do about it.

## Updating

`git pull` in the clone. Edits to existing files take effect immediately — the
symlinks already point here. After a file is **added, renamed, or deleted**,
re-run `bash scripts/init-global.sh` to sync the links.

## Trial Skills

A skill worth trying is not yet a skill worth keeping. `scripts/trial-skill.sh`
installs one temporarily into `~/.claude/skills/` as a **real directory** — the
managed set are all symlinks, and `init-global.sh` never touches real
directories, so trials coexist with the permanent skills and are trivially
identifiable. Each trial carries a `.trial.json` (source repo, path, pinned
commit, install date), a superset of `source.json`, so promotion is lossless.

```bash
scripts/trial-skill.sh install <owner/repo> <path-in-repo> [--name <n>]
scripts/trial-skill.sh list              # every unmanaged dir, tracked or not
scripts/trial-skill.sh rm <name>         # delete a trial
scripts/trial-skill.sh promote <name>    # move into this repo as an external
                                         # skill: source.json from the trial
                                         # provenance, --establish-base, re-link
```

For a skill needed in one session only, skip installation entirely: fetch its
SKILL.md into scratch, read it, follow it.

## External Skills

Some skills are sourced from third-party repos. Each keeps a `source.json` (upstream repo, path, file list, pinned commit) alongside a `.upstream/` pristine base and, if we've adapted it, an `override.patch`.

Updates preserve local edits the way oh-my-zsh's `upgrade_oh_my_zsh_custom` does: rather than overwriting `SKILL.md`, the sync 3-way merges upstream's change into the working files against the stored base, replaying our edits on top. Conflicts are surfaced as markers, never silently dropped.

```bash
bash scripts/sync-external-skills.sh            # all external skills → upstream HEAD
bash scripts/sync-external-skills.sh caveman     # specific skill only
bash scripts/sync-external-skills.sh --establish-base [name]  # (re)build base + patch from the pin
```

See CLAUDE.md → *External (Third-Party) Skills* for the full model.
