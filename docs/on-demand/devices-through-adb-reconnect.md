# Reach phones through ADB Reconnect, never raw adb

**The adb server is a singleton on this machine, owned by the ADB Reconnect app. Agents never run
`adb` against a real device.** Device work goes through the app's agent door:

    adb-reconnect devices
    adb-reconnect device <name> status | connect | ui | screenshot | notifications | tap | key | open-settings | push | install <apk>
    adb-reconnect device <name> shell -- <command>     # only once the owner allows shell for that device

Every adb call from any session goes through that one server. A raw `adb reconnect offline`,
`disconnect`, `connect` or `kill-server` drops or redirects connections the owner's mirrors and other
sessions depend on. A raw `adb install` skips the app's busy guard and activity log.

- **Installing an APK:** `adb-reconnect device <name> install /abs/path/app.apk` (`install -r`,
  600 s by default, `--timeout` for more). Never raw `adb install`.
- **A phone dropped off:** `adb-reconnect device <name> connect`, never `adb reconnect` or
  `adb connect`.
- **The shared headless emulator** is the app's `Emulator` row, with no raw-adb exception:
  `adb-reconnect device emulator connect --for "<why>"` boots it if needed (so does
  `ensure-android-emulator --for "<why>"`); the owner sees who started it and why, and it stops after 30 idle minutes. And
  every verb works on it, `shell` included. Never boot a second one; `stop-emulator` waits for the
  owner's click.

Read `~/dev/adb-reconnect/CLAUDE.md` for the full rules.

## Provenance

2026-11-10, elifer: asked to install three APKs on the phone, a session ran raw `adb install` and,
when the phone dropped, `adb reconnect offline` against the shared server. It never read the
adb-reconnect CLAUDE.md, because the session was launched in another repo and no rule fired. The
owner: "adb is also like a singleton on this machine thats why".
