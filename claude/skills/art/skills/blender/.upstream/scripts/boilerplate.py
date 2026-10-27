"""
Blender 5.x headless boilerplate (tested on 5.0.1 and 5.2.3 LTS).
Copy this file next to your scene script and `from boilerplate import *`,
or paste the helpers you need.

Run:
    blender -b --factory-startup --python-exit-code 1 -P scene.py -- --out /tmp/out.png

`--python-exit-code 1` matters: without it Blender exits with code 0 even when
the script raised an exception, so a failed build looks like a success.

What it gives you:
- clean_scene(): deterministic start (default cube/camera/light and orphans gone).
- mesh_from_bmesh(): context-free mesh creation.
- edit_mode(obj): context manager for edit-mode operators (UV unwrap etc.).
- add_framing_camera(): 3/4 camera whose distance fits the subject's bounding
  sphere in the narrower field of view, so nothing is ever cropped.
- add_ground(), add_default_lighting(): ground contact + a size-aware lighting
  preset (uses lighting_presets.py when it sits next to this file).
- setup_render(), render_still(), render_views(): render and a multi-angle
  contact sheet for checking the model from all sides.
- report_scene(), verify_render(): catch black / blown-out / empty / cropped
  renders automatically, before you even look at the image.
"""

import contextlib
import math
import os
import sys
import tempfile

import bpy  # import bpy first: with the pip `bpy` module, bmesh/mathutils need it loaded
import bmesh
from mathutils import Vector

assert bpy.app.version >= (5, 0, 0), f"This skill targets Blender 5.x, got {bpy.app.version_string}"

GEOMETRY_TYPES = {"MESH", "CURVE", "FONT", "SURFACE", "META", "GREASEPENCIL"}
HELPER_NAMES = ("Ground", "Backdrop", "Floor")


# ---------------------------------------------------------------------- args
def get_args():
    """Arguments after `--` on the Blender command line."""
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg_value(flag, default=None):
    args = get_args()
    return args[args.index(flag) + 1] if flag in args else default


# --------------------------------------------------------------------- scene
def clean_scene():
    """Remove all objects and purge every orphaned datablock."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    bpy.data.orphans_purge(do_recursive=True)
    # removing the active collection leaves bpy.context.collection = None
    view_layer = bpy.context.view_layer
    view_layer.active_layer_collection = view_layer.layer_collection
    print("Scene cleaned:", len(bpy.data.objects), "objects remain")


def link(obj, collection=None):
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def new_object(name, data=None, collection=None):
    """Create and link an object. data=None makes an empty."""
    return link(bpy.data.objects.new(name, data), collection)


@contextlib.contextmanager
def edit_mode(obj, select_all=True):
    """Run edit-mode operators (UV unwrap, mesh.* ops) headless.

    temp_override(active_object=...) is NOT enough for edit-mode operators:
    edit mode follows the view layer's active object, so make it truly active
    and selected, enter edit mode, and always return to object mode.

        with edit_mode(obj):
            bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
    """
    view_layer = bpy.context.view_layer
    view_layer.update()  # view_layer.objects is stale (contains None) after link/remove
    for o in bpy.context.scene.objects:
        o.select_set(False)
    view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        if select_all:
            bpy.ops.mesh.select_all(action="SELECT")
        yield obj
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def mesh_from_bmesh(name, build, smooth=False):
    """build(bm) fills a fresh bmesh; returns a linked mesh object."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for poly in me.polygons:
            poly.use_smooth = True
    return new_object(name, me)


# ------------------------------------------------------------ bounds/camera
def scene_bounds(exclude=HELPER_NAMES):
    """World-space (min, max) over evaluated renderable geometry (modifiers included)."""
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for obj in bpy.context.scene.objects:
        if obj.name in exclude or obj.type not in GEOMETRY_TYPES or obj.hide_render:
            continue
        ev = obj.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    if not pts:
        return Vector((-1, -1, -1)), Vector((1, 1, 1))
    lo = Vector(tuple(min(p[i] for p in pts) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in pts) for i in range(3)))
    return lo, hi


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def place_camera(cam, azimuth_deg=35, elevation_deg=20, margin=1.15, exclude=HELPER_NAMES):
    """Move `cam` onto a view of the subject that fits it in frame.
    Azimuth 0 = front (-Y), 90 = right (+X). Elevation 0 = eye level."""
    scene = bpy.context.scene
    lo, hi = scene_bounds(exclude)
    center = (lo + hi) / 2
    radius = max((hi - lo).length / 2, 1e-4)
    data = cam.data
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    if data.type == "ORTHO":
        data.ortho_scale = 2 * radius * margin * max(rx, ry) / min(rx, ry)
        dist = radius * 3
    else:
        fov_wide = data.angle  # AUTO sensor fit: angle spans the larger dimension
        fov_narrow = 2 * math.atan(math.tan(fov_wide / 2) * min(rx, ry) / max(rx, ry))
        dist = radius * margin / math.sin(fov_narrow / 2)
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    direction = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = center + direction * dist
    look_at(cam, center)
    data.clip_start = max(min(data.clip_start, dist * 0.01), 1e-4)
    data.clip_end = max(data.clip_end, dist * 4)
    return cam


