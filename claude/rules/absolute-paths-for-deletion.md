# Deletions name their targets by absolute path

**Every `rm`, `rmdir`, `unlink` and `trash` operand must be a full path.** Not
`build`, not `./out`, not `../old` — `/Users/…/project/build`.

A relative delete is correct in one directory and catastrophic one level up, and
the cwd of a shell call is not something you can see. An absolute path carries
its own context, so a stale assumption about where you are cannot redirect the
delete at something else. This is the same failure as
[no hardcoded paths](no-hardcoded-paths.md) read from the other end: there, a
typed path is wrong on another machine; here, an *untyped* one is wrong in
another directory.

## The rules

- **Absolute only.** `/…`, `~/…` or `$HOME/…`. Nothing cwd-relative.
- **No globs in a delete.** `rm /abs/dir/*.tmp` deletes a set you never
  enumerated. List the directory first and delete the names, or delete the whole
  absolute directory in one command.
- **No unresolved variables or `$(…)`.** If the target cannot be read off the
  command line, it cannot be checked. Resolve it, then delete the literal path.
- **Never `/` or a top-level directory** (`/Users`, `/etc`, `/opt`).
- Same applies to the ways around the above: `find <abs-path> … -delete`, and
  `xargs rm` not at all — its operands arrive on stdin unverifiable.

## Enforcement

`agents-shared/hooks/require-absolute-rm.sh` is a `PreToolUse` Bash hook that
blocks every one of these, including inside `cd x && rm …`, behind `sudo`, and
inside a nested `sh -c "…"` or `eval "…"` — the command text is on the command
line, so it gets read. There is no override flag: a delete that genuinely cannot
be expressed as absolute literal paths is one the user runs in their own shell.

What the hook does **not** inspect is a deletion inside a script file, a make
target, or an npm script. That is not an invitation to route around it by
writing a script — it reflects that committed code establishes its own root and
is reviewed, which an improvised command is not. The rule above still applies to
anything you write.
