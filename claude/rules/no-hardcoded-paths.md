# No hardcoded paths

**No absolute or machine-specific path may be committed to a repo or a config.**
That includes `/Users/<name>/…`, `/home/<name>/…`, and any default that assumes one
particular machine's layout — a path is machine state, and committing it breaks the
repo on every other machine and leaks the layout (see
[machine details](#related)).

## The pattern

Committed file holds the *shape*; a gitignored local file holds the *value*.

1. **Gitignored local config** — `config.local.sh`, `.env.local`, `*.local.json`.
   Real paths live here and only here. Add it to `.gitignore`.
2. **Committed example** — the same filename plus `.example`, in the same directory,
   with placeholder values and a comment per field. This is the documentation.
3. **README/CLAUDE.md line** — one sentence: copy the example, fill it in.

The committed code reads the local file if present and fails with a clear message
if a required value is missing. It does not silently guess.

## Acceptable without a local config

Only paths *derived at runtime*, never typed:

- `$HOME`-relative where the location is genuinely conventional (`~/.config/…`)
- Script-relative: `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`
- Repo-relative: `git rev-parse --show-toplevel`
- An env var the caller sets, with **no** machine-specific fallback baked in

A hardcoded default "just as a fallback" is still a hardcoded path. If a value can
differ per machine, it belongs in the local config.

## Related

Same instinct as keeping machine and host inventories out of files entirely: what a
repo records about one machine is both wrong elsewhere and nobody else's business.
