# Rendering and export

## Contents
1. Choosing an engine (Cycles vs Eevee)
2. Samples, denoising, resolution
3. Cameras
4. Output formats (stills & animation)
5. Transparent background & compositing basics
6. Exporting to glTF / FBX / OBJ / STL / USD

---

## 1. Engine: Cycles vs Eevee

- **Cycles** — physically-based path tracer. Best for realism: true reflections,
  refraction/glass, soft shadows, caustics, accurate GI. Slower. Set
  `scene.render.engine = "CYCLES"`. Use GPU if available:
  ```python
  prefs = bpy.context.preferences.addons["cycles"].preferences
  for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
      try:
          prefs.compute_device_type = backend
      except TypeError:
          continue                      # backend not compiled into this build
      prefs.get_devices()
      if any(d.type != "CPU" for d in prefs.devices):
          for d in prefs.devices:
              d.use = d.type != "CPU"
          scene.cycles.device = "GPU"
          break
  ```
  (`boilerplate.enable_gpu()` does exactly this and returns the backend.)
- **EEVEE** — real-time rasteriser. Fast, great for stylised looks, previews, and
  animation on a budget. In Blender 5.x the engine id is **`BLENDER_EEVEE`**
  (`BLENDER_EEVEE_NEXT` existed only in 4.2–4.5 and raises `TypeError` now):
  ```python
  scene.render.engine = "BLENDER_EEVEE"
  scene.eevee.use_raytracing = True     # proper reflections / GI
  ```
  EEVEE needs a GPU. Headless without one it renders in software and can be
  slower than Cycles on CPU. It approximates glass/GI; for hero glass/caustics
  use Cycles.

Rule of thumb: **Cycles** when the user says photoreal/product/realistic, and on
machines without a GPU; **EEVEE** for speed on a GPU, previews, motion graphics,
toon/flat styles.

---

## 2. Samples, denoising, resolution

```python
# Cycles
scene.cycles.samples = 128          # 32-64 preview, 128-512 final
scene.cycles.use_denoising = True   # OptiX/OpenImageDenoise cleans low samples
scene.cycles.use_adaptive_sampling = True

# EEVEE
scene.eevee.taa_render_samples = 64

# Resolution (both)
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
```
Denoising lets you use far fewer samples — always enable it for quick, clean
results.

---

## 3. Cameras

```python
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 50               # mm; 35 wide, 50 natural, 85 portrait/compressed
cam = bpy.data.objects.new("Camera", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = (7, -7, 5)
scene.camera = cam               # MUST set the active camera or render is empty
```
For framing, prefer `boilerplate.add_framing_camera()`: it computes the distance
from the subject's bounding sphere and the narrower field of view, so the subject
is never cropped at any aspect ratio (`place_camera(cam, azimuth, elevation)`
re-frames an existing camera). To aim manually, use `TRACK_TO` at an empty or
`cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()`.

Depth of field: `cam_data.dof.use_dof = True`, set `focus_object` and `aperture_fstop`
(lower = shallower). Orthographic: `cam_data.type = "ORTHO"`,
`cam_data.ortho_scale`.

---

## 4. Output formats

Still:
```python
scene.render.image_settings.file_format = "PNG"   # or "OPEN_EXR" (HDR), "JPEG"
scene.render.image_settings.color_depth = "16"    # PNG/EXR
scene.render.filepath = "/tmp/render.png"
bpy.ops.render.render(write_still=True)
```
Animation → prefer a PNG sequence (resumable), or FFMPEG for a video file. See
animation.md §8.

---

## 5. Transparent background & compositing

```python
scene.render.film_transparent = True        # alpha where no object
scene.render.image_settings.color_mode = "RGBA"
```
For post effects (glow, colour grade, vignette) use the compositor. In 5.x the
compositor is a **node group** assigned to the scene (`scene.node_tree` and the
Composite node are gone; `scene.use_nodes` is deprecated). The result goes to a Group
Output with an `"Image"` socket, and most node settings are **input sockets**:

```python
scene = bpy.context.scene
tree = bpy.data.node_groups.new("Compositor", "CompositorNodeTree")
tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
scene.compositing_node_group = tree

rl = tree.nodes.new("CompositorNodeRLayers")
glare = tree.nodes.new("CompositorNodeGlare")
glare.inputs["Type"].default_value = "Bloom"      # menu socket, not a property
glare.inputs["Threshold"].default_value = 1.0      # only pixels brighter than this glow
glare.inputs["Strength"].default_value = 0.8
glare.inputs["Size"].default_value = 0.6
out = tree.nodes.new("NodeGroupOutput")
tree.links.new(rl.outputs["Image"], glare.inputs["Image"])
tree.links.new(glare.outputs["Image"], out.inputs["Image"])
```
Bloom only affects pixels above `Threshold`, so it needs emissive surfaces or
bright highlights (emission strength well above 1). Print `node.inputs.keys()`
to discover a node's settings.

---

## 6. Exporting

Blender ships exporters; call them with a filepath. Prefer **glTF** for
web/real-time/interchange (materials + animation survive well), **STL** for 3D
printing (geometry only — run the manifold check in geometry.md first), **FBX**
for game engines, **OBJ** for simple static geometry, **USD** for pipelines.

```python
# glTF (recommended default for a 3D asset):
bpy.ops.export_scene.gltf(filepath="/tmp/asset.glb", export_format="GLB")

# STL for 3D printing (core exporter; export_mesh.stl no longer exists):
bpy.ops.wm.stl_export(filepath="/tmp/asset.stl")

# FBX / OBJ / USD / PLY:
bpy.ops.export_scene.fbx(filepath="/tmp/asset.fbx")
bpy.ops.wm.obj_export(filepath="/tmp/asset.obj")          # export_scene.obj was removed
bpy.ops.wm.usd_export(filepath="/tmp/asset.usdc")
bpy.ops.wm.ply_export(filepath="/tmp/asset.ply")
```
Before export: apply transforms (`object.transform_apply`) so scale/rotation bake
in, apply modifiers if the target format won't carry them, and pack or copy
textures. For glTF with animation, ensure actions exist and the frame range is set.
