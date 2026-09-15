# Game harness — Godot 4

How each of the five parts is built in Godot. Paths are examples; keep the layout the project
already has.

## 1. State hook: a `DebugState` autoload

An autoload that serialises what matters and prints it as one JSON line on request.

```gdscript
# res://tests/debug_state.gd — registered as autoload "DebugState"
extends Node

func snapshot() -> Dictionary:
    return {
        "frame": Engine.get_process_frames(),
        "scene": get_tree().current_scene.scene_file_path,
        "mode": Game.mode,                       # whatever the game's own state machine exposes
        "player_pos": Game.player.global_position,
        "near": Game.nearest_body_name(),
        "ready": Game.streaming_ready(),         # true once streamed content is in place
        "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
        "primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
        "process_ms": Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0,
        "physics_ms": Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0,
        "nodes": Performance.get_monitor(Performance.OBJECT_NODE_COUNT),
        "queued_jobs": Game.queued_jobs(),       # background generation still pending
    }

func dump() -> void:
    print("STATE " + JSON.stringify(snapshot()))
```

Call `DebugState.dump()` on a debug key, at the end of a journey, and on `--quit-after`.
Tests grep stdout for the `STATE ` prefix and parse the rest. Add fields as the game grows;
never print prose here.

## 2. Named scenes: user command-line arguments

Everything after `--` reaches the game untouched. A small launcher autoload reads them and
jumps to the requested scene with the requested seed.

```gdscript
# in the same autoload, _ready()
var args := {}
for a in OS.get_cmdline_user_args():          # e.g. --scene=orbit --seed=42 --fixed
    var kv := a.trim_prefix("--").split("=")
    args[kv[0]] = kv[1] if kv.size() > 1 else "1"
if args.has("seed"):
    seed(int(args["seed"]))
if args.has("scene"):
    get_tree().call_deferred("change_scene_to_file", "res://tests/scenes/%s.tscn" % args["scene"])
```

```bash
godot --path . -- --scene=orbit --seed=42
```

One `.tscn` per situation under `tests/scenes/`. A scene sets position, mode and loadout, and
nothing else; the game's own systems take over from there.

## 3. Headless capture: Movie Maker mode

`--headless` uses a dummy renderer and produces no pixels. Capture needs a rendering display
server, so run windowed but off the working screen, and use Movie Maker mode, which advances
the engine on a fixed step and writes numbered frames.

```bash
godot --path . --position 4000,0 --resolution 1280x720 \
  --write-movie tests/capture/out/orbit.png --fixed-fps 60 --quit-after 30 \
  -- --scene=orbit --seed=42
```

`.png` as the movie extension writes a frame sequence; keep the last frame as the shot. The
fixed step is what makes the pixels repeatable, provided nothing in the game reads
`Time.get_ticks_msec()` or `Time.get_unix_time_from_system()` for animation. Search for those
and replace them with accumulated `delta`.

Each shot is its own process, so instances never leak state into one another.

Diff against the accepted baseline with any per-pixel tool; a Godot-only option is
`Image.load_png_from_buffer` on both files and comparing `get_data()` in a GUT test. Under
`window-focus` DENY on a shared machine, this is the run that needs asking first: batch every
shot into one launch script rather than one process per question.

## 4. Journey tests: drive the real actions

Use the test framework the project already has. GUT runs headless from the command line;
gdUnit4 ships a `runtest.sh`. Either way the journey script presses the game's own input
actions and records state each physics frame.

```gdscript
# res://tests/journeys/test_land_and_walk.gd (GUT)
extends GutTest

func test_land_exit_walk_reboard() -> void:
    var trace := []
    get_tree().change_scene_to_file("res://tests/scenes/coastal_approach.tscn")
    await wait_for_signal(Game.streaming_became_ready, 10.0)
    Input.action_press("descend")
    for i in 600:
        await get_tree().physics_frame
        trace.append(DebugState.snapshot())
        if Game.mode == "landed": break
    Input.action_release("descend")
    assert_eq(Game.mode, "landed")
    assert_true(Game.ground_collision_ready(), "collision under the ship was not ready")
    # no position jump larger than one frame of travel during the transition
    for i in range(1, trace.size()):
        assert_lt(trace[i].player_pos.distance_to(trace[i-1].player_pos), 5.0)
    FileAccess.open("user://journeys/land_and_walk.json", FileAccess.WRITE) \
        .store_string(JSON.stringify(trace))
```

```bash
godot --headless --path . -s addons/gut/gut_cmdln.gd -gdir=res://tests/journeys -gexit
```

Journeys run headless because they assert on state, not pixels. Keep one per interaction the
game promises: land, exit, walk, save, reload, board, take off, and whatever the genre adds.

## 5. Measured runs: frame intervals on a fixed scene

Movie Maker mode fixes the step, so it cannot measure timing. Timing comes from a normal
windowed run of a named scene that collects `delta` for N frames and prints percentiles.

```gdscript
# res://tests/profile.gd — attach to a scene or trigger via -- --profile=300
var _samples: PackedFloat32Array = []
func _process(delta: float) -> void:
    _samples.append(delta * 1000.0)
    if _samples.size() == 300:
        _samples.sort()
        var p := func(q: float): return _samples[int(q * (_samples.size() - 1))]
        print("PROFILE " + JSON.stringify({
            "p50_ms": p.call(0.5), "p95_ms": p.call(0.95), "p99_ms": p.call(0.99),
            "worst_ms": _samples[-1],
            "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
        }))
        get_tree().quit()
```

Run it on an exported build for real numbers; the editor and debug builds add overhead. State
which build and which machine every time the numbers are reported. Same scene, same
resolution, same quality settings before and after, or the comparison is void.

## Off-screen and focus

`--position` far off the working display and `--resolution` small keep the window out of the
way. On a machine under `window-focus` DENY, journeys and state dumps still run fully headless;
only capture and profiling need a window, and those are asked for once and batched.
