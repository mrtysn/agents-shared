# High-detail models and working from a reference image

Read this whenever the user wants something **detailed / realistic / like this
picture**, or attaches a reference image, whatever the subject: a machine, a
vehicle, a prop, furniture, rocks and terrain, a building, a whole scene. The default failure mode of generated Blender scenes
is *primitives with one flat material and flat light*. It looks low-poly no
matter how many primitives there are. Detail comes from three things working
together:

1. **Geometry at three scales**: primary forms (silhouette), secondary (panels,
   openings, seams, structural parts) and tertiary (bolts, vents, hatches,
   cables, chips, small parts). Every element has real thickness and depth.
2. **Material variation**: no surface is one flat colour. Per-part tone and
   roughness, grime, edge wear, fine bump.
3. **Light that reveals relief**: grazing key, rim light, practical lights and
   atmosphere. Flat front light hides all detail.

`scripts/detail_kit.py` implements the reusable parts. This file is the
workflow and the rules behind it.

## Contents
1. Workflow from a reference image (any subject)
2. Rules that separate detail from primitives
3. Techniques by subject
4. detail_kit: general tools
5. Example: hard-surface prop
6. Example: architecture (FacadeKit)
7. Writing your own detail parts
8. Calibration tables
9. Performance
10. Mistakes we made (so you don't)

---

## 1. Workflow from a reference image (any subject)

**Step 0 — IP check.** If the reference shows a recognisable design from a
film, game, show or brand (a specific building, vehicle, character, logo), do
not replicate it. Tell the user once and build an **original** design in the
same style and mood: same genre, materials, lighting and camera feel, but your
own forms and details, and invented text. A generic style (rusty industrial
machine, brutalist tower, rainy neon street, medieval chest) is fine to match.

**Step 1 — Write a breakdown before any code.** Fill this in from the image (in
your reply or as a comment at the top of the script):

| Aspect | What to extract |
|---|---|
| Silhouette & massing | the few main volumes, how they connect, proportions |
| Scale | metres from known things: person 1.75 m, door 2.1 m, chair seat 0.45 m, car 4.5 m, floor 3–4 m, bolt head 1–3 cm |
| Module / rhythm | the repeating unit: panel size, rib spacing, plank width, bay width |
| Primary details | what you'd still recognise as a silhouette at 100 px |
| Secondary details | panels and seams, openings, ribs, frames, plates, structural members |
| Tertiary details | bolts, vents, hatches, cables, labels, chips, cracks, small lights |
| Materials | base material per part + wear (rust, chipped paint, grime, dust, wetness) |
| Light | key direction and colour, practical lights, colour temperatures |
| Atmosphere | fog/haze, rain, dust, glow |
| Camera | height, lens (wide = strong perspective), angle |

**Step 2 — Budget detail by what the final image can show.** Detail smaller than
~2 px in the final render is invisible: skip it. Pixel size of a part ≈
`part_size / visible_width_at_that_distance × image_width`. The hero gets full
geometric detail; background gets cheap shader detail and fog.

**Step 3 — Block out primary forms only, then render.** Simple shapes at real
scale, clay material, neutral light, camera matching the reference. Compare
proportions with the reference *before* adding detail; fixing massing later
means rebuilding everything.

**Step 4 — Secondary detail as real geometry.** Pick techniques from §3 for the
subject (panel lines, openings with frames, ribs, planks, displacement). Every
element has depth; every opening has something behind it.

**Step 5 — Tertiary detail, structured.** Small parts follow the module and
cluster where they make functional sense: bolts along seams and flanges, vents
near engines and roofs, cables between things that need power, chips on edges
that get hit. Pure random scatter reads as noise.

**Step 6 — Materials.** Recipes from detail_kit (`worn_paint`, `panel_metal`,
`concrete`, `wood`, `rock_material`, `glass`, …) or the same ingredients:
per-part variation, grime, edge wear, bump. With image textures, follow
materials.md (colour spaces).

**Step 7 — Lighting.** Grazing key along the main surfaces, rim from behind,
practical emissives at calibrated strengths (§8), then
`lighting_presets.balance_exposure()`. Dark materials need more light than you
think.

**Step 8 — Atmosphere and camera.** Mist-pass fog in the compositor for depth,
bloom on emissives, background in the haze. Match the reference camera.

**Step 9 — Verify and iterate.** Render a low-res preview of the **hero shot**
and a **close-up detail shot** (35–50 mm, close to the surface), and put the hero
shot next to the reference. Write down the three biggest differences
(proportions, value range, missing detail scale, materials, colour), fix them,
re-render. Stop when the remaining differences are taste, not structure. Show
previews early; the final render is the last step.

---

## 2. Rules that separate detail from primitives

- **Openings are recesses, not painted shapes.** A window, port, vent or screen
  has a frame, depth and something behind it (a room, a fan, a grille, a glow).
  Never a flat emissive rectangle on a surface.
- **Seams are geometry.** Panels are separated by real grooves or gaps
  (`panel_lines`, or parts that stop short of each other over a darker core).
- **Vary sizes inside the rhythm.** Identical parts on a perfect grid read as
  tiles or bricks. Keep the module but merge and split cells.
- **Bevel hard edges, but narrower than the detail around them.** A bevel wider
  than a seam turns panels into rounded blocks.
- **Per-part variation.** Merge parts into one mesh per material and use Geometry
  > Random Per Island for tone/roughness.
- **Wear where it happens.** Chips on convex edges, grime streaking down from
  ledges, dust in cavities, rust near water and joints.
- **Structure over noise.** Randomise within the structure, never instead of it.
- **Everything scales with the module.** Pipe radii, bolt sizes, bevels, light
  sizes and offsets derive from the module, never fixed numbers.
- **Light the relief.** Grazing light shows depth; front light flattens it.
- **Background is cheap.** Simple masses + shader detail + fog; detail there only
  competes with the hero.

---

## 3. Techniques by subject

| Subject | Primary | Secondary | Tertiary | Materials |
|---|---|---|---|---|
| Hard-surface machines, vehicles, sci-fi props, robots | boxes/cylinders, bevelled; booleans for big cut-outs | `panel_lines`, hatches, vents as recesses, ribs, plates | `greeble`, bolts (`MeshBuilder.dot`/`cyl`), pipes, `cable` | `worn_paint`, `panel_metal`, rubber, glass |
| Buildings, facades, interiors | prisms per storey, setbacks | `FacadeKit` cells: panels with seams, recessed windows with rooms, slabs | vents, pipes, lights, signs, AC units | `panel_metal`, `concrete`, `glass`, `interior` |
| Rocks, cliffs, terrain | displaced meshes (`rock`), grids with displace | layered displacement (big lumps + small chips), strata | `scatter_instances` of pebbles/debris, moss decals | `rock_material`, dirt, wet variants |
| Furniture & wooden props | boxes and planks at real sizes | plank seams, joints, mouldings, handles | nails/screws, chips, scratches | `wood`, metal fittings |
| Organic / natural (plants, trees) | curves with bevel, skin modifier, subdivision | branching, leaves as instanced planes | `scatter_instances` | leaf/bark materials with variation |
| Characters | out of scope for procedural scripting: block out with subdivision + skin modifier, or import a user-supplied model and detail its materials and lighting | | | |

General modelling tools for secondary detail on any mesh: `bmesh.ops.inset_region`
/ `inset_individual` (panels, frames), `extrude_face_region` (ribs, lips),
`bevel` (chamfers), Solidify (thickness), Array (repetition), Screw/`spin`
(lathe parts), Subdivision + creases (smooth hard-surface), Displace with noise
textures (organic surfaces).

---

## 4. detail_kit: general tools

| Tool | Use |
|---|---|
| `MeshBuilder(name, material, bevel)` | `.box()`, `.cyl()`, `.dot()`, `.prism()` many parts into one mesh; `.finish()` → object |
| `subdivide(obj, cuts)` | grid-subdivide so later tools have enough faces |
| `panel_lines(obj, panel_size, seam, depth, raised, seed)` | real V-groove panel seams with varied panel sizes on any mesh; sets flat shading |
| `greeble(target, builder, count, size, height, facing, seed)` | small boxes/cylinders/stacks on a surface, aligned to normals |
| `scatter_instances(target, source, count, scale, facing, seed)` | linked duplicates over a surface (pebbles, bolts, debris, plants) |
| `rock(name, radius, seed)` | displaced, applied rock mesh (use as scatter source) |
| `cable(p0, p1, sag, radius)` | hanging cable, hose or wire |
| `apply_modifiers(obj)` | bake modifiers before sharing a mesh between instances |
| materials | `worn_paint`, `panel_metal`, `concrete`, `wood`, `rock_material`, `glass`, `wet_asphalt`, `emissive`, `interior`, `simple`, `city_windows` |
| architecture | `Face`, `rect`, `octagon`, `inset`, `FacadeKit`, `facade_segment`, `mech_floor` |

---

## 5. Example: hard-surface prop

An industrial unit: subdivided hull with varied panel seams and chipped paint,
kitbash parts on top and front, pipes with flanges, pebbles on the floor and a
cable. Builds in well under a second.

```python
import sys, math
sys.path.insert(0, "/path/to/skill/blender/scripts")
import bpy, bmesh
import detail_kit as dk

me = bpy.data.meshes.new("Hull")
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.scale(bm, vec=(2.4, 1.4, 1.1), verts=bm.verts)
bm.to_mesh(me)
bm.free()
hull = bpy.data.objects.new("Hull", me)
bpy.context.scene.collection.objects.link(hull)
hull.location.z = 0.75

dk.subdivide(hull, cuts=10)                          # faces smaller than the panels
dk.panel_lines(hull, panel_size=0.35, seam=0.012, depth=0.008, seed=2)
hull.data.materials.append(dk.worn_paint(wear=0.6))
bev = hull.modifiers.new("Bevel", "BEVEL")           # corners only, narrower than the seams
bev.width, bev.segments = 0.008, 2
bev.limit_method, bev.angle_limit = "ANGLE", math.radians(80)

parts = dk.MeshBuilder("Greebles", dk.panel_metal("GreebleMetal", tone=(0.05, 0.12)), bevel=0.004)
dk.greeble(hull, parts, count=90, facing=((0, 0, 1), 0.7), seed=4)            # top
dk.greeble(hull, parts, count=60, size=(0.03, 0.15), height=(0.005, 0.05),
           facing=((0, -1, 0), 0.7), seed=5)                                   # front
pipes = dk.MeshBuilder("Pipes", dk.simple("Chrome", (0.8, 0.8, 0.82), rough=0.2, metal=1.0))
for k, z in enumerate((0.45, 0.6, 1.0)):
    pipes.cyl((-1.25, -0.75, z), (1.25, -0.75, z), 0.03 + 0.01 * k, segments=16)
    for x in (-1.0, 0.0, 1.0):                                                 # flanges
        pipes.cyl((x, -0.7, z), (x, -0.76, z), 0.05 + 0.01 * k, segments=16)
parts.finish()
pipes.finish()

gme = bpy.data.meshes.new("Floor")
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=20, y_segments=20, size=6)
bm.to_mesh(gme)
bm.free()
floor = bpy.data.objects.new("Floor", gme)
bpy.context.scene.collection.objects.link(floor)
floor.data.materials.append(dk.concrete("FloorConcrete", tone=(0.18, 0.24)))
pebble = dk.rock("Pebble", radius=0.12, seed=1)
pebble.location = (0, 0, -50)                         # template, out of view
dk.scatter_instances(floor, pebble, count=40, scale=(0.5, 1.6), seed=7, offset=0.02)
dk.cable((1.25, 0.3, 1.2), (2.35, 1.6, 1.85), sag=0.25, radius=0.02)
```

Light it with `lighting_presets.apply_preset("studio")` and frame it with
`boilerplate.add_framing_camera()`.

---

## 6. Example: architecture (FacadeKit)

Facades are a special case of the same rules: cells on a module, real depth,
something behind every opening. `FacadeKit` builds panels with seams down to a
dark core, recessed windows (frame, mullion, glass, sill, blinds, a lit or dark
room behind), vent banks and fins with lights.

```python
import sys
sys.path.insert(0, "/path/to/skill/blender/scripts")
import detail_kit as dk

kit = dk.FacadeKit(seed=3)                              # builders + default materials
dk.facade_segment(kit, dk.octagon(12, 3), 0, 16)        # storeys: core, cells, slab strip
dk.mech_floor(kit, dk.octagon(10, 2.5), 16, 21)         # recessed plant floor, pipes
dk.facade_segment(kit, dk.rect(10, 8), 21, 37, window_ratio=0.5)
objects = kit.finish()                                  # one object per material
print(len(objects), "objects,", sum(len(o.data.polygons) for o in objects), "faces")
```

- Footprints are CCW 2D polygons: `rect(half_w, half_d)`, `octagon(half_w,
  chamfer)` or your own; `inset(polygon, metres)` shrinks one.
- `panelize(face, col_w, row_h, window_ratio, strip_prob, vent_ratio,
  fins_every)` sets the facade rhythm.
- Openings are built **from parts around the opening** (frame pieces, sill,
  glass, room) rather than by cutting a boolean hole per window: hundreds of
  booleans are slow and fragile. The same applies to ports, vents and screens
  on any object.
- Restyle with `FacadeKit(materials={"panels": dk.concrete()})`.
- Background buildings: `dk.city_windows()` on simple boxes, in fog.

---

## 7. Writing your own detail parts

When nothing in the kit fits what the reference shows, write a part on top of
`MeshBuilder` and a local frame. `Face` gives a frame on a vertical wall
(`at(s, t, d)` = along, up, out; `basis` orients boxes), `Face.from_frame()` on
any plane; for curved surfaces use per-polygon frames as `greeble` does.

```python
import detail_kit as dk

kit = dk.FacadeKit(seed=5)
wall = dk.Face((-6, -4), (6, -4), 0, 9)          # 12 m wall facing -Y, 9 m high

def balcony(kit, f, s, t, w=3.0, depth=1.4):
    """Slab + front edge light + railing posts and top rail, at (s, t) on wall f."""
    B = f.basis
    kit.panels.box(f.at(s, t, depth / 2), (w, depth, 0.18), B)
    kit.strip.box(f.at(s, t - 0.1, depth + 0.01), (w * 0.9, 0.02, 0.03), B)
    for k in range(int(w / 0.25) + 1):
        x = s - w / 2 + k * 0.25
        kit.frames.cyl(f.at(x, t + 0.09, depth - 0.05), f.at(x, t + 1.05, depth - 0.05), 0.015, 6)
    kit.frames.cyl(f.at(s - w / 2, t + 1.05, depth - 0.05),
                   f.at(s + w / 2, t + 1.05, depth - 0.05), 0.03, 8)

kit.panelize(wall, col_w=3.0, row_h=3.0, window_ratio=0.6)
for s in (1.5, 7.5):
    balcony(kit, wall, s, 3.0)
kit.finish()
```

Checklist for a new part: real thickness, sizes in metres from the module, a
bevel-friendly builder, at least one smaller sub-detail (rail, bolt, light,
label), and randomness only where it would vary in reality.

---

## 8. Calibration tables

All values tested in Cycles with AgX at exposure 0 (Blender 5.x).

**Emission strengths**

| Element | Size | Strength |
|---|---|---|
| Indicator / navigation light dots | r 5–7 cm | 50–80 |
| Beacons | r 15 cm | 60–80 (red) |
| Light strips | ~5 cm section | 10–20 |
| Neon sign / tube | text or 8 cm tube | 20–30 |
| Screens, billboards | large panel | 4–8 |
| Lit room behind a window | full opening | 2.5–3.5 warm, 2–3 cool, 0.5 dim |
| Background city windows (shader) | 1.2 × 2.6 m cells | 1–1.5, lit fraction ~10 % |

**Sizes of common detail**

| Element | Typical |
|---|---|
| Panel seam (machines / buildings) | 5–15 mm / 5–8 cm |
| Panel size | 0.2–0.6 m on machines, 1.2–3 m on buildings |
| Bolt / rivet head | 1–3 cm diameter |
| Bevel | 2–5 mm on props, 2–3 cm on building cladding, always < seam |
| Pipes on a machine / plant floor | 2–6 cm / 3–8 % of floor height |
| Cable / hose | 0.5–3 cm radius, sag 5–25 % of span |
| Window | 1.2–1.6 × 1.6–2.0 m, frame 5–10 cm |
| Railing | 1.05 m high, posts every 0.12–0.25 m |
| Floor height | 3–4 m |

**Material knobs**

| Recipe | Knob | Guide |
|---|---|---|
| `worn_paint` | `wear` | 0.2 light chips, 0.6 used, 1.0 heavily worn; needs a dense mesh (Pointiness) |
| `panel_metal` | `tone` | (0.018, 0.06) dark painted, (0.05, 0.12) mid grey |
| `concrete` | `tone` | (0.18, 0.24) dark floor, (0.25, 0.38) facade |

**Render budget (CPU, Cycles, measured)**

| Scene | Preview 640×360, 12–16 spp | Final 1280×720, 32–64 spp |
|---|---|---|
| ~110k faces, 70 objects, glass, fog | ~45 s incl. build | ~2.5 min at 32 spp |
| street with 700 instanced rain drops | ~20 s | ~4 min at 64 spp |
| hard-surface prop, 40 rocks | ~15 s | under 1 min |

---

## 9. Performance

- **Merge, don't multiply objects.** Thousands of objects slow every step;
  `MeshBuilder` puts all parts of one material into one mesh.
- **Build openings from parts, not one boolean each.** If you need a boolean,
  join all cutters into one object and do a single EXACT boolean.
- **Bevel segments 1–2** on merged meshes; more multiplies the face count.
- **Linked duplicates** (`scatter_instances`, or `bpy.data.objects.new(name,
  same_mesh)`) for repeated heavy parts; `apply_modifiers` first.
- **Fog via the mist pass**, not volumes, on CPU. Volumes only with a GPU.

---

## 10. Mistakes we made (so you don't)

| What happened | Fix |
|---|---|
| Windows were flat white emissive rectangles | Recesses with something behind them; interior strength 2–3.5; 30–60 % lit |
| Panels on a regular grid looked like bricks/tiles | Vary panel sizes inside the module (`panel_lines` does) |
| A 3 cm bevel turned 1 cm seams into rounded blocks | Bevel narrower than the seam, angle limit ~80° |
| Smooth shading made panelled surfaces look like pillows | Flat shading on panel-lined meshes |
| Edge wear covered the whole object (camouflage look) | Pointiness threshold well above 0.5; dense mesh; lower `wear` |
| Background towers near the camera stole the image | Push them into the fog, cheap shader detail |
| Hero object came out nearly black | Strong grazing light on dark materials; then `balance_exposure()` |
| Sky became a flat fog-coloured slab | Darker fog colour; fog factor ≤ 0.75 |
| Camera so close the base hid the subject | Step back; check silhouette in the blockout render |
| Pipes with fixed radii stuck out of a smaller floor | Scale every part with the module |
| Emitter pointed at the lens made a blown blob | Lower strength or turn it away |
