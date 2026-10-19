# Paths the user has to navigate to are absolute

**When you hand over a file path the user must act on outside the terminal, write
it as a full absolute path, on its own line.** Not `dist/extension.zip`, not
`./out/report.html`, not `~/dev/…` — `/Users/…/dev/project/dist/extension.zip`.

Outside the terminal means: attaching it to mail or WhatsApp, uploading it through
a browser file picker, dragging it into an app, importing a zip as a temporary
Firefox extension, revealing it in Finder — anywhere the path gets typed or pasted
into a dialog that has no cwd.

The text of an AskUserQuestion question is a message under this rule: a file it
names is written absolute there too, and the report holding it has been sent in
visible text first.

## Why a relative path is useless here

There are 20+ tabs open. Which directory a given session sits in is not visible at
a glance, and a file picker resolves neither `~` nor `./`. So a relative path costs
a full round trip — "full path please", then the answer that should have come the
first time.

## What stays relative

Code references — `src/foo.ts:42`, "see `scripts/build.sh`" — stay repo-relative.
Those are for reading, the terminal makes them clickable, and absolute paths would
only add noise. The rule covers paths that get *navigated to*, not paths that get
*read*.

When unsure which kind it is, absolute. A long path costs a line; a relative one
costs a turn.

## Related

Same instinct as [absolute paths for deletion](absolute-paths-for-deletion.md): a
path carrying its own context cannot be resolved against the wrong directory.
Distinct from [no hardcoded paths](no-hardcoded-paths.md), which governs what goes
in a *file* — this governs what goes in a *message*.

Provenance: [docs/provenance/absolute-paths-for-handoff.md](../../docs/provenance/absolute-paths-for-handoff.md).
