# Spotlight runs inside "Siri AI" on macOS 27

**On macOS 27 there is no `Spotlight` process.** Spotlight, Cmd+Space and the Apps menu are drawn by
`/System/Applications/Siri AI.app`, the launchd job `com.apple.campo`; `com.apple.Spotlight` is
disabled while that feature is on. So `pgrep -x Spotlight` finds nothing even when search works, and
that result is not evidence of a fault.

- **Cmd+Space or the Apps key does nothing** (the process takes key focus and runs the typed query,
  but no panel is visible): `killall "Siri AI"`. launchd respawns it at once, and no window takes
  focus. Check with `pgrep -x "Siri AI"` and `ps -o etime -p <pid>`. The cause is not known yet:
  **capture the window state before restarting** (the owner's machine has a capture step for this),
  since a restart destroys the only evidence. Presses logged with `loginwindow` frontmost were made
  at the lock screen and say nothing about whether Spotlight works.
- Restarting the Dock does not fix it.
- **Never `launchctl disable` `com.apple.campo` or kill it in a loop.** That removes Spotlight and the
  Apps menu entirely; there is no fallback binary.

## Provenance

Nov 23 2026: Spotlight and the Apps menu stopped opening; the Dock restart did nothing, restarting
`Siri AI` (7 days old) fixed it. Nov 27 2026: a session ran `pgrep -lx Spotlight`, found nothing and
told the user "the Spotlight process isn't running"; the user then reported Cmd+Space failing again,
and restarting `Siri AI` (4 days old) was the fix once more.
