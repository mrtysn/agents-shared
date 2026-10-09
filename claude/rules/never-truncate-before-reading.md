# Never open a file for writing before reading it

**A file that already exists is edited with the Edit tool, or read into memory
first and written back from that copy — never in one expression that opens it
for writing and reads it.**

    open(path, "w").write(change(open(path).read()))   # empties the file first
    sed … file > file                                   # same, in the shell

The `"w"` open truncates the file to 0 bytes before the read runs, so the read
returns nothing and the file is written back empty. Whatever was only in the
working tree — another session's uncommitted lines — is gone, with no copy in
git, Time Machine or Claude's file history.

## What to do

- **Prefer the Edit tool** for any change to an existing file. It reads, matches
  and writes in one checked step.
- **In a script:** read into a variable, check it is not empty, transform, write
  to a temp file, then replace: `text = p.read_text(); assert text; tmp.write_text(new); tmp.replace(p)`.
- **Shared docs** (a file other sessions or agents also edit, such as a project's
  pipeline doc): Edit tool only. Stage your own lines from a HEAD blob
  (`git update-index --cacheinfo`) so others' uncommitted lines stay theirs.
- **Briefing a sub-agent** that will edit such a file: say this in the brief.

## Provenance

Oct 9 2026, asset-pipeline: four sub-agents in one session emptied
docs/PUPPET_PIPELINE.md this way. Three rebuilt it from memory; the fourth
emptying was found later and restored from HEAD. Another session's uncommitted
plush-clothing lines were lost.
