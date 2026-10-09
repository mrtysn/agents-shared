---
description: Start a new Roblox game in the robloj framework through the project-lifecycle pipeline — robloj creates games/<slug>/ (Rojo project, source tree, one Lune test, asphalt and mantle config) and the manifest gives it test, build, deploy, status and run. Use when the user asks for a new Roblox game, experience, place or demo.
argument-hint: [game name]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
---

# New Roblox Game Skill

robloj owns how a game starts: `tools/robloj.py init --name <slug>` writes `games/<slug>/` with
the Rojo project, the source tree, `asphalt.toml`, `mantle.yml` and one Lune test. This skill
asks for the name, lets robloj make the game through `project-lifecycle init roblox-game`,
proves it with `project-lifecycle test`, and commits in robloj. It never copies a template.

## Required inputs (ask if missing)

Ask with AskUserQuestion only for what the user will see or type:

1. **Game name** — what the game is called (`Gum Gum Pop`). The directory under robloj's
   `games/` and the tool slug both derive from it (`gum-gum-pop`).

Do not ask for the universe or place id: they exist only once the experience is created on
Roblox, and `init` takes `--universe-id` and `--place-id` later, or they are added to the
manifest by hand. Do not ask about a repo: the game lives in robloj.

## Steps

1. **Read robloj's rules**: `$DEV_ROOT/robloj/CLAUDE.md` before anything. The checkout is the
   `robloj_root` setting on this machine (`~/.config/project-lifecycle/config.json`).
2. **Create it**, with `-C` on the game's directory in the checkout, which does not exist yet:

       project-lifecycle -C <robloj_root>/games/<slug> init roblox-game --name "<Game Name>" --json

   It runs `robloj.py init --name <slug> --json` in the checkout, which writes `games/<slug>/`
   with its manifest, then confirms that manifest (kind and game) and writes `CLAUDE.md` beside
   it; `created_in_robloj.written` in the output lists what robloj wrote. Run anywhere else,
   it writes the manifest into the current directory instead; the game still lives in robloj.
3. **Prove it**: `project-lifecycle -C <robloj_root>/games/<slug> test` must pass (it runs
   `robloj.py check --game <slug>`: Selene, StyLua, luau-lsp analyze, Lune tests). Then
   `status` shows whether the `.rbxl` is built and current, the pinned tool versions, and
   what Mantle deployed.
4. **Commit in robloj** the new game the way its CLAUDE.md says (its check is the gate), and
   push.
5. **Report**: the game's directory in robloj, the manifest's path, the test output, and the
   commands `project-lifecycle build` (`rojo build` to the `.rbxl`), `deploy` (build, then
   `mantle deploy`; refuses without `ROBLOX_API_KEY`, which comes from Doppler through
   `doppler run`), `run` (opens the built place in Studio with `open -g`).

## Pitfalls

- **Never `cp -R` another game** and never create a game outside robloj's CLI; the project
  file, the test and the configs come from `robloj.py init`.
- **Never open Studio to check the game**; `robloj.py check` is the check. Studio is the
  user's window: `run` opens it for them, never quietly, and only when they ask.
- **`deploy` publishes to Roblox**; do not run it to "see if it works". `status` shows the
  state, and `build` is the harmless half.
- **The key is never written anywhere**: not in the manifest, not in the repo, not in a
  report. The manifest carries only `game`, `universe_id` and `place_id`.
