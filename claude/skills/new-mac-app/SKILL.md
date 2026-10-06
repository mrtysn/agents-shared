---
description: Start a new macOS app on the project-lifecycle pipeline — a Swift/AppKit app on the shared MacAppBase package that already builds, self-tests and reports — then create its GitHub repo. Use when the user asks for a new Mac app, menu bar app, or a native window over a local tool.
argument-hint: [app name] [window|menu-bar] [--login-agent]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
---

# New Mac App Skill

Scaffold a macOS app with `project-lifecycle init mac-app`, prove it builds and passes its
self-test, then hand the directory to `/new-repo`. The templates live in project-lifecycle
(`project_lifecycle/init.py`); this skill only asks what a person must decide and runs the
command. Any agent can run the command without this skill.

## Required inputs (ask if missing)

Ask with AskUserQuestion, in one call, only for what the user will see or type:

1. **App name** — what Spotlight, the menu bar and the window title show (`Memory Guard`).
   The directory name, the tool slug (`memory-guard`), the bundle id (`local.memory-guard`)
   and the product name (`MemoryGuard`) all derive from it; say so in the question, and offer
   `--tool` only if the user wants a different slug.
2. **Shape** — `window` (a windowed app the user opens and quits; no heartbeat) or `menu-bar`
   (a menu bar item over a background job; heartbeat every five minutes). Recommend from what
   the user described.
3. **Keep it running from login?** — adds a login agent `install` manages. Recommend yes for a
   menu-bar app that watches something, no for a windowed tool.

Do not ask about the repo here; `/new-repo` asks its own questions.

## Steps

1. **Directory**: the current directory if it is empty or has no `project-lifecycle.json`,
   `Package.swift`, `mac/main.swift` or `CLAUDE.md`; otherwise `mkdir` the slug under the
   current directory and `cd` into it. `init` refuses to overwrite and names what is in the
   way: stop and report, never delete.
2. **Scaffold**:

       project-lifecycle init mac-app --name "<App Name>" --shape <window|menu-bar> [--login-agent] [--tool <slug>]

   Relay the files it wrote.
3. **Prove it**: `project-lifecycle test` must pass (it compiles the app against the shared
   package and runs the self-test). If the first compile fails with "cannot find 'Reporter' in
   scope", run it once more: SwiftPM replans on the second build. Any other failure is reported
   as is.
4. **Repo**: invoke `/new-repo` with the Skill tool, passing the slug and a one-line
   description built from the app name and shape. It handles identity, visibility, license
   and the push.
5. **Report**: the directory (absolute path), the slug, the three files to edit next
   (`mac/main.swift` for the app, `project-lifecycle.json` for icon and agent, `CLAUDE.md`),
   and the two commands: `project-lifecycle install`, `project-lifecycle status`.

## What the scaffold already does

- One instance (`SingleInstance.replaceOlder`), the AppKit delegate pattern the other apps use
  (`@MainActor` delegate, Swift 5 mode, macOS 13).
- A self-test behind `<SLUG>_SELFTEST=1` that `project-lifecycle test` runs; every control the
  app grows must get a check there (the repo's `CLAUDE.md` says so).
- `Reporter.start(tool:)` to the receiver; a menu-bar app also heartbeats. Events for failures
  are the app author's job: short stable names, nothing routine, nothing personal.
- Local-certificate signing (`Local Dev Signing` from `~/.config/project-lifecycle/config.json`),
  so permission grants survive rebuilds.

## Pitfalls

- **Never launch the app yourself to check it**; the self-test is the check. A windowed app
  takes focus, and `quiet-open` cannot run one that quits when its window is hidden.
- **The name is the user's**: never pick an app name, and never rename one to make the slug
  nicer; use `--tool` for that.
- **`init` on a non-empty directory**: it only refuses when one of its own files exists, so a
  directory with other sources is fine; a repo that already has `Package.swift` is a migration,
  not an init — see `docs/moving-a-mac-app-onto-project-lifecycle.md` in project-lifecycle.
