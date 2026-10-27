# Blender 5.x API differences and footguns

This skill targets **Blender 5.x** (5.0 Nov 2025, 5.1, 5.2 LTS). Everything here
was verified on 5.0.1 and 5.2.3 LTS. Most LLM-written Blender code is trained on
3.x/4.x examples, so the table below is the first thing to check when a snippet
fails.

## Discover the API at runtime — do this instead of guessing

```python
import bpy
print("version:", bpy.app.version, bpy.app.version_string)

mat = bpy.data.materials.new("probe")
bsdf = mat.node_tree.nodes["Principled BSDF"]
print([s.name for s in bsdf.inputs])                       # socket names

scene = bpy.context.scene
print([i.identifier for i in scene.render.bl_rna.properties["engine"].enum_items])

print([x for x in dir(bpy.data) if not x.startswith("_")])  # datablock collections
print([x for x in dir(bpy.ops.mesh) if not x.startswith("_")])
bpy.data.materials.remove(mat)
```
For an enum, `obj.bl_rna.properties["prop"].enum_items` lists valid values. For
node inputs that are menus (e.g. compositor Glare "Type"), print
`node.inputs.keys()` and set `inputs["Type"].default_value = "Bloom"`.

## 4.x/3.x code that breaks on 5.x

| Old code | What happens on 5.x | Use instead |
|---|---|---|
| `scene.render.engine = "BLENDER_EEVEE_NEXT"` | `TypeError` (4.2–4.5 only) | `"BLENDER_EEVEE"` |
| `action.fcurves` | `AttributeError` (slotted actions since 4.4, legacy API removed in 5.0) | `bpy_extras.anim_utils.action_get_channelbag_for_slot(action, slot).fcurves` (animation.md §2) |
| `scene.node_tree` (compositor) | `AttributeError` | `scene.compositing_node_group = bpy.data.node_groups.new(..., "CompositorNodeTree")` (rendering.md §5) |
| `CompositorNodeComposite` | node type undefined | `NodeGroupOutput` + an `"Image"` output socket on the tree interface |
| `glare.glare_type = "FOG_GLOW"` | property gone | `glare.inputs["Type"].default_value = "Bloom"` (settings are input sockets now) |
| `mat.use_nodes = True`, `world.use_nodes`, `scene.use_nodes` | DeprecationWarning, removal planned for 6.0 | Omit: node trees always exist |
| `mat.blend_method = "BLEND"` | still exists but is the legacy EEVEE setting | `mat.surface_render_method = "BLENDED"` (or `"DITHERED"`) |
| `bpy.data.grease_pencils` holding annotation/GPv2 data | different type | `bpy.data.grease_pencils` is GPv3 (object type `GREASEPENCIL`); annotations are `bpy.data.annotations` |
| `scene["cycles"]` and other dict access to add-on props | no longer returns the settings | `scene.cycles` (attribute access) |
| `mesh.use_auto_smooth`, `auto_smooth_angle` | removed (4.1) | `bpy.ops.object.shade_smooth_by_angle(angle=...)` under override (destructive, simple), or `shade_auto_smooth(angle=...)` which adds a "Smooth by Angle" modifier (geometry.md §4) |
| `bpy.ops.export_mesh.stl`, `export_scene.obj` | removed | `bpy.ops.wm.stl_export`, `bpy.ops.wm.obj_export` |
| Python 3.11-only compiled modules | 5.1+ bundles Python 3.13 | Pure Python, or rebuild wheels |

Still valid on 5.x: Principled BSDF socket names from 4.0 (`Specular IOR Level`,
`Emission Color` + `Emission Strength`, `Subsurface Weight`, `Transmission Weight`,
`Coat Weight`, …), `bmesh`, `temp_override`, `keyframe_insert`, `bpy.ops.import_curve.svg`.

New in 5.x and worth using: `light.use_temperature` + `light.temperature`
(Kelvin), physical sky types `MULTIPLE_SCATTERING`/`SINGLE_SCATTERING`, light
linking (`obj.light_linking`), `bpy.data.orphans_purge(do_recursive=True)`.

## Running headless

```bash
blender -b --factory-startup --python-exit-code 1 -P scene.py -- --out /tmp/out.png
```
- `--python-exit-code 1`: without it Blender exits 0 even after a Python
  exception, so a failed script looks successful to an agent.
- `--factory-startup`: ignores user preferences and add-ons for reproducibility.
- Everything after `--` is for your script (`sys.argv`).
- `pip install bpy==5.2.3` (Python 3.13) gives Blender as a Python module, handy
  for tests. There, `import bpy` must come **before** `import bmesh` or
  `mathutils`.

## Context & reference footguns (all versions)

- **`context is incorrect`** — an operator ran headless without the needed
  context. Use `bpy.context.temp_override(...)` or, better, the data API.
- **`StructRNA of type ... has been removed`** — you held a Python reference to a
  datablock that was deleted or reallocated (after an operator, `to_mesh`, or a
  helper like `lighting_presets.apply_preset` that clears lights). Re-fetch from
  `bpy.data` by name; don't cache across operators.
- **`frame_current = n` doesn't update evaluated geometry** — use
  `scene.frame_set(n)`.
- **Reading evaluated (modified) geometry** — the base mesh ignores modifiers:
  ```python
  dg = bpy.context.evaluated_depsgraph_get()
  eval_obj = obj.evaluated_get(dg)
  eval_mesh = eval_obj.to_mesh()
  print(len(eval_mesh.vertices))
  eval_obj.to_mesh_clear()
  ```
- **Units/scale** — lights in watts assume real-world scale. Use the size-aware
  presets in `scripts/lighting_presets.py` instead of fixed wattages.
- **Selection/active object** — headless, `context.active_object` and selection
  are often `None`; always pass them in the override.
- **Edit-mode operators** (`mesh.*`, `uv.*`) fail with "context is incorrect"
  even inside `temp_override(active_object=obj)`: edit mode follows the view
  layer's active object. Set `view_layer.objects.active = obj`, select it, then
  `mode_set(mode="EDIT")` (`boilerplate.edit_mode(obj)` wraps this).
- **`view_layer.objects` is stale** right after linking/removing objects (it can
  contain `None`). Call `bpy.context.view_layer.update()` first, or iterate
  `scene.objects` instead.
- **`bpy.context.collection` can be `None`** (e.g. after deleting collections).
  Link new objects to `bpy.context.scene.collection`, which always exists.
- **EEVEE without a GPU** runs in software and can be slower than Cycles on CPU.
- **Saving the file** — `bpy.ops.wm.save_as_mainfile(filepath="/tmp/scene.blend")`;
  pack textures first (`bpy.ops.file.pack_all()`) for portability.

## Sanity checklist before declaring success

- [ ] Script ran with `--python-exit-code 1` and exited 0.
- [ ] Scene cleaned of the default cube/camera/light.
- [ ] Every object linked to a collection.
- [ ] Coincident verts merged; normals recalculated outward.
- [ ] Hard-surface edges bevelled (a small Bevel modifier); organic shapes smooth.
- [ ] Materials use correct color spaces; textures packed (no pink).
- [ ] Lighting from a preset or scaled to subject size; ground for contact shadows.
- [ ] Active camera frames the subject (`add_framing_camera`).
- [ ] View transform chosen deliberately (AgX vs Standard vs Khronos PBR Neutral).
- [ ] Frame range set (for animation).
- [ ] `verify_render()` reported no warnings, `render_views()` contact sheet
      checked for holes / flipped normals, and you **looked at** the image.
