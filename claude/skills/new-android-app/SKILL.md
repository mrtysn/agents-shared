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
`adb-reconnect devices | device <name> status|connect|push|shell -- …|screenshot|ui|tap`. `shell`
needs "Let agents run shell commands" switched on for that device; if it is off, say so, or push the
APK to `/sdcard/Download` for the user to tap. The user works phone and watch in parallel: pin every
call with `-s <serial>`, disconnect by address. The one direct-adb exception is your own headless
emulator, always `-s emulator-5554`.

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
5. **Try it on the emulator before the phone.** AVD `Medium_Phone_API_36.0` exists. Headless, so no
   window takes focus (commands from the grandma-launcher session; not re-run here):

       ~/Library/Android/sdk/emulator/emulator -avd Medium_Phone_API_36.0 -no-window -no-audio \
         -no-snapshot -no-boot-anim -gpu swiftshader_indirect >/dev/null 2>&1 &
       until [ "$(adb -s emulator-5554 shell getprop sys.boot_completed | tr -d '\r')" = 1 ]; do sleep 5; done
       adb -s emulator-5554 install -r app/build/outputs/apk/debug/app-debug.apk
       adb -s emulator-5554 shell am start -n <package>/.MainActivity
       adb -s emulator-5554 exec-out screencap -p > <scratchpad>/home.png
       adb -s emulator-5554 shell uiautomator dump /sdcard/u.xml
       adb -s emulator-5554 logcat -d -t 200 | grep -E 'AndroidRuntime|FATAL|<package>'
       adb -s emulator-5554 emu kill

   Read the screenshot PNG: a launch that did not crash is not a layout check. `uiautomator dump`
   gives tap targets for `input tap`. A sleeping emulator needs `input keyevent KEYCODE_WAKEUP` and
   `wm dismiss-keyguard`. When done, `emu kill` and confirm nothing is left (`pgrep -fl qemu-system`).
6. **Install on the user's phone**, only the one they named, through ADB Reconnect (the flow used for
   grandma-launcher on the Xiaomi; not re-run here):

       adb-reconnect device "<name>" status
       adb-reconnect device "<name>" push app/build/outputs/apk/debug/app-debug.apk /sdcard/Download
       adb-reconnect device "<name>" shell -- 'cp /sdcard/Download/app-debug.apk /data/local/tmp/a.apk && pm install -r /data/local/tmp/a.apk'

   A script that installs itself (`./build.zsh --install "<device>"` in pad-bridge, lava-lamp,
   link-keeper) takes the serial from `adb-reconnect --serial "<name or hardware serial>" --wait 30`
   and then runs `adb -s "$serial" install -r`; copy that block from pad-bridge. It takes a named
   device and refuses without one: no default ("a default would put a build on the wrong one").
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
- `assembleRelease` only when a baseline profile matters (grandma-launcher); it is signed with the
  debug key for a sideloaded app. Otherwise install the debug build.
