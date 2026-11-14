# Sign a script app before it asks for a permission

A script app (`osacompile`) or any app signed ad-hoc (`codesign -s -`) is known to macOS by
its binary hash and the generic name `applet`. An Accessibility or Automation grant made to
it never matches, and each rebuild voids it.

Before the first launch, and before sending the user to any permission pane:

1. Give it its own bundle id. `osacompile` writes none, so `Set` fails; use `Add`:
   `/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string in.mertyas.<name>" <app>/Contents/Info.plist`
2. Sign it with the local certificate and that identifier:
   `codesign --force --deep -s "Local Dev Signing" --identifier in.mertyas.<name> <app>`
3. Only then ask for the grant, once.
4. Launch it once after the grant. An alert that comes back means the identity is wrong:
   do not send the user back to the pane, and do not relaunch in a loop.

An app that clicks a menu item through System Events opens the menu first (`click menu bar
item "<Menu>" of menu bar 1`, then a short `delay`). A closed menu reports its items as
disabled, and clicking a disabled item does nothing and raises no error, so the app exits
cleanly having done nothing. Press Escape when the item is still disabled after the menu is
open.

## No test grants, and take back what a task needed

Never send the user to add a program to Full Disk Access, Accessibility or any privacy pane
to test something. Test from a program that already holds the grant (the terminal), or on a
copy of the data. A grant a task really needs goes to one program with a stable identity: signed
with the local certificate under its own bundle id (`clo-tmux-host` is one), never a
version-named binary (`~/.local/share/claude/versions/<n>`, which is Claude Code itself), an
`applet`, or `sqlite3`, which leave a dead row on every update or rebuild.

A program is also listed, switched off, when it is denied a read of protected data (Safari,
Messages, Mail, the privacy database). Run such a read under the granted host (`clo-tmux-host`
for launchd jobs, the terminal otherwise), never from a bare `sqlite3`, `node` or `uv` in a
job with no grant.

When the task ends, remove what it added: `tccutil reset <Service> <bundle id>` for a signed
app; for a bare binary, name the row in the closing line so the user can delete it. A task
is not done while a grant it added for testing is still there.

Provenance: Nov 12 2026, the Merge Finder Windows applet. It was signed ad-hoc as `applet`,
and the user was sent to the Accessibility pane three times. The user: "claude we fucking
did this step already". See also the memory `adhoc-signing-voids-tcc-grants`.
Nov 14 2026, clo-remote: the Full Disk Access list held two `2.1` (Claude Code's own versioned
binary), three `applet` and one `sqlite3` row, all off or unused; how each got there is unproven. The user: "the agent is adding random entries on my computer for
its testing purposes ... why are they kept after we are done with it".
