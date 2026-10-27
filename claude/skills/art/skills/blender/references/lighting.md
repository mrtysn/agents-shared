# Lighting and color management (Blender 5.x)

Good lighting is the difference between a flat, amateur render and a convincing
one. Three things break renders here: **light power that ignores scene scale**
(black or blown-out), **no light hierarchy** (everything equally bright, flat
look), and the **wrong view transform** (washed-out or crushed).

Fastest correct path: use a preset from `scripts/lighting_presets.py`. Every
preset measures the subject, places lights relative to it and scales their power
with distance², so the same call gives the same exposure for a 2 cm ring and a
20 m house (verified: mean luminance 0.425 at 2 cm and 1 m, 0.431 at 20 m).

## Contents
1. Quick start: presets
2. Light types, units and properties
3. Placing lights relative to the subject (scale-independent power)
4. Lighting principles: ratios, softness, direction, colour temperature
5. World: flat colour, physical sky, HDRI
6. Color management: view transform, looks, exposure
7. Automatic exposure check
8. Emissive materials as lights
9. Light linking and per-object visibility
10. Engine notes (EEVEE vs Cycles)
11. Troubleshooting

---

## 1. Quick start: presets

```python
import sys
sys.path.insert(0, "/path/to/skill/blender/scripts")   # or copy the file next to scene.py
import lighting_presets as lp

# ... build geometry first: presets measure it ...
lp.apply_preset("studio")       # removes existing lights, builds the rig + world + look
lp.balance_exposure()           # optional safety net, see §7
```

Floors and backdrops named `Ground`, `Backdrop` or `Floor` are ignored when
measuring (pass `exclude=(...)` for other names). All values below are
calibrated for **AgX at exposure 0** on mid-grey materials (albedo ~0.5).

| Preset | Use for | Rig | Target mean luminance |
|---|---|---|---|
| `studio` | products, characters, the default | soft key 5600 K-ish, fill at ~1/3, rim behind | ~0.42 |
| `high_key` | e-commerce, clean white, friendly | big soft key + fill + top, bright white world, ratio ~1.5:1 | ~0.62 |
| `low_key` | drama, luxury, horror, hero shots | one gridded side key, cool rim, near-black world | ~0.25 |
| `outdoor` | daylight exteriors, architecture | physical sky + sun lamp (crisp shadows) | ~0.45 |
| `golden_hour` | warm, cinematic exteriors | sun at 6°, 3000 K, dusty sky | ~0.35 |
| `overcast` | soft natural light, no harsh shadows | bright grey world + huge top panel | ~0.45 |
| `night_neon` | sci-fi, cyberpunk, night streets | magenta/cyan rims, dark blue ambient, moon fill | ~0.20 |

`outdoor` and `golden_hour` take `sun_azimuth=` (and `outdoor` also
`sun_elevation=`): `lp.apply_preset("outdoor", sun_azimuth=30, sun_elevation=60)`.

Pick by the words in the request: "product shot", "render of X" → `studio`;
"white background", "catalogue" → `high_key`; "dramatic", "moody", "dark" →
`low_key`; "outside", "daylight", "street", "house" → `outdoor`; "sunset",
"warm" → `golden_hour`; "soft", "cloudy", "natural" → `overcast`; "night",
"neon", "cyberpunk" → `night_neon`. Then add emissive props, HDRI or tweaks.

To build a custom rig, use the same helpers the presets use:
`lp.add_area(...)`, `lp.add_sun(...)`, `lp.set_world_color/sky/hdri(...)`,
`lp.set_view(...)` and `lp.subject_bounds()`.

---

## 2. Light types, units and properties

```python
import bpy, math
light = bpy.data.lights.new("Key", type="AREA")   # POINT, SUN, SPOT, AREA
light.energy = 500                 # W for point/spot/area; W/m^2 for sun
light.use_temperature = True       # Blender 5.x: physical colour temperature
light.temperature = 4500           # Kelvin (overrides light.color while enabled)
obj = bpy.data.objects.new("Key", light)
bpy.context.scene.collection.objects.link(obj)
obj.location = (4, -4, 5)
```

