---
description: Start a new Godot game on the oj engine through the project-lifecycle pipeline — an arcade entry by default, or its own project with a shape — with the manifest that gives it test, build, deploy and status. Use when the user asks for a new game, demo, prototype or playable experience.
argument-hint: [game name] [arcade | portrait-mobile | landscape-desktop | web-jam]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
---

# New Godot Game Skill

oj owns how a game starts: an arcade entry through its `/new-demo` skill (the documented
default: every game begins in the arcade playground), or its own project through
`ojctl.py create-game-project --shape ...` when it needs a renderer or orientation the arcade
cannot give. This skill asks which, lets oj make the game, then writes the project-lifecycle
manifest beside it so the one command works for it. It never copies oj's template.

## Required inputs (ask if missing)

Ask with AskUserQuestion, in one call, only for what the user will see or type:

1. **Game name** — what the game is called (`Gum Gum Pop`). The directory under oj's `games/`
   derives from it (`gum_gum_pop`), as does the tool slug (`gum-gum-pop`).
2. **Where it starts** — arcade (default; a registry entry in `games/arcade`, no manifest of
   its own yet) or its own project with a shape: `portrait-mobile` (android, ios),
   `landscape-desktop` (macos, android), `web-jam` (web, macos). Recommend arcade unless the
   user named a platform or orientation the arcade cannot serve.

## Steps

1. **Read oj's rules**: `/Users/mrtysn/dev/oj/CLAUDE.md` ("Where a game lives") before
   anything, and its `/new-demo` skill if the arcade path is chosen.
2. **Arcade path**: invoke `/new-demo` with the Skill tool (it scaffolds the demo and wires
   the registry and chooser). No manifest: an arcade entry is tested and shipped as part of
   arcade; say so, and that `graduate-game-out-of-arcade` moves it out when it earns its own
   project.
3. **Own-project path**: in a directory for the game's manifest (the slug under the current
   directory, or the current directory if empty):

       project-lifecycle init godot-game --name "<Game Name>" --game-shape <shape>

   It has oj create `games/<name>/` (`ojctl.py create-game-project`, which writes the shaped
   project, presets, the `[oj]` section, a consistency test, and runs the first headless
   import) and writes `project-lifecycle.json` and `CLAUDE.md` here. The oj checkout is the
   `oj_root` setting on this machine.
4. **Prove it**: `project-lifecycle test` must pass (it runs `./runtests.sh <game>` in oj:
   script compile, the game's tests, the crash-report check). Then `project-lifecycle status`
   shows the targets, each with its planned build number and whether it is exported.
5. **Commit in oj** the new game the way oj's CLAUDE.md says (its tests are the gate), and
   `/new-repo` for the manifest directory only if the user wants the manifest in a repo of
   its own; the usual place is beside the game, committed in oj.
6. **Report**: the game's directory in oj, the manifest's path, the targets, and the commands
   `project-lifecycle build` (development export of every target), `deploy` (release export,
   published where the game publishes), `run` (launch through oj's launcher).

## What the game already has, from oj

- Analytics (opt-in, PostHog, key from Doppler per game through
  `tools/write_posthog_local_cfg.zsh`), the derived build number in every export and event,
  and error reporting once the error reporter lands in core (see
  `docs/specs/error_reporting.md`).
- One version per game, typed by hand in `project.godot` when the game is published; never
  the build number.

## Pitfalls

- **Never `cp -R` oj's template** and never create a game outside oj's tools; the shape,
  package id and consistency test come from `create-game-project`.
- **Never launch the game to check it**; `runtests.sh` is the check, `--headless` the way.
- **A real export (`build`, `deploy`) installs to a phone, builds an Xcode project or
  publishes to itch**; do not run it to "see if it works". `status` shows the plan.
