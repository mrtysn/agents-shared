---
description: Register a script as a toolbelt entry — add a DESC comment, ensure executable, link it into ~/bin through the tools repo's installer so it shows in `toolbelt`. Use when the user asks to add a script to their toolbelt or wants a one-line invocation for an existing script.
argument-hint: [script-path] [one-line description]
allowed-tools: Bash, Read, Edit, Write
---

# New Tool Skill

Register a script with the user's `toolbelt` system. The toolbelt scans `~/bin` and `~/.local/bin` for executables containing a `# DESC: <one-liner>` line in their first 20 lines, and lists each as `<name>  <type>  <description>`.

**Register into `~/bin`, never `~/.local/bin`.** `~/bin` is the directory the user owns. `~/.local/bin` is the install target for uv, pipx, and most language package managers — they contend over it and refuse to overwrite each other's names, so a hand-placed symlink there is liable to be clobbered by an unrelated install.

## Required inputs (ask if missing)

1. **Script path** — the absolute path to the script being registered. May already exist or may be one you're about to write. Source files live in a repo, chosen by the placement rule in `persist-useful-tooling`; `~/bin` holds only symlinks.
2. **Tool name** — the invocation name (no extension). Defaults to the basename of the script with any `.sh` / `.py` / `.rb` extension stripped. Confirm before symlinking.
3. **One-line DESC** — propose one based on the script's purpose. Confirm with the user before writing. Format follows existing conventions: brief, present tense, em-dash for elaboration if needed (e.g., "Unity project sync — clean, pull, and update foundation submodule").

## Steps

### 1. Locate or create the script

If the user names an existing path, use it. For a fresh script, pick its home with the placement rule in `persist-useful-tooling` — a hand-invoked machine tool belongs in `$DEV_ROOT/tools/bin/`. Never put it in `dev-env`: that repo is dotfiles, and a program you invoke is not configuration. Never write the source directly into `~/bin` — keep source and symlink separate so the script is editable in its natural project location and travels with its repo.

Confirm the tool is missing from `~/bin` before proceeding — registering one twice produces a second entry that shadows the first. `tools/install.sh` links everything in `tools/bin/` in bulk, so a script already placed there and installed needs nothing further.

### 2. Verify shebang and DESC line

Read the first 20 lines of the script:
- Line 1 must be a `#!` shebang.
- Somewhere in the first 20 lines there must be a `# DESC: <text>` line.

If DESC is missing, insert it as **line 2** (immediately after the shebang). This is the existing convention — see `toolbelt`, `repo-survey`, `ffmpeg-progress`, etc.

### 3. Make it executable

```bash
chmod +x <script-path>
```

### 4. Link it through the manifest

`~/bin` holds only what `$DEV_ROOT/tools/install.sh` puts there, so the
installer creates the link, not you — never a bare `ln -s`.

- **Script in `tools/bin/`** — nothing to register; `install.sh` links every
  executable there.
- **Script anywhere else** (its own repo, `agents-shared/scripts/`) — add a line
  to `$DEV_ROOT/tools/links.txt`: `<tool-name>  <path relative to $DEV_ROOT>`,
  kept in alphabetical order.

Pre-check that the name is free, both in `~/bin` and in `links.txt`:

```bash
[[ -e "$HOME/bin/<tool-name>" || -L "$HOME/bin/<tool-name>" ]] && echo "already exists"
grep -E '^<tool-name>[[:space:]]' "$DEV_ROOT/tools/links.txt"
```

(`-e` alone misses broken symlinks; the `-L` clause catches dangling links too.)
If either finds something, stop and ask the user. Then run:

```bash
"$DEV_ROOT/tools/install.sh"
```

It never replaces a `~/bin` entry that points elsewhere — it prints a `!` line
instead. The `tools` repo now has a change to commit.

### 5. Verify

Run `toolbelt` and confirm the entry appears with the correct name, type (`bash` / `python` / `binary`), and DESC.

```bash
toolbelt | grep "<tool-name>"
```

If the entry doesn't appear, the most likely causes are: missing `# DESC:` line, DESC line beyond line 20, or the symlink landing outside `~/bin`.

## Pitfalls

- **Name collision in `~/bin`** — stop and ask. Don't overwrite or rename existing tools without explicit confirmation.
- **DESC line position** — `toolbelt` only scans the first 20 lines for `^#\s*DESC:`. Placement matters.
- **Hand-made symlink** — a link `install.sh` did not create is invisible to the next machine. Register it in `links.txt` instead.
- **`~/bin` not in PATH** — verify with `echo $PATH | tr ':' '\n' | grep -F "$HOME/bin"`. If absent, the symlink works but invocation-by-name doesn't; tell the user to add it to their shell rc.
- **Extension convention** — symlinks omit `.sh` / `.py` / `.rb` (e.g., `adb-keep-awake`, not `adb-keep-awake.sh`). Source files keep their extensions. The `toolbelt` listing uses the symlink name.
- **Don't write source into `~/bin`** — that directory is for symlinks. The source script lives in its project so it's editable in context and easy to find via `readlink`.
- **Compiled binaries use a sidecar `.desc` file**, not a `# DESC:` line. For Mach-O / ELF executables, `toolbelt` reads `<name>.desc` (first line) from the same directory as the binary. The sidecar sits beside the binary, not beside the symlink. This skill targets scripts; binary registration is a sibling workflow.
