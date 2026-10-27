---
name: blender
description: >-
  Generate, edit, and render 3D and 2D scenes in Blender by writing Python (bpy)
  scripts that run headless. Use this skill WHENEVER the task involves Blender or
  a .blend file, or asks to create/model/join 3D objects, 2D shapes, curves, or
  text; build or assign materials and textures; UV unwrap; set up lighting or an
  HDRI environment; rig, keyframe, or animate; or render stills and animations —
  even if the user does not say the word "Blender" but clearly wants a 3D model,
  a rendered image, a procedural scene, or a 3D asset exported as glTF/FBX/OBJ/STL,
  and when they ask for a detailed or realistic model or a scene matching a
  reference image.
  Trigger this to get clean, watertight, correctly-joined geometry with proper
  normals, PBR materials, good lighting, and working animation instead of fragile
  bpy.ops-based code that breaks headless.
---

# Blender scripting (bpy)

Blender is driven from Python through the `bpy` module. The reliable way to produce
3D/2D assets, materials, lighting, and animation from a prompt is to **write a
`.py` script and run Blender headless**, then **render a preview to verify the
result before declaring success**. This skill encodes the non-obvious rules that
separate scripts that actually work from ones that silently produce garbage
(duplicate vertices, flipped normals, black renders, context errors).

## The one rule that matters most: prefer data-API over operators

`bpy.ops.*` operators (e.g. `bpy.ops.mesh.primitive_cube_add`) depend on **context**
— the active object, the current mode, the area under the mouse. Headless, that
context is often wrong or missing, so operators throw `RuntimeError: context is
incorrect` or quietly act on the wrong object. **Default to the low-level data API
and `bmesh` instead.** Operators are a last resort, and when you must use one,
wrap it in a context override.

```python
# FRAGILE — depends on context, may fail or hit the wrong object headless:
bpy.ops.mesh.primitive_cube_add(size=2)

# ROBUST — explicit data creation, no context needed:
import bpy
mesh = bpy.data.meshes.new("Cube")
obj  = bpy.data.objects.new("Cube", mesh)
bpy.context.scene.collection.objects.link(obj)
# ...then fill `mesh` with bmesh (see references/geometry.md)
```

When an operator is genuinely the best tool (booleans applied via modifier are
usually better, but e.g. some unwraps), override context explicitly:

```python
# Blender 4.x / 5.x context override:
with bpy.context.temp_override(active_object=obj, selected_objects=[obj],
                               object=obj):
    bpy.ops.object.shade_smooth()
```

Edit-mode operators (`bpy.ops.mesh.*`, `bpy.ops.uv.*`, editing armature bones)
are the exception: edit mode follows the *view layer's* active object, so an
override is not enough. Use `boilerplate.edit_mode(obj)`, or set
`view_layer.objects.active = obj` + `obj.select_set(True)` before
`mode_set(mode="EDIT")` (see `references/gotchas.md`).

## Standard workflow

If the user wants something **detailed or realistic**, or attaches a
**reference image**, read `references/detailing.md` first: it adds a breakdown
of the reference, a detail budget, a blockout render, three scales of detail
and a compare-and-iterate loop on top of the steps below, for any subject
(machines, vehicles, props, rocks, buildings). `scripts/detail_kit.py`
provides the parts: panel lines and greebles on any mesh, surface scattering,
rocks, cables, merged builders, weathered materials. Never answer "detailed"
with primitives and flat colours.

1. **Target Blender 5.x and check the version.** This skill is written and
   tested for 5.0–5.2. Most examples online (and in training data) are 3.x/4.x
   and break on 5.x: `BLENDER_EEVEE_NEXT`, `action.fcurves`, `scene.node_tree`,
   `use_nodes = True`, old Grease Pencil. **Read the table in
   `references/gotchas.md` before writing anything version-sensitive**, and when
   unsure print the available names at runtime instead of guessing.

   ```python
   import bpy
   assert bpy.app.version >= (5, 0, 0), bpy.app.version_string
   ```