| Type | `energy` unit | Softness control | Notes |
|---|---|---|---|
| `POINT` | watts | `shadow_soft_size` (radius, m) | Bulbs, candles; radius 0 = razor shadows |
| `SPOT` | watts | `shadow_soft_size` | `spot_size` (cone, rad), `spot_blend` (edge) |
| `AREA` | watts | `size` / `size_y` | `shape` SQUARE/RECTANGLE/DISK/ELLIPSE; `spread` = beam angle (180° bare panel, 30–60° softbox with grid) |
| `SUN` | W/m², distance-independent | `angle` (0.53° = real sun) | Position is irrelevant, only rotation counts |

Watts are **not** perceptual brightness: what the subject receives falls off
with distance². A 1000 W area light 2 m away is ~25× brighter on the subject than
the same light 10 m away. That is why fixed wattages break as soon as the model's
scale changes (§3).

Other useful properties (all 5.x):
- `light.use_shadow = False`: light without shadows (cheap fill).
- `light.normalize = True` (default): area light power is independent of its size,
  so you can resize for softness without re-balancing.
- `obj.visible_glossy = False` on the light object: hide the panel's reflection
  in glossy surfaces. Area lights are not visible to the camera by default.
- `light.diffuse_factor`, `specular_factor`: tweak per-light contribution.

Point the light with `rotation_euler`, `lp.aim(obj, target)`, or a `TRACK_TO`
constraint (needs an empty target; see animation.md §4).

---

## 3. Placing lights relative to the subject

Measure first, then express positions in **subject radii** and power as
**irradiance × distance²**. This is what `lp.add_area` does:

```python
from mathutils import Vector
import lighting_presets as lp

center, radius, floor_z = lp.subject_bounds()      # evaluated bounds, modifiers included
# azimuth 0 = in front of the subject (−Y, camera side), 90 = right (+X), 180 = behind
key = lp.add_area("Key", azimuth=-40, elevation=35, irradiance=5.2,
                  center=center, radius=radius,
                  distance=3.0,      # in subject radii
                  size=1.5,          # in subject radii: bigger = softer
                  kelvin=5000)
# internally: d = distance * radius; light.energy = irradiance * d * d
```

Irradiance guide (AgX, exposure 0): 0.3–1 accent or dim fill, 2–3 fill,
**~5 normal key**, 8+ bright key for high-key work. If the subject is very dark
(black car) or very bright (white plastic), adjust exposure (§6–7) rather than
re-balancing every light.

---

## 4. Lighting principles

**Key:fill ratio** sets the mood. With equal distances it is simply the ratio of
irradiances:

| Ratio | Look | Example |
|---|---|---|
| 1.5:1 – 2:1 | flat, bright, friendly | high-key, catalogue |
| 3:1 | natural modelling, the default | `studio` (5.2 : 1.8) |
| 4:1 – 8:1 | dramatic, sculpted | moody portraits |
| no fill | chiaroscuro | `low_key` |

**Shadow softness** depends on the light's apparent size seen from the subject:
`size / distance`. Bigger or closer = softer. A sun with `angle` 0.53° gives crisp
midday shadows; 2–5° looks like hazy sun.

**Direction**:
- Key at 30–45° to the side and 30–45° up reads as natural and shows form.
- Pure front light (azimuth 0, low elevation) flattens; avoid as a key.
- Side light (azimuth ±80–90°) maximises texture and drama.
- Rim/back light (azimuth 140–180°, elevation 30–50°) outlines the silhouette and
  separates the subject from a dark background; make it 0.5–1× the key.
- Under-lighting (negative elevation) is "horror"; use only on purpose.

**Colour temperature** (Kelvin, `light.temperature`): 1800 candle, 2700 household
bulb, 3200 tungsten, 4500 warm-white LED, 5600 daylight/flash, 6500 overcast,
7500–9000 shade/moonlight look. Warm key + cool fill/rim (e.g. 4500 K key, 6500 K
fill) gives depth for free. Saturated `color` values are for stylised looks
(neon, sci-fi) only.

