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

Provenance: Nov 12 2026, the Merge Finder Windows applet. It was signed ad-hoc as `applet`,
and the user was sent to the Accessibility pane three times. The user: "claude we fucking
did this step already". See also the memory `adhoc-signing-voids-tcc-grants`.