2. **Start from a clean, deterministic scene.** Blender's default file ships a
   cube, a camera, and a light that will pollute your scene. Use the boilerplate
   in `scripts/boilerplate.py` (it wipes orphan data too) and always run Blender
   with `--factory-startup` so user preferences/add-ons can't change behaviour.
   Build at **real-world scale in metres** (a mug is ~0.1 m, a door ~2 m).

3. **Build geometry** with `bmesh` for meshes, `bpy.data.curves` for 2D/curves.
   Follow `references/geometry.md`. Crucially: **join correctly** — merge
   coincident vertices, recalculate normals outward, and decide deliberately
   between *join* (one object), *boolean* (fused watertight solid), and *parent*
   (grouped but separate). Wrong choice here is the #1 cause of "it looks broken".
   Give hard-surface objects a small Bevel modifier (geometry.md §4): razor-sharp
   edges are the most common reason a model reads as cheap CG.

4. **Materials & UVs** per `references/materials.md`: node-based Principled BSDF,
   proper UV unwrap before image textures, correct color space (sRGB for base
   color, Non-Color for roughness/normal/metallic maps).

5. **Lighting & world** per `references/lighting.md`. Default to a preset from
   `scripts/lighting_presets.py` (`studio`, `high_key`, `low_key`, `outdoor`,
   `golden_hour`, `overcast`, `night_neon`) applied *after* the geometry exists:
   it measures the subject and scales light placement and power to it, so
   exposure stays correct at any model scale. Then `balance_exposure()` if the
   preview is too dark or bright. Never hardcode wattages for an unknown scale.

6. **Animation** per `references/animation.md`: keyframes via `keyframe_insert`,
   F-curve interpolation, drivers, constraints, and armatures — set the scene
   frame range explicitly.

7. **Frame, render and verify** per `references/rendering.md`. Use
   `add_framing_camera()` (fits the subject, never crops), add a ground plane
   for contact shadows, then `render_still()`, which runs `verify_render()` and
   prints warnings for black, blown-out, flat, empty or cropped output. **Then
   look at the image.** For models, also run `render_views()` (4-angle contact
   sheet) to catch holes, flipped normals and wrong proportions a single view
   hides. Iterate: fix what you see, re-render. A script that runs without
   error can still produce a useless image; inspecting it is part of the job.

## How to run

```bash
# Headless, reproducible, fails loudly:
blender -b --factory-startup --python-exit-code 1 -P scene.py -- --out /tmp/render.png
```
`--python-exit-code 1` is essential: without it Blender exits with code 0 even
when the script raised an exception, so a broken build looks successful.
Everything after `--` is passed to the script.

Inside the script, read args after `--`:

```python
import sys
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
```

If Blender isn't installed in the environment, `pip install bpy==5.2.3`
(needs Python 3.13; `bpy==5.0.*` needs 3.11) gives a working headless Blender as
a Python module: run the script with `python scene.py` (import `bpy` before
`bmesh`/`mathutils`). EEVEE there needs a GPU; use Cycles on CPU otherwise. If
that is impossible too, say so and hand over the script for the user to run.
Never fabricate a render you didn't produce.

## Verifying without a GUI

- Render one frame at low samples to a PNG and **open/inspect the image**.
- `report_scene()` prints object counts, vertex counts, bounds, materials,
  lights and camera. "0 lights" or "camera: NONE" explains a black or empty
  render before you even open the image.
- `verify_render(path)` checks the PNG numerically (mean luminance, clipped
  whites, flatness, and with a transparent film: subject touching the frame
  edge). Treat its warnings as failures.
- For meshes destined for export or 3D print, assert **manifold + consistent
  normals** (see `references/geometry.md`).
- Check the console for `RuntimeError`/`ReferenceError` — a freed datablock
  (`ReferenceError: StructRNA ... has been removed`) means you kept a Python
  reference across an operator that reallocated it; re-fetch from `bpy.data`.

## Common failure modes (symptom → cause)