def add_framing_camera(azimuth_deg=35, elevation_deg=20, lens=50, margin=1.15,
                       ortho=False, exclude=HELPER_NAMES):
    """Create the scene camera on a 3/4 view that frames the whole subject."""
    data = bpy.data.cameras.new("Camera")
    data.lens = lens
    data.sensor_fit = "AUTO"
    if ortho:
        data.type = "ORTHO"
    cam = new_object("Camera", data)
    bpy.context.scene.camera = cam
    return place_camera(cam, azimuth_deg, elevation_deg, margin, exclude)


# ------------------------------------------------------- ground + lighting
def add_ground(size_factor=20.0, color=(0.5, 0.5, 0.5), roughness=0.7):
    """Ground plane under the subject (sized relative to it) for contact shadows."""
    lo, hi = scene_bounds()
    radius = max((hi - lo).length / 2, 0.01)
    obj = mesh_from_bmesh("Ground", lambda bm: bmesh.ops.create_grid(
        bm, x_segments=1, y_segments=1, size=radius * size_factor))
    obj.location = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)
    mat = bpy.data.materials.new("Ground")
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    obj.data.materials.append(mat)
    return obj


def _import_lighting_presets():
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    for path in (here, os.getcwd()):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import lighting_presets
        return lighting_presets
    except ImportError:
        return None


def add_default_lighting(preset="studio", **kwargs):
    """Size-aware lighting. Uses lighting_presets.py (see references/lighting.md);
    falls back to a minimal scaled 3-point rig if that file isn't available."""
    lp = _import_lighting_presets()
    if lp is not None:
        lp.apply_preset(preset, **kwargs)
        return
    print("[lighting] lighting_presets.py not found, using fallback rig")
    lo, hi = scene_bounds()
    center, r = (lo + hi) / 2, max((hi - lo).length / 2, 1e-3)
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.02
    for name, (az, el), irr, size in (("Key", (-40, 35), 5.2, 1.5), ("Fill", (50, 15), 1.8, 2.5),
                                      ("Rim", (160, 40), 4.6, 0.8)):
        d = 3.0 * r
        light = bpy.data.lights.new(name, "AREA")
        light.energy, light.size = irr * d * d, size * r
        o = new_object(name, light)
        a, e = math.radians(az), math.radians(el)
        o.location = center + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * d
        look_at(o, center)
    bpy.context.scene.view_settings.view_transform = "AgX"


# -------------------------------------------------------------------- render
def enable_gpu():
    """Use a GPU for Cycles when one exists. Returns the backend name or None."""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type != "CPU"]
        if gpus:
            for d in prefs.devices:
                d.use = d.type != "CPU"
            bpy.context.scene.cycles.device = "GPU"
            return backend
    bpy.context.scene.cycles.device = "CPU"
    return None


def setup_render(engine="CYCLES", samples=None, res=(1280, 720), transparent=False):
    """engine: "CYCLES" (works everywhere, realistic) or "EEVEE" (fast, but needs
    a GPU: without one it can be slower than Cycles on CPU)."""
    scene = bpy.context.scene
    scene.render.engine = {"CYCLES": "CYCLES", "EEVEE": "BLENDER_EEVEE"}[engine]
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = transparent
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    if engine == "CYCLES":
        print("[render] cycles device:", enable_gpu() or "CPU")
        scene.cycles.samples = samples or 64
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
    else:
        scene.eevee.taa_render_samples = samples or 32
        scene.eevee.use_raytracing = True


def render_still(path, verify=True):
    scene = bpy.context.scene
    if scene.camera is None:
        add_framing_camera()
    scene.render.filepath = path
    report_scene()
    bpy.ops.render.render(write_still=True)
    print("Rendered ->", path)
    return verify_render(path) if verify else None