**Ground contact**: without a floor there are no contact shadows and objects look
pasted on. Add a ground plane (or `obj.is_shadow_catcher = True` in Cycles with a
transparent film when compositing over another image).

---

## 5. World: flat colour, physical sky, HDRI

The world lights the scene from every direction (ambient) and appears in
reflections. In Blender 5.x the world always has a node tree; do **not** set
`world.use_nodes` (deprecated, removed in 6.0).

### Flat colour
```python
lp.set_world_color((0.8, 0.85, 1.0), strength=0.02)   # faint cool ambient for studio
lp.set_world_color((1, 1, 1), strength=0.3)            # bright white surround (high-key)
```
Strength 0 = pure black world: only lamps light the scene, and shadows go fully
black. A little ambient (0.01–0.05 with a studio rig) is almost always better.

### Physical sky (pair with a sun lamp)
```python
lp.set_world_sky(sun_azimuth=-45, sun_elevation=45, strength=0.036)
lp.add_sun("Sun", azimuth=-45, elevation=45, strength=1.2, kelvin=5600)
```
- 5.x `sky_type` values: `MULTIPLE_SCATTERING` (default here, most accurate),
  `SINGLE_SCATTERING` (the old "Nishita"), `PREETHAM`, `HOSEK_WILKIE`.
- The physical sky is very bright: strength ~0.03–0.04 matches a 1.2 W/m² sun
  lamp at exposure 0; raise to ~0.1 for a low sun.
- Keep `sun_disc=False` when you also add a sun lamp, otherwise the sun is
  counted twice. The lamp gives cleaner, cheaper shadows than the sky's disc.
- Same azimuth/elevation for sky and lamp, or shadows contradict the sky.
- Increase `aerosol_density` (dust) for hazy, warmer sunsets.

### HDRI
```python
lp.set_world_hdri("/path/studio.exr", strength=1.0, rotation_deg=90)
# Light + reflections from the HDRI, but a flat grey background in the frame:
lp.set_world_hdri("/path/studio.exr", strength=1.0, camera_color=(0.18, 0.18, 0.2))
```
- `rotation_deg` spins the environment around Z (a Mapping node) to move the
  dominant light source / window highlight.
- `camera_color` uses a Light Path "Is Camera Ray" mix: camera rays see the flat
  colour, everything else sees the HDRI. Use `film_transparent = True` instead
  when you need alpha.
- HDRIs come in different absolute brightness; check with §7 and adjust `strength`
  or exposure. Load `.exr`/`.hdr`, not 8-bit images.
- No HDRI file available? Use `set_world_sky` or `set_world_color`; never point
  at a path you didn't verify exists (missing images render pink).

---

## 6. Color management

```python
scene = bpy.context.scene
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.0     # stops; 2**exposure multiplies all light
```

View transforms in 5.x: `AgX` (default, photoreal, graceful highlight roll-off),
`Khronos PBR Neutral` (accurate product/material colours, good for e-commerce
when base colours must match), `Standard` (no tone mapping: flat 2D, UI, logos,
toon, exact colours), `Filmic` (legacy look), `Filmic Log`, `False Color`
(exposure debugging: shows over/under-exposed areas as colours).

AgX looks (exact strings): `None`, `AgX - Punchy`, `AgX - Greyscale`,
`AgX - Very High Contrast`, `AgX - High Contrast`,
`AgX - Medium High Contrast`, `AgX - Base Contrast`,
`AgX - Medium Low Contrast`, `AgX - Low Contrast`, `AgX - Very Low Contrast`.

`exposure` is a linear multiplier of the whole scene applied *before* the view
transform, so +1 EV is exactly the same as doubling every light and world
strength. Balance lights relative to each other first, then fix overall
brightness with exposure.

---

## 7. Automatic exposure check

A scene can be lit "correctly" and still come out too dark or blown out (dark
materials, a strong HDRI, a sun far too bright). `lp.balance_exposure()` renders
a tiny 160 px preview, measures mean luminance, and corrects exposure with a
secant step (usually 2–3 previews):

