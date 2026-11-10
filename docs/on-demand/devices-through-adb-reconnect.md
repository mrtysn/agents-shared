# Reach phones through ADB Reconnect, never raw adb

**The adb server is a singleton on this machine, owned by the ADB Reconnect app. Agents never run
`adb` against a real device.** Device work goes through the app's agent door:

    adb-reconnect devices
    adb-reconnect device <name> status | connect | ui | screenshot | notifications | tap | key | open-settings | push
    adb-reconnect device <name> shell -- <command>     # only once the owner allows shell for that device

Every adb call from any session goes through that one server. A raw `adb reconnect offline`,
`disconnect`, `connect` or `kill-server` drops or redirects connections the owner's mirrors and other
sessions depend on. A raw `adb install` skips the app's busy guard and activity log.

- **Installing an APK on a phone:** the door has no `install` verb yet
  (`~/dev/adb-reconnect/docs/emulator-support-plan.md`). Use `push` to `/sdcard/Download` and ask
  the owner to tap it, or `shell -- pm install …` where shell is allowed. Do not use raw adb.
- **A phone dropped off:** `adb-reconnect device <name> connect`, never `adb reconnect` or
  `adb connect`.
- **The one exception** is the shared headless emulator: `ensure-android-emulator` starts it if
  needed and prints `emulator-5554`, and `adb -s emulator-5554 …` is allowed. Never boot a second
  one, and never `emu kill` it.

Read `~/dev/adb-reconnect/CLAUDE.md` for the full rules.

## Provenance

2026-11-10, elifer: asked to install three APKs on the phone, a session ran raw `adb install` and,
when the phone dropped, `adb reconnect offline` against the shared server. It never read the
adb-reconnect CLAUDE.md, because the session was launched in another repo and no rule fired. The
owner: "adb is also like a singleton on this machine thats why".
