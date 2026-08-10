# Maintaining the agent configuration across machines

How the behavioural rules, skills, and commands in this repo reach a machine, stay in
step across several machines, and get changed safely.

> **This file lives in `docs/`, not `claude/rules/`, on purpose.** `init-global.sh`
> symlinks *every* `.md` in `claude/rules/` into `~/.claude/rules/`, where Claude loads
> it as an instruction in every session. A README placed in there would be silently
> obeyed as a rule. Documentation goes here; only actual rules go in `claude/rules/`.

## The layers

Four things carry configuration, and they are not interchangeable.

| Layer | Lives in | Reaches a machine by | Shared across machines? |
|---|---|---|---|
| **Behavioural rules** | `claude/rules/*.md` (this repo) | `init-global.sh` → `~/.claude/rules/` symlinks | Yes — git |
| **Skills & commands** | `claude/skills/`, `claude/commands/` | same script → `~/.claude/skills`, `~/.claude/commands` | Yes — git |
| **Machine config** | `dev-env` repo | `dev-env/import.sh` | Yes — git, split base + per-machine |
| **Auto memory** | `~/.claude/projects/<project>/memory/` | nothing — Claude writes it | **No.** Machine-local by design |

`~/.claude/CLAUDE.md` is deliberately empty (a block HTML comment, stripped before
loading, so it costs zero tokens). Everything that used to be in it is now a rule file
here. Don't put content back in it — it isn't version-controlled.

## Setting up a new machine

```bash
git clone git@github.com:mrtysn/agents-shared.git ~/dev/agents-shared
bash ~/dev/agents-shared/scripts/init-global.sh
```

That creates `~/.claude/{rules,skills,commands}/` and symlinks every file in. It is
idempotent: re-running repairs wrong targets, links new files, and prunes symlinks whose
source disappeared. Real (non-symlink) files in those directories are treated as local
overrides and never touched.

Then `dev-env/import.sh` for shell, tmux, iTerm, and `~/bin` tooling.

Verify with `/context` in a session — every rule should appear under **Memory files**.

## Syncing an existing machine

```bash
git -C ~/dev/agents-shared pull
bash ~/dev/agents-shared/scripts/init-global.sh
```

The pull alone is enough for *edits* to existing rules — the symlinks already point at
the files. `init-global.sh` is only required when a rule was **added, renamed, or
deleted**. Running it regardless is harmless and is the safe habit.

There is no push-based sync. A machine gets changes when you pull on it.

## When a new rule arrives

Decide which layer it belongs to before writing anything:

| The instruction is… | Put it in | Why |
|---|---|---|
| A standing behaviour that should apply in **every** session | `claude/rules/<topic>.md` | Loaded at launch, everywhere |
| Only relevant to **one project** | that repo's `CLAUDE.md` | Loaded when working in that repo |
| Only relevant when working with **certain files** | that repo's `.claude/rules/` with `paths:` frontmatter | Loads on match, saves context |
| A **multi-step procedure** invoked on demand | `claude/skills/<name>/SKILL.md` | Loads only when invoked |
| Something that must run at a fixed moment, unconditionally | a **hook** in `settings.json` | Rules are context, not enforcement |
| Machine-specific, private, or a path | a **gitignored local file** | This repo is **public** |

To add a rule:

1. Write `claude/rules/<topic>.md`. One concern per file, kebab-case name.
2. `bash scripts/init-global.sh` to symlink it.
3. Commit and push.
4. On other machines: pull, then run the script.

Keep each file short and concrete — under ~200 lines total across all rules is the
target, since every one of them loads into every session. Cross-reference sibling rules
with a relative link rather than repeating their content.

## When a rule needs editing

Edit the file in `claude/rules/` — **never** the symlink in `~/.claude/rules/`, which
just points here. Commit, push, pull elsewhere. No re-run of `init-global.sh` needed for
a pure edit.

If a rule keeps getting violated, the fix is usually specificity, not volume: replace a
vague sentence with a concrete, checkable one. If it must be enforced rather than
encouraged, convert it to a hook.

## When a rule should be deleted

1. `git rm claude/rules/<topic>.md`, commit, push.
2. `bash scripts/init-global.sh` — the prune step removes the now-dangling symlink.
3. On other machines: pull, then run the script. **Skipping the script leaves a broken
   symlink in `~/.claude/rules/`.**

`bash scripts/init-global.sh --unlink` tears down every symlink this repo created,
leaving local overrides intact. Use it to fully detach a machine.

## Keeping auto memory in step

Auto memory is machine-local and is *not* synced. Where a rule here has a matching
`feedback_*` memory (the durable rule plus the story of why it exists), the memory should
point at the rule file by path rather than restating it. When a rule is deleted, delete
or correct its memory on each machine — a stale memory contradicting a current rule is
worse than no memory, because Claude may follow either.

## Consumer repos

Repos vendor this one as a `.agents` submodule and symlink skills/commands from it.
**Rules do not need the submodule**: they load from `~/.claude/rules/`, which points at
the standalone clone. Bumping `.agents` in a consumer is about that repo's skills and
commands, not about rules taking effect.

Bump consumers with `/broadcast-update` (uses `consumers.local`, gitignored).

## Checks

| Question | Command |
|---|---|
| Which instruction files loaded this session? | `/context` → **Memory files** |
| What is Claude's saved auto memory? | `/memory` |
| Are the symlinks correct and complete? | `bash scripts/init-global.sh` (reports `+new ~repaired -pruned`) |
| Any broken symlinks left behind? | `find ~/.claude/rules ~/.claude/skills ~/.claude/commands -type l ! -exec test -e {} \; -print` |
| Are all repos current across machines? | `repo-survey ~/dev` (from `dev-env/bin`) |
