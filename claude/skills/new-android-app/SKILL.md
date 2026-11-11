---
description: Start a new Android app the way the user's existing ones are built (Gradle + Kotlin + Compose, or the bare-SDK build.zsh for a tiny Java app), prove it builds, test it on the headless emulator, install it on the user's own phone through ADB Reconnect, then create its GitHub repo. Use when the user asks for a new Android app, APK, launcher, share target, tablet or phone client, or a native companion for a tool.
argument-hint: [app name] [gradle|bare-sdk]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
---

# New Android App Skill

There is no `project-lifecycle init` template for Android yet: copy the shapes below from the user's
existing apps. Evidence: grandma-launcher (Gradle, Kotlin, Compose), adb-reconnect/android (Gradle,
Kotlin, views), pad-bridge/android, link-keeper/android and lava-lamp (bare SDK, Java).

## Required inputs (ask if missing)

One AskUserQuestion call, only for what the user will see or type:

1. **App name** and **package id**. Default `dev.mrtysn.<name-without-dashes>` (grandma-launcher,
   adb-reconnect); lava-lamp uses `com.burnish.*`. Say which you assume. The package id can never
   change once installed, so put it in the question.
2. **Build shape**, recommended from what the app does:
   - `gradle`: Kotlin, Compose or views, libraries, more than a few files (default).
   - `bare-sdk`: a few Java files, no libraries, no Compose: a share target, a service, a toy.
3. **Which device to try it on**: read `adb-reconnect devices` and offer its names. Never default one.
4. **Icon**: the first grandma-launcher install had none and the user said "this app lacks an icon".
   Offer a glyph and colour; the scaffold gets an adaptive icon from the start.

Do not ask about the repo here; `/new-repo` does.

## Before touching adb

Read `~/dev/adb-reconnect/CLAUDE.md` first (a subdirectory CLAUDE.md does not load by itself; the
grandma-launcher session ran adb directly and only read it afterwards). Its rules: agents do not run
`adb` against a real device and never kill or restart the adb server; device work goes through
`adb-reconnect devices | device <name> status|connect|install|push|shell -- …|screenshot|ui|tap`.
`shell` needs "Let agents run shell commands" switched on for that device; if it is off, say so. The
shared headless emulator is the app's `Emulator` row and goes through the same door, with shell on by
default: there is no raw-adb exception for it any more.

## Steps