| Symptom | Likely cause |
|---|---|
| Black render | No light, or light power far too low, or world set to pure black |
| Empty/transparent render | Object not linked to a collection, or camera aimed away, or object behind camera |
| Pink / magenta surfaces | Image texture path missing or not packed |
| Faceted where it should be smooth | Forgot `shade_smooth` / normals not recalculated |
| Object looks "inside out" | Normals flipped inward — recalc outside |
| Seams/cracks after joining | Coincident vertices not merged (remove doubles) |
| Boolean gives holes/artefacts | Non-manifold input, or overlapping coplanar faces |
| `context is incorrect` | Used an operator headless without a context override |
| `enum "BLENDER_EEVEE_NEXT" not found` | 4.x engine id; 5.x uses `BLENDER_EEVEE` |
| `'Action' object has no attribute 'fcurves'` | Slotted actions; use the channelbag helper (animation.md §2) |
| `'Scene' object has no attribute 'node_tree'` | 5.x compositor is `scene.compositing_node_group` (rendering.md §5) |
| Subject cut off at frame edge | Hand-placed camera; use `add_framing_camera()` |
| `StructRNA has been removed` | Held a stale reference after data was reallocated |
| Washed-out/overexposed render | Wrong view transform or exposure; light power too high |

## Reference files

Read the one(s) relevant to the task — don't load all of them by default:

- `references/geometry.md` — creating meshes with bmesh; **joining objects
  correctly** (join vs boolean vs parent), merging vertices, recalculating
  normals, manifold checks, modifiers, procedural generation, instancing.
- `references/materials.md` — node materials, Principled BSDF, PBR texture maps,
  color spaces, UV unwrapping, procedural textures, applying different materials
  to different faces.
- `references/lighting.md` — lighting presets and when to use each, light types &
  units, scale-independent placement, key:fill ratios, shadow softness, colour
  temperature, physical sky / HDRI, AgX looks & exposure, auto-exposure, light
  linking, EEVEE vs Cycles notes, troubleshooting table.
- `references/animation.md` — keyframes, F-curve interpolation & easing, drivers,
  constraints, armatures/rigging, shape keys, following a path, frame range.
- `references/rendering.md` — Cycles vs Eevee, samples/denoise, resolution,
  output formats, rendering stills vs animation, cameras, exporting glTF/FBX/etc.
- `references/objects_2d.md` — 2D work: bezier/NURBS curves, filled shapes, text
  objects, the Grease Pencil (v3), logos/SVG, and 2D-in-3D compositions.
- `references/detailing.md` — high-detail modelling of any subject and working
  from a reference image: breakdown table, detail budget, blockout → secondary
  → tertiary detail, rules, techniques per subject (hard-surface, buildings,
  rocks/terrain, wood props), worked examples, calibration tables, mistakes.
- `references/gotchas.md` — table of 4.x code that breaks on 5.x and its
  replacement, runtime API discovery, headless flags, footguns, final checklist.

- `scripts/boilerplate.py` — import it or copy it as the top of a new script:
  `clean_scene`, `mesh_from_bmesh`, `add_framing_camera`/`place_camera`,
  `add_ground`, `add_default_lighting`, `setup_render` (+ GPU detection),
  `render_still`, `render_views` (contact sheet), `report_scene`,
  `verify_render`. Start here for almost every task.
- `scripts/detail_kit.py` — general: `MeshBuilder` (thousands of parts merged
  per material), `subdivide`, `panel_lines` (seams on any mesh), `greeble`,
  `scatter_instances`, `rock`, `cable`, `apply_modifiers`; materials
  (`worn_paint`, `panel_metal`, `concrete`, `wood`, `rock_material`, `glass`,
  `wet_asphalt`, `emissive`, `interior`); architecture example: `Face`,
  footprints, `FacadeKit`, `facade_segment`, `mech_floor`, `city_windows`.
- `scripts/lighting_presets.py` — size-aware lighting presets, world helpers
  (flat colour, physical sky, HDRI), view settings and `balance_exposure()`.
  Import it (or copy it next to the scene script) for any task that renders.