def render_views(path, views=((35, 20), (125, 20), (215, 20), (0, 89)), res=(640, 360)):
    """Render the subject from several angles into one contact sheet PNG.
    Default: front 3/4, right 3/4, back 3/4, top. Use it to catch holes,
    flipped normals and wrong proportions that a single view hides."""
    import numpy as np
    scene = bpy.context.scene
    rs = scene.render
    saved = (rs.resolution_x, rs.resolution_y, rs.filepath)
    cam = scene.camera or add_framing_camera()
    saved_cam = (cam.location.copy(), cam.rotation_euler.copy())
    rs.resolution_x, rs.resolution_y = res
    tiles = []
    base, _ = os.path.splitext(path)
    for i, (az, el) in enumerate(views):
        place_camera(cam, az, el)
        rs.filepath = f"{base}_view{i}.png"
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(rs.filepath, check_existing=False)
        px = np.empty(len(img.pixels), dtype=np.float32)
        img.pixels.foreach_get(px)
        bpy.data.images.remove(img)
        tiles.append(px.reshape(res[1], res[0], 4))
    cols = 2
    rows = -(-len(tiles) // cols)
    sheet = np.ones((rows * res[1], cols * res[0], 4), dtype=np.float32)
    for k, tile in enumerate(tiles):
        r, c = divmod(k, cols)
        y = (rows - 1 - r) * res[1]  # image rows start at the bottom
        sheet[y:y + res[1], c * res[0]:(c + 1) * res[0]] = tile
    out = bpy.data.images.new("ContactSheet", sheet.shape[1], sheet.shape[0])
    out.pixels.foreach_set(sheet.ravel())
    out.filepath_raw, out.file_format = path, "PNG"
    out.save()
    bpy.data.images.remove(out)
    rs.resolution_x, rs.resolution_y, rs.filepath = saved
    cam.location, cam.rotation_euler = saved_cam
    print("Contact sheet ->", path)
    return path


# ----------------------------------------------------------------- checks
def report_scene():
    """Print what will be rendered. '0 lights' or 'camera: NONE' explains a
    black or empty render before you open the image."""
    scene = bpy.context.scene
    kinds = {}
    for o in scene.objects:
        kinds[o.type] = kinds.get(o.type, 0) + 1
    print("--- SCENE REPORT ---", bpy.app.version_string, scene.render.engine)
    print("  objects:", kinds, " camera:", scene.camera.name if scene.camera else "NONE!")
    lo, hi = scene_bounds()
    print("  subject bounds:", tuple(round(v, 4) for v in lo), "->", tuple(round(v, 4) for v in hi))
    for o in scene.objects:
        if o.type == "MESH":
            print(f"  mesh {o.name!r}: {len(o.data.vertices)} v, {len(o.data.polygons)} f, "
                  f"materials={[m.name for m in o.data.materials if m]}")
    world = scene.world
    world_strength = 0.0
    if world:
        bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        world_strength = bg.inputs["Strength"].default_value if bg else 1.0
    if not kinds.get("LIGHT") and world_strength <= 0:
        print("  WARNING: no lights and no world light -> render will be black")
    print("--------------------")


def verify_render(path, border_px=2):
    """Automatic QA of the written image. Returns a dict; prints warnings."""
    import numpy as np
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(h, w, 4)
    lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    transparent = bpy.context.scene.render.film_transparent
    if transparent and (px[..., 3] > 0.5).any():
        lum = lum[px[..., 3] > 0.5]  # judge exposure on the subject, not empty background
    res = {
        "mean_luminance": round(float(lum.mean()), 3),
        "clipped_white_%": round(float((lum > 0.98).mean() * 100), 2),
        "near_black_%": round(float((lum < 0.02).mean() * 100), 2),
        "contrast_std": round(float(lum.std()), 3),
    }
    warnings = []
    if res["mean_luminance"] < 0.05:
        warnings.append("nearly black: check lights, world strength, exposure")
    if res["clipped_white_%"] > 5:
        warnings.append("large blown-out area: lower light power or exposure")
    if res["contrast_std"] < 0.02:
        warnings.append("flat/uniform image: subject missing or camera aimed away")
    if transparent:
        a = px[..., 3]
        edges = np.concatenate([a[:border_px].ravel(), a[-border_px:].ravel(),
                                a[:, :border_px].ravel(), a[:, -border_px:].ravel()])
        if (edges > 0.5).mean() > 0.01:
            warnings.append("subject touches the frame edge: likely cropped")
        if (a > 0.5).mean() < 0.01:
            warnings.append("almost nothing rendered (alpha empty)")
    res["warnings"] = warnings
    print("--- RENDER QA ---", res)
    return res


if __name__ == "__main__":
    out = arg_value("--out", os.path.join(tempfile.gettempdir(), "render.png"))  # /tmp doesn't exist on Windows
    clean_scene()
    setup_render("CYCLES", samples=32)
    # ---- build your scene here ----
    cube = mesh_from_bmesh("Cube", lambda bm: bmesh.ops.create_cube(bm, size=2.0))
    cube.location.z = 1.0
    bevel = cube.modifiers.new("Bevel", "BEVEL")  # real objects never have razor edges
    bevel.width, bevel.segments = 0.05, 3
    # -------------------------------
    add_ground()
    add_default_lighting("studio")
    add_framing_camera()
    render_still(out)
