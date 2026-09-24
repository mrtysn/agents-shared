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
| `hooks/memory-lint.sh` | PreToolUse (`Edit\|Write`) | Keeps auto-memory index lines topic-only and refuses a memory that duplicates a rule |
| `hooks/dump-hook-stdin.sh` | any | Probe: writes the JSON a hook event receives to a file, then allows the call |
| `hooks/system-one-start.sh` | SessionStart | Brings up the system-one decision-model server in the background; reports one line, never blocks |
| `hooks/system-one-bash.sh` | PreToolUse (`Bash`) | Scores each command for destructiveness with the decision model; shadow mode logs, act mode asks (never denies) |

### memory-lint.sh

`MEMORY.md` loads into every session in its project; the memory files load only
on recall. A fact in an index line is therefore paid for in every session and
is where private detail leaks. On any `Edit` or `Write` under
`<config>/projects/*/memory/` this checks the two halves a script can check:

- a new or changed index line must be a topic label — no digits, no currency
  symbol, at most 12 words after the dash. Entries whose file says
  `type: feedback` are exempt, because a prohibition has to fire before the
  mistake and so keeps its instruction in the line
- a memory file being created must not share its slug with a rule in
  `<config>/rules/`

Only lines being introduced are judged, so rewriting an index that already
carries old offenders is not blocked for them. The rule that says what to
write is `claude/rules/memory-hygiene.md`; this refuses what it can detect.

**Fails closed**, like the other PreToolUse guards. Cases in
`hooks/tests/memory-lint-cases.tsv`, run with `hooks/tests/run-memory-lint.sh`.

```json
{ "matcher": "Edit|Write", "hooks": [{ "type": "command", "command": "…/hooks/memory-lint.sh", "timeout": 10 }] }
```

### dump-hook-stdin.sh

Point any hook event at it and it writes the JSON it received to
`$HOOK_STDIN_OUT` (else `<config>/hook-stdin.json`), then exits 0. That answers
"what does this event actually get?" — which fields `tool_input` carries, what
`cwd` and `permission_mode` look like — before writing a hook that depends on it.

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

The session-start line reads `Focus policy: ALLOW · quiet-open: /path` (or
`quiet-open: not installed`). The verdict is a tolerance for the interruption,
not a licence: a window that activates hides a hotkey terminal on either kind of
machine, so windowed apps go through `quiet-open` (the `tools` repo) under either
verdict, and only an app it cannot quiet becomes an ask. `--verdict` and
`--check` are consumed by scripts and never change shape.

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

The matching standing rule is `claude/rules/window-focus.md` — the hook
reports the verdict and whether `quiet-open` is present, the rule says what to
do about both.

### system-one

A local decision model (Laya, one warm server on loopback) that answers typed
questions (`choice`, `score`, yes/no `noul`) about a text state with calibrated
probabilities, for the bounded checks the exact guards cannot enumerate. Design,
measurements and the evaluation plan: `notebook/2026-09-24-system-one-decision-model-integration.md`.

`scripts/system-one` is the wrapper (`start`, `stop`, `status`, `ask`,
`shadow-report`, `install`; `roster` is a stub until the prompt hook lands). It
reaches `~/bin` through the tools repo's `links.txt`. Copy
`scripts/system-one.local.sh.example` to `${CLAUDE_CONFIG_DIR:-~/.claude}/system-one.local.sh`
and set `SYSTEM_ONE_VENV`; the port (7811), idle exit (30 min) and mode have
defaults there, and the Bash hook's thresholds live in the questions file with
`SYSTEM_ONE_BASH_ASK_<QUESTION>` as the override.

- `system-one-start.sh` runs `system-one start` at SessionStart (it returns at
  once; the server takes about 4 s to load and is warm by the first Bash call).
  Nothing else starts it; a start lock keeps two sessions from launching it twice;
  a watchdog stops it by pid after the idle period. `stop` and the watchdog signal
  only the pid they wrote, and only while that pid is still `laya-serve`, never a
  port or a name.