1. **Directory** `~/dev/<slug>` (or `android/` inside an existing project's repo). Never overwrite.
2. **Scaffold, gradle shape.** Copy the wrapper from a sibling, write the rest:

       cp ~/dev/adb-reconnect/android/gradlew ~/dev/adb-reconnect/android/gradlew.bat <app>/
       mkdir -p <app>/gradle/wrapper && cp ~/dev/adb-reconnect/android/gradle/wrapper/* <app>/gradle/wrapper/

   Then `settings.gradle.kts`, root `build.gradle.kts` and `gradle.properties` as grandma-launcher's
   (AGP 9.x has Kotlin built in: add only `org.jetbrains.kotlin.plugin.compose` for Compose, no
   `kotlin-android` plugin; `FAIL_ON_PROJECT_REPOS` with `google()` and `mavenCentral()`;
   `android.useAndroidX=true`). `app/build.gradle.kts`: `compileSdk` and `targetSdk` 36, `minSdk` 30
   unless a target device needs lower, `namespace` = `applicationId`, `versionCode 1`, Compose BOM
   `2025.10.00`, `activity-compose`, `junit` for tests. Sources in
   `app/src/main/kotlin/<package path>/`, tests in `app/src/test/kotlin/…`. Strings in
   `res/values/strings.xml`; add `values-tr` when family will read it (English and Turkish). Adaptive
   icon: `mipmap-anydpi/ic_launcher.xml`, `drawable/ic_launcher_foreground.xml`, a background colour.
   **Bare-SDK shape:** copy `~/dev/pad-bridge/android/build.zsh` (aapt2, javac, d8, zipalign,
   apksigner with `~/.android/debug.keystore`), `AndroidManifest.xml`, `res/`, `src/<package path>/`.
   Put pure logic where a desktop-JVM check can run it before packaging (lava-lamp's `tests/SimCheck.java`).
3. **Machine-specific files stay out of git**: `local.properties` (`sdk.dir=$ANDROID_HOME`), real
   config (apps, numbers, hosts, tokens) in a gitignored file beside a committed `*.example` (the build
   fails with a message naming the example when it is missing, as grandma-launcher's `config.json`),
   device names in `device.local` or the app's config dir. `.gitignore`: `.gradle/`, `build/`,
   `local.properties`, `*.apk`, `*.aab`, `.idea/`, `*.iml`, `.kotlin/`, `captures/`.
4. **Prove it.** Verified on this Mac with a scratch Compose app (7 s warm, cached Gradle 9.7.1):
   `./gradlew testDebugUnitTest assembleDebug`. No gradle or kotlinc is on PATH; the wrapper is the
   only entry, with `JAVA_HOME` (Java 17) and `ANDROID_HOME` set. APK:
   `app/build/outputs/apk/debug/app-debug.apk`. Bare-SDK: `./build.zsh` (tools present in
   build-tools 36.1.0; not re-run here).
5. **Try it on the emulator before the phone.** The machine has one shared headless emulator (AVD
   `Medium_Phone_API_36.0`, 12G /data), used by every session and owned by ADB Reconnect as its
   `Emulator` row. `connect` boots it only if it is not running, waits for the boot (about 30 s cold)
   and wakes it; `ensure-android-emulator --for "<why>"` does the same and prints `emulator-5554`. `--for`
   is shown to the owner with who started it; one an agent started stops itself after 30 idle minutes. Never boot a
   second one; `stop-emulator` waits for the owner's click, so do not ask for it. `connect`, `install`,
   `ui`, `screenshot` and `shell` were run on it on 2026-11-10; the `am start` and `logcat` lines were not:

       adb-reconnect device emulator connect --for "trying <app name> before the phone"
       adb-reconnect device emulator install "$PWD/app/build/outputs/apk/debug/app-debug.apk"
       adb-reconnect device emulator shell -- am start -n <package>/.MainActivity
       adb-reconnect device emulator screenshot          # prints the PNG's path
       adb-reconnect device emulator ui                  # one line per control with its centre
       adb-reconnect device emulator shell -- logcat -d -t 200 | grep -E 'AndroidRuntime|FATAL|<package>'

   Read the screenshot PNG: a launch that did not crash is not a layout check. `ui` gives tap targets
   for `adb-reconnect device emulator tap <x> <y>`. Leave the emulator running when done. Uninstall
   your own test app if it is large (`shell -- pm uninstall <package>`), since /data is shared.
6. **Install on the user's phone**, only the one they named, through ADB Reconnect (the flow used for
   grandma-launcher on the Xiaomi; not re-run here):

       adb-reconnect device "<name>" status
       adb-reconnect device "<name>" install "$PWD/app/build/outputs/apk/debug/app-debug.apk"

   `install` runs `install -r` (600 s by default, `--timeout` for more) and needs "Let agents tap,
   install and open settings", which is on unless the owner turned it off. A script that installs
   itself (`./build.zsh --install "<device>"`) calls the same `adb-reconnect device "<device>" install`.
   pad-bridge, lava-lamp and link-keeper still run raw `adb -s "$serial" install -r` after
   `adb-reconnect --serial`; do not copy that block. The script takes a named device and refuses
   without one: no default ("a default would put a build on the wrong one").
   Xiaomi/HyperOS needs "Install via USB" on and refuses adb while locked. Sideloaded apps are signed
   with the debug key so `install -r` updates in place; a different key needs an uninstall, which
   wipes app data: ask first. A special permission (`WRITE_SECURE_SETTINGS`) is one `pm grant` per
   phone, recorded in the manifest comment and the README.
7. **Repo**: write `CLAUDE.md` (device rules above, the exact test, build and install lines, what is
   gitignored, what was learned about the target device), commit atomically with a pathspec, then
   invoke `/new-repo` with the Skill tool. Shell helpers are `#!/bin/zsh`; no absolute home paths in
   committed files (`${0:A:h}`, `$HOME`, `$ANDROID_HOME`).
8. **Report**: absolute project path, package id, what was tried where (emulator, which phone), the
   rebuild and install commands, and what only a person can check (permission dialogs, default home app).

## Pitfalls from the sessions

- **Test on the user's own phone**, never the recipient's. They said "we will not test on her
  phone obviously" and then "just install it on my phone".
- **Wireless debugging drops constantly.** When a device is gone, say it in one line and stop. Do not
  judge from `adb mdns services` (stale or empty); use `adb-reconnect --serial`.
- **Do not use Gradle for what three Java files do**: the bare-SDK apps build in seconds. Do not
  hand-write wrappers: copy them.
- **Apps for a non-technical person**: mistaps must be harmless, so risky toggles and menus sit
  behind a deliberate action (the user's words on grandma-launcher).
- Cloud config such as `google-services.json` is gitignored and optional at build time, as in adb-reconnect.
- **A native terminal client** (clo-remote's `android/`, built 2026-11-05 and tried on the headless
  emulator): Termux's `terminal-view` and `terminal-emulator` come from JitPack
  (`com.github.termux.termux-app:*:v0.118.0`, filtered to that group in `settings.gradle.kts`; the
  libraries are Apache 2.0 per Termux's LICENSE.md). `TerminalView` and `TerminalSession` are `final`:
  watch the view with `addOnLayoutChangeListener`, never subclass. A session needs a local pty
  process, so a remote terminal runs `sh -c 'stty raw -echo; exec toybox nc 127.0.0.1 <port>'` and the
  app bridges that loopback port to its WebSocket. The view repaints only when
  `TerminalSessionClient.onTextChanged` calls `view.onScreenUpdated()`; without it the screen stays
  black with a lone cursor. Call `requestFocus()` after layout (`view.post {}`), or hardware and
  `input text` keys fall through to the next Compose button (Enter once pressed "back").
- **Emulator against a server on the Mac**: the emulator reaches the host's loopback at `10.0.2.2`;
  allow cleartext for that one host in `network_security_config.xml`. Never point a test at a real
  session of the user's: attaching a client resizes tmux for everyone, so run a second server on its
  own tmux socket and port. Preseed the app's settings with
  `adb-reconnect device emulator shell -- run-as <package> …` into `shared_prefs/`.
- `assembleRelease` only when a baseline profile matters (grandma-launcher); it is signed with the
  debug key for a sideloaded app. Otherwise install the debug build.
