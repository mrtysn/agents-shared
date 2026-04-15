---
description: Create a new GitHub repository under the active `gh` account, scaffolding standard files and pushing an initial commit. Use when the user asks to create a new repo for an existing or empty local directory.
argument-hint: [repo-name] [one-line description]
allowed-tools: Bash, Read, Write, Edit
---

# New Repo Skill

Create a fresh GitHub repository for the current working directory (or a new directory) and push an initial commit. Nothing about the user is hardcoded — read identity and paths from the environment.

## Required inputs (ask if missing)

1. **Repo name** — defaults to the basename of the current working directory if not given. Confirm.
2. **One-line description** — propose one from the project contents (README, package manifests, top-level source), then confirm with the user before using it.
3. **Visibility** — default `--private`. **Always** confirm explicitly before creating the remote; once pushed to a public remote, history cannot be fully retracted.

## Steps

### 0. Confirm and lock in the `gh` account

This is the first action of the skill. Do not run any other `gh` command before the user confirms.

```bash
gh auth status
```

Capture the account name on the line marked `Active account: true`. Ask the user **verbatim**:

> Is `<account>` the account you'd like to use for this repo?

Wait for an explicit yes. If the user names a different account, stop and instruct them to run `gh auth switch` themselves (it is interactive — do not run it). Re-run `gh auth status` after they switch, then ask the question again.

Once confirmed, **lock in the account** for the rest of the operation:

- Record the confirmed account as `LOCKED_ACCOUNT`.
- Immediately before step 5 (`gh repo create`), re-run `gh auth status` and verify the active account still matches `LOCKED_ACCOUNT`. If it drifted, abort and tell the user — do not auto-switch.
- Use `LOCKED_ACCOUNT` wherever the account name appears in user-facing echoes and in any post-push instructions (e.g., the SSH remote URL in the pitfalls section).

Git author is inherited from global config. If relevant (e.g., the user asks about attribution), read it with `git config user.name` and `git config user.email` — never hardcode.

### 1. Ensure a working directory

If the user is already in the target directory (the normal case), skip creation. Otherwise:

```bash
mkdir -p <path> && cd <path>
```

Prefer the user's current working directory over guessing a root like `~/dev/...`.

### 2. Initialize the git repo (if not already)

Check for `.git/` first. If absent:

```bash
git init -b main
```

If a `.git/` exists, inspect `git remote -v` before proceeding. If `origin` already points somewhere, stop and ask — do not remove or overwrite it.

### 3. Standard files

Only create what is missing; never overwrite existing files without asking.

- **`.gitignore`** — pick sensible defaults for the detected stack (look at file extensions, package manifests, lockfiles). Keep it minimal. If unsure, ask.
- **`README.md`** — one short paragraph describing what the project is. Draw from existing project files; do not invent features.

Ask the user before adding anything beyond these two.

### 4. First commit

```bash
git add <specific files>
git commit -m "init"
```

Stage specific files rather than `git add -A` to avoid accidentally committing secrets, build artifacts, or large binaries. The commit message is lowercase `init` — not `Initial commit`.

Respect repo-local conventions if they already exist (e.g., no Co-Authored-By trailer on personal repos).

### 5. Confirm visibility, then create remote and push

Re-confirm visibility with the user. Echo back: account, repo name, description, visibility — then wait for a clear go-ahead.

```bash
gh repo create <repo-name> \
  --private \
  --description "<one-line description>" \
  --source=. \
  --push
```

Swap `--private` for `--public` only after explicit user confirmation in this turn (a prior approval does not carry forward).

Report the resulting URL from `gh repo create`'s stdout.

## Flags reference

| Flag | Effect |
|---|---|
| `--public` / `--private` / `--internal` | Visibility |
| `--description "..."` | Short description shown on repo page and in `gh repo list` |
| `--source=.` | Use current directory as the repo source |
| `--push` | Push the current branch after creation |
| `--remote origin` | Name of the git remote (default `origin`) |
| `--homepage <url>` | Project homepage (e.g., live demo URL) |
| `--disable-issues` / `--disable-wiki` | Turn off features at creation time |

## Pitfalls

- **Wrong `gh` account active** — the repo lands on whichever account is active, not necessarily the one tied to the user's git author email. Always check `gh auth status` first and surface the account to the user.
- **HTTPS vs SSH** — `gh` uses HTTPS by default. To switch a specific repo to SSH afterwards: `git remote set-url origin git@github.com:<account>/<repo-name>.git`.
- **Default branch name** — `git init -b main` makes `main` the initial branch. Without `-b main`, older Git versions may default to `master`, which won't match GitHub's default.
- **Already has a remote** — `gh repo create` fails if `origin` already exists. Stop and investigate where that remote points before touching it; do not blindly remove it.
- **Hardcoded identity** — never write the user's name, email, or GitHub handle into repo content (LICENSE, README, etc.) without reading it from `gh auth status` / `git config` in that turn.