```python
lp.apply_preset("studio")
ev = lp.balance_exposure(target=0.42)   # ~0.6 high-key, ~0.25 low-key, ~0.2 night
print("exposure set to", ev)
```
Use it when the materials are far from mid-grey, after adding an HDRI, or
whenever the first preview looks too dark or bright. If it needs more than
±2 EV, something is structurally wrong (light power units, missing world,
camera inside an object); fix that instead of relying on exposure.

---

## 8. Emissive materials as lights

Any surface with emission contributes light in Cycles and EEVEE: screens, neon
tubes, lamps, lava, or a big soft panel that also shows up in reflections.

```python
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Emission Color"].default_value = (1.0, 0.1, 0.6, 1.0)
bsdf.inputs["Emission Strength"].default_value = 15.0
```
Emission strength is in W/m² of surface, so small emitters need large values
(a 1 cm neon tube ~20–50) to light anything nearby. In Cycles, many small
emitters cause noise; keep `scene.cycles.use_light_tree = True` (default) and add
a real lamp for the main contribution if the result is noisy.

---

## 9. Light linking and per-object visibility

Light linking (Cycles and EEVEE, 5.x) restricts which objects a light
illuminates or which objects cast its shadows. Useful for a rim that should hit
only the hero, or an eye light.

```python
receivers = bpy.data.collections.new("KeyReceivers")
receivers.objects.link(hero)              # collection need not be in the scene
key.light_linking.receiver_collection = receivers   # key lights only `hero`
# key.light_linking.blocker_collection = blockers   # only these cast its shadow
```

Per-object visibility (both engines) helps clean up reflections and shadows:
`obj.visible_camera`, `visible_glossy`, `visible_diffuse`, `visible_shadow`,
`visible_transmission`. Example: a fill card that lights but never appears in
reflections: `card.visible_glossy = False`.

---

## 10. Engine notes

**EEVEE** (`BLENDER_EEVEE` in 5.x, not `_NEXT`)
- Needs a GPU. On a headless server without one, EEVEE runs in software and can
  be slower than Cycles on CPU (we measured 36–61 s vs ~10 s for the same
  frame). Prefer Cycles with low samples + denoising there.
- `scene.eevee.use_raytracing = True` for proper reflections and AO-like GI.
- Shadow softness comes from light size like in Cycles; increase
  `light.shadow_maximum_resolution`/lower `shadow_filter_radius` only if shadows
  look blurry or blocky.
- Result is close to Cycles with these presets (studio mean luminance 0.38 vs
  0.43).

**Cycles**
- Fireflies with small bright lights or glossy surfaces: enable denoising, then
  `scene.cycles.sample_clamp_indirect = 10` if needed.
- Caustics are off by default for speed (`caustics_reflective/refractive`).
- `obj.is_shadow_catcher = True` + `render.film_transparent = True` for compositing
  objects over photos.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Render is black | No lights and world strength 0; light behind a wall; energy ~1 W | Add a preset; check `report_scene()` light count |
| Completely white / blown out | Sun `energy` in hundreds; area light with watts tuned for a much bigger scene | Sun ~1.2 W/m²; use `lp.add_area` (scales with distance²) |
| Fine at one scale, broken at another | Fixed wattages and positions | Use presets / `subject_bounds()`-relative placement |
| Flat, lifeless image | Single front light, or key = fill | Key at 30–45°, fill at 1/3, add a rim |
| Harsh, ugly shadows | Tiny light far away; point light radius 0 | Bigger `size` / closer, or `shadow_soft_size` |
| Floor brighter than the subject | Key floods the floor | Narrow the beam: `spread_deg=40–60`, move the key closer |
| Two shadows outdoors | Sky `sun_disc=True` plus a sun lamp | `sun_disc=False` |
| Shadows don't match sky | Sky and sun lamp have different angles | Same azimuth/elevation for both |
| Pink background | HDRI path missing | Verify path; or use sky/flat world |
| Light panel visible in chrome | Glossy rays see the area light | `light_obj.visible_glossy = False` |
| Noisy, speckled render (Cycles) | Small strong emitters, low samples | Denoise, more samples, clamp indirect |
| Colours look wrong vs swatch | AgX desaturates bright saturated colours | `Khronos PBR Neutral` or `Standard` for exact colours |