- `system-one-bash.sh` builds `cwd: ...\ncommand:\n...` (each heredoc body cut to
  its first two lines plus a marker by `hooks/system-one-bash-state.awk`), asks the
  four yes/no questions in `hooks/system-one-bash-questions.json` (foreign process,
  irreversible, leaves the machine, network install) and pipes them to
  `system-one ask --fail-open --gate` with that file's thresholds. **Shadow** and
  **show** modes append the verdict to the shadow log and emit nothing (identical
  behaviour; `show` only tells `status`, the status line and Agent Bar Hopping the
  user has opted in to seeing verdicts there); **act** mode emits
  `permissionDecision: "ask"` naming the question that fired. Fails open
  everywhere: no config, no server, timeout. Flip to act only on the user's word,
  after the evaluation plan in the design doc.
- Agents needing a bounded judgment: `echo '{"state": "...", "questions": {...}}' | system-one ask`.
  Do not start Python or the server yourself.

Shadow log: one file per session, `${XDG_STATE_HOME:-~/.local/state}/system-one/shadow/<session_id>.jsonl`
(no session id: `shadow/_nosession.jsonl`), one JSON object per call (hook, latency,
sha256 and length of the state, every answer, `would_act`, `acted`, and for the
Bash hook the command itself, which labelling needs). `system-one shadow-report`
summarises every file under `shadow/`, or one with `--session <id>`; `status`
counts lines across all of them. A flat `shadow.jsonl` from before this layout is
split by `session_id` into `shadow/` the first time `status` or `shadow-report`
runs, and renamed to `shadow.jsonl.migrated`. Cases in
`hooks/tests/system-one-bash-cases.tsv`, run with `hooks/tests/run-system-one-bash.sh`,
which reports agreement with the expected column and fails only on a hook error,
output in shadow mode, or a call over 2 s.

**Show mode**: the status line and the Agent Bar Hopping app (`cc-statusline`
repo) read the session's shadow log and draw the four gate scores as a fourth
row whenever the user has turned that display on and the log file exists,
whatever `SYSTEM_ONE_MODE` is (see
`notebook/2026-09-24-system-one-decision-model-integration.md` section 9). The
mode name `show` exists only so `status`, the status line and the app can say
the user has chosen to see verdicts; nothing in system-one itself renders the
row, and the log is the only interface between the two repos.

## Updating

`git pull` in the clone. Edits to existing files take effect immediately — the
symlinks already point here. After a file is **added, renamed, or deleted**,
re-run `bash scripts/init-global.sh` to sync the links.

## Skill Groups

External packs live in **groups**: a directory under `claude/skills/` holding a
`.claude-plugin/plugin.json` and a `skills/` folder of skills. Claude Code loads
such a directory as a plugin named `<group>@skills-dir` — discovered in place
through the symlink, no marketplace, no install, no cache copy — and its skills
are invoked as `/<group>:<skill>`. Grouping is what makes a pack switchable:

```bash
claude plugin disable gamedev@skills-dir --scope user     # off everywhere
claude plugin enable  gamedev@skills-dir --scope project  # on for this repo, committed
claude plugin list                                        # what is on here
claude plugin details gamedev@skills-dir                  # what it costs in context
```

A disabled group costs nothing; an enabled one loads its skill descriptions like
any other skill. Skills the machine's owner wrote stay flat under
`claude/skills/<name>/` and keep their bare `/<name>`.

`scripts/skill-tree.py` draws all of this as one page on loopback — every group
with its skills, the description cost, and the switches: a group per scope for
the project you pick, a skill inside a group as auto or slash-only (a fenced
frontmatter edit in this repo, override.patch regenerated), a flat skill through
the four `skillOverrides` states. It reaches `~/bin` as `skill-tree` through the tools repo's `links.txt`;
`scripts/make-skill-tree-app.zsh` wraps it as *Skill Tree* in `~/Applications`
for Spotlight.

Grouped skills follow the external-skill convention below, one `source.json` per
skill under `<group>/skills/<name>/`; the sync script finds both layouts, and a
group name as its argument syncs the whole group. A skill switched off sits in
`<group>/off/<name>/` instead, which no session scans; nothing inside it changes,
so its slash-only setting and provenance survive the move, and the sync script
still updates it there.

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
