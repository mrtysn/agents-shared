---
name: game-harness
description: >
  Make a game inspectable by an agent, then investigate it that way: a state hook tests can
  read, named scenes to jump to, draw and frame counters, headless capture that is identical
  run to run, and tests that drive the real controls through the main interactions. Checks a
  game repo for the five parts, adds the missing ones, and runs every problem as reproduce →
  inspect → trace → change → rerun the same check. Use before the first feature of a new game,
  when a bug can only be described in words, when a performance claim has no before/after, or
  when the user says test scene, state hook, headless capture, screenshot test, "let the agent
  play it", or "I can't tell you what's wrong, look at it yourself".
disable-model-invocation: true
---

# Game harness

An agent cannot play a game the way its author does. It can read state, load a known scene,
take a screenshot, count draw calls, and drive the controls through a scripted route. Give it
those five things and it investigates on its own; withhold them and every bug arrives as a
paragraph of prose the agent has to guess from. This skill installs the five things and fixes
the working loop that uses them. The author keeps judging how the game looks and feels; the
harness is what makes the agent's half of the work verifiable.

## When to use

- Use at the start of a game, before the first feature, so every later change lands on
  something measurable. Retrofitting is possible but costs more each month.
- Use when a bug report is words only ("the planet vanishes when I come in shallow") and
  needs a repeatable reproduction before anyone touches code.
- Use before any performance or rendering change, so it can be measured against the same
  scene before and after.
- Use when the author wants to review by playing and leave the tracing to the agent.

**When *not* to use:** for the profiler-driven fix itself, use `performance-optimization`;
this skill builds the repeatable scene that skill measures against. For a one-off launch and
screenshot with nothing kept in the repo, the global `run` skill is enough. For judging a
screen against other games, use `game-ui-refs-compare`.

## The five parts

Check for each in the repo. Add what is missing, smallest working version first.

| # | Part | What it must do | Missing when |
|:-:|------|-----------------|--------------|
| 1 | **State hook** | Expose the current game state as data a test can read: what the player is near, the mode, readiness of streamed content, the active camera. Plus counters: draw calls, triangles or primitives, frame time, queued and buffered work. | The only way to know the state is to look at the screen. |
| 2 | **Named scenes** | Jump straight to a defined starting point: a location, a mode, a loadout. One per situation that matters (orbit, descent, landing, boss room, empty inventory). | Reaching a bug means playing to it by hand. |
| 3 | **Headless capture** | Take a screenshot of a named scene from the command line with no window and no human, and get the same pixels every run. | Two captures of the same scene differ. |
| 4 | **Journey tests** | Drive the real controls through the main interactions (land, exit, walk, save, reload, board, take off) and record position and state along the way. | Only staged scenes are tested, never the transitions between them. |
| 5 | **Measured runs** | Collect N frame intervals on a fixed scene and report p50, p95 and p99 with the counters. | Performance is reported as "feels faster". |

Engine specifics, including how each part is built, are in `references/`:
`references/godot.md` for Godot, `references/browser.md` for three.js, Phaser, PixiJS and
other browser games. Read the one matching the detected engine; the router already
fingerprinted it.

## The working loop

Every problem, whether visual, behavioural or performance, runs the same way. Do not skip
step 1 to start reading code.

1. **Reproduce.** Name the scene that shows it. If none does, add one; that is part of the
   fix, not a detour. Load it and confirm the problem is there.
2. **Inspect.** Read the state hook and take a capture. Compare against the reference image or
   the counter values the author accepted earlier. For a visual defect, capture with the
   suspect effect on and off; the difference isolates the cause better than the broken frame.
3. **Trace.** Now read the code, starting from the state values that were wrong.
4. **Change.** One cause at a time.
5. **Rerun the same check.** The scene, the capture, the counters, on the same settings.
   Report the before and after numbers, and what they were measured on. A number from a
   software renderer or an editor build is relative, not a frame rate; say so.

Journey tests catch what a capture cannot: a collision surface not ready under a landed ship,
a position that jumps during a transition, a save that reloads into the wrong mode. Run them
after any change to the systems they cross.

## Capture rules that make numbers trustworthy

Both come from measurements that turned out to be wrong.

- **Fresh instance per shot.** Reusing one running instance across captures leaks particle
  age, decal buffers, exposure and streaming state forward. Two runs of the same shot then
  differ on most frames. Start each capture from a cold scene load.
- **Engine clock, never wall clock.** Anything animated from real time makes every capture
  depend on boot duration and machine speed. Drive animation, noise and spawning from the
  engine's simulation time, and give test mode a fixed step. A pixel-identical baseline is
  only possible once nothing reads the wall clock.
- **Median hides the stall.** A static-camera benchmark can report a smooth frame rate while
  play is unplayable because of shader compilation or streaming spikes. Report p95 and p99
  from a moving, playing run, and attribute the worst frames.
- **Fixed budget per frame for background work.** Generation on the main thread must yield
  after a few milliseconds and resume next frame, or the capture stalls with it.

## Where the harness lives

In the game's repository, beside the game. This skill is invoked there, not in a company or
marketing repo. Keep the pieces small and boring:

```text
tests/scenes/        one file per named scene
tests/journeys/      scripted control runs with recorded state
tests/capture/       baseline images and the diff gate
tools/               capture, profile and diff entry points
```

Scenes and journeys are the record of what "working" means for this game. When a bug is fixed,
the scene that showed it stays.

## Pitfalls

- **Building the game first, the harness later.** Every feature added before part 1 exists is
  a feature the agent cannot inspect. The cost is paid on every bug afterwards.
- **A state hook that prints prose.** Emit data: JSON, key-value pairs. Prose has to be parsed
  by eye.
- **Staged scenes as proof.** A landing scene that starts on the ground proves nothing about
  landing. Journeys test transitions; scenes only test states.
- **Reading a screenshot to diagnose a stall.** Frame timing and counters find stalls; pixels
  find visual defects. Use the right instrument.
- **Comparing against a description.** The reference for a capture is an accepted image or an
  accepted counter value, never a sentence about what it should look like.
- **Quietly changing the settings between before and after.** Same scene, same resolution,
  same quality preset, same renderer, or the comparison is void.

## References

- `references/godot.md` — state autoload, test scenes, Movie Maker capture, GUT or gdUnit4
  journeys, `Performance` monitors, headless and off-screen launch flags.
- `references/browser.md` — window state hook, scene query parameter, Playwright capture and
  journeys, `renderer.info` counters, frame-interval profiling, pixel diff gate.

## Related skills

- `performance-optimization` — profile, fix, re-measure; runs on the scenes this skill sets up.
- `physics-tuning` — fixed timestep and interpolation, which the engine-clock rule depends on.
- `game-ui-refs-compare` — critic for a captured screen against shipped games.
- `gauntlet-loop` (global) — builder and critic loop against a named bar; its critic needs
  this skill's captures to compare.
