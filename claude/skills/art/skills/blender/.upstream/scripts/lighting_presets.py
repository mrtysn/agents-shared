"""
Size-aware lighting presets for Blender 5.x (tested on 5.2 LTS).

Copy this file next to your scene script (or paste the functions you need), then:

    import lighting_presets as lp
    lp.apply_preset("studio")            # after the subject geometry exists
    lp.balance_exposure()                # optional: auto-fix too dark / too bright

Every preset measures the subject first and places + scales lights to it, so the
same call works for a 2 cm ring and a 20 m house. Light power is scaled with
distance^2, which keeps the illumination on the subject constant.

Presets: studio, high_key, low_key, outdoor, golden_hour, overcast, night_neon.
See references/lighting.md for when to use which.
"""

import math
import bpy
from mathutils import Vector

# Objects ignored when measuring the subject (floors, backdrops, helpers).
DEFAULT_EXCLUDE = ("Ground", "Backdrop", "Floor")
LIGHT_COLLECTION = "Lights"


# ---------------------------------------------------------------- measurement
def subject_bounds(exclude=DEFAULT_EXCLUDE):
    """(center, radius, floor_z) of all renderable geometry, modifiers included."""
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for obj in bpy.context.scene.objects:
        if obj.name in exclude or obj.hide_render:
            continue
        if obj.type not in {"MESH", "CURVE", "FONT", "SURFACE", "META", "GREASEPENCIL"}:
            continue
        ev = obj.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    if not pts:
        return Vector((0, 0, 0)), 1.0, 0.0
    lo = Vector(tuple(min(p[i] for p in pts) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in pts) for i in range(3)))
    return (lo + hi) / 2, max((hi - lo).length / 2, 1e-3), lo.z


# ------------------------------------------------------------------- helpers
def _collection():
    coll = bpy.data.collections.get(LIGHT_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(LIGHT_COLLECTION)
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    return coll


def clear_lights():
    """Remove every light object (and the Lights collection's contents)."""
    for obj in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(obj, do_unlink=True)


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def direction(azimuth_deg, elevation_deg):
    """Unit vector. Azimuth 0 = in front of the subject (-Y, where the default
    camera sits), 90 = right (+X), 180 = behind. Elevation 0 = horizon."""
    az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
    return Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))


def add_area(name, azimuth, elevation, irradiance, center, radius,
             distance=3.0, size=1.0, kelvin=None, color=(1, 1, 1), shape="SQUARE",
             spread_deg=180):
    """Area light placed `distance * radius` from the subject center.

    irradiance: relative brightness at the subject, calibrated for AgX at
                exposure 0 on a mid-grey subject: 1-2 dim, ~5 normal key, 8+ bright. Power = irradiance * d^2 (inverse-square).
    size:       relative to subject radius. Bigger = softer shadows.
    kelvin:     colour temperature (1800 candle .. 3200 tungsten .. 5600 daylight
                .. 7500 shade). Overrides `color` when given.
    spread_deg: beam spread. 180 = bare panel; 30-60 = softbox with a grid, keeps
                light off the floor/background (essential for low-key looks).
    """
    d = distance * radius
    data = bpy.data.lights.new(name, "AREA")
    data.shape = shape
    data.size = size * radius
    if shape in {"RECTANGLE", "ELLIPSE"}:
        data.size_y = size * radius * 0.5
    data.energy = irradiance * d * d
    data.spread = math.radians(spread_deg)
    _colour(data, kelvin, color)
    obj = bpy.data.objects.new(name, data)
    _collection().objects.link(obj)
    obj.location = center + direction(azimuth, elevation) * d
    aim(obj, center)
    return obj


def add_sun(name, azimuth, elevation, strength=1.2, angle_deg=0.53, kelvin=5600):
    """Sun lamp shining FROM (azimuth, elevation). strength is W/m^2 and does not
    depend on distance. Calibrated with AgX at exposure 0: ~1.2 = clear midday,
    ~1.0 = low sun. Values in the hundreds blow the frame out completely."""
    data = bpy.data.lights.new(name, "SUN")
    data.energy = strength
    data.angle = math.radians(angle_deg)  # 0.53 = real sun, 2-5 = softer shadows
    _colour(data, kelvin, (1, 1, 1))
    obj = bpy.data.objects.new(name, data)
    _collection().objects.link(obj)
    obj.location = direction(azimuth, elevation) * 10
    aim(obj, (0, 0, 0))
    return obj


def _colour(light_data, kelvin, color):
    if kelvin:
        light_data.use_temperature = True
        light_data.temperature = kelvin
    else:
        light_data.use_temperature = False
        light_data.color = color


# --------------------------------------------------------------------- world
def _world():
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    return world


def set_world_color(color=(0.05, 0.05, 0.06), strength=1.0):
    """Uniform ambient light. Strength 0 = pure black world (lights only)."""
    nt = _world().node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return bg


def set_world_sky(sun_azimuth=135, sun_elevation=35, strength=0.12,
                  sky_type="MULTIPLE_SCATTERING", sun_disc=False, air=1.0, dust=1.0):
    """Physical sky. Pair with add_sun() at the same azimuth/elevation for crisp
    shadows (sun_disc=False avoids counting the sun twice).

    The physical sky is very bright: `strength` ~0.03-0.04 pairs with a
    1.2 W/m^2 sun lamp at exposure 0 (raise it for a low sun, ~0.1)."""
    nt = _world().node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = sky_type
    sky.sun_disc = sun_disc
    sky.sun_elevation = math.radians(sun_elevation)
    # Sky rotation 0 points the sun toward +Y; convert from our azimuth convention.
    sky.sun_rotation = math.radians((180 - sun_azimuth) % 360)
    sky.air_density = air
    sky.aerosol_density = dust
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return sky


def set_world_hdri(path, strength=1.0, rotation_deg=0.0, camera_color=None):
    """HDRI lighting + reflections. camera_color=(r, g, b) shows a flat colour
    to the camera while the HDRI still lights the scene and appears in
    reflections (Light Path 'Is Camera Ray' mix). Works in Cycles and EEVEE."""
    nt = _world().node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(path, check_existing=True)
    mapping.inputs["Rotation"].default_value[2] = math.radians(rotation_deg)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    final = bg
    if camera_color is not None:
        flat = nt.nodes.new("ShaderNodeBackground")
        flat.inputs["Color"].default_value = (*camera_color, 1)
        path_node = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(path_node.outputs["Is Camera Ray"], mix.inputs["Fac"])
        nt.links.new(bg.outputs["Background"], mix.inputs[1])
        nt.links.new(flat.outputs["Background"], mix.inputs[2])
        final = mix
    nt.links.new(final.outputs[0], out.inputs["Surface"])
    return env


# ------------------------------------------------------------- tone mapping
def set_view(transform="AgX", look="AgX - Base Contrast", exposure=0.0):
    vs = bpy.context.scene.view_settings
    vs.view_transform = transform
    try:
        vs.look = look
    except TypeError:
        vs.look = "None"
    vs.exposure = exposure


# ------------------------------------------------------------------- presets
def preset_studio(c, r, floor_z):
    """Product/character default. Soft key 3:1 over fill, rim for separation."""
    set_world_color((0.8, 0.85, 1.0), 0.02)
    add_area("Key", -40, 35, 5.2, c, r, size=1.5, kelvin=5000)
    add_area("Fill", 50, 15, 1.8, c, r, size=2.5, kelvin=6500)
    add_area("Rim", 160, 40, 4.6, c, r, size=0.8, kelvin=6000)
    set_view(look="AgX - Medium High Contrast")


def preset_high_key(c, r, floor_z):
    """Bright, almost shadowless, e-commerce / clean white look."""
    set_world_color((1, 1, 1), 0.32)
    add_area("Key", -30, 45, 8.5, c, r, size=3.0, kelvin=5600)
    add_area("Fill", 40, 20, 5.6, c, r, size=3.0, kelvin=5600)
    add_area("Top", 0, 85, 4.2, c, r, size=4.0, kelvin=6000)
    set_view(look="AgX - Base Contrast")


def preset_low_key(c, r, floor_z):
    """Dramatic: one side key, hard-ish shadows, strong rim, near-black world."""
    set_world_color((0.02, 0.025, 0.04), 0.002)
    add_area("Key", -55, 30, 0.75, c, r, distance=2.2, size=0.6, kelvin=4200, spread_deg=40)
    add_area("Rim", 150, 30, 1.0, c, r, distance=2.5, size=0.4, kelvin=7000, spread_deg=45)
    set_view(look="AgX - High Contrast")


def preset_outdoor(c, r, floor_z, sun_azimuth=-45, sun_elevation=45):
    """Clear day: physical sky for ambient + sun lamp for crisp shadows."""
    set_world_sky(sun_azimuth, sun_elevation, strength=0.036)
    add_sun("Sun", sun_azimuth, sun_elevation, strength=1.2, kelvin=5600)
    set_view(look="AgX - Base Contrast")


def preset_golden_hour(c, r, floor_z, sun_azimuth=-70):
    """Low warm sun, long shadows, cool sky fill."""
    set_world_sky(sun_azimuth, 6, strength=0.1, dust=3.0)
    add_sun("Sun", sun_azimuth, 6, strength=1.05, angle_deg=1.5, kelvin=3000)
    set_view(look="AgX - Medium High Contrast")


def preset_overcast(c, r, floor_z):
    """Cloudy day: soft directionless light, faint shadows."""
    set_world_color((0.85, 0.88, 0.95), 0.31)
    add_area("Sky", -20, 80, 2.2, c, r, distance=4, size=6.0, kelvin=6800)
    set_view(look="AgX - Base Contrast")


def preset_night_neon(c, r, floor_z):
    """Dark blue ambient + coloured magenta/cyan rims. Add emissive props to sell it."""
    set_world_color((0.01, 0.015, 0.04), 0.03)
    add_area("NeonL", -110, 20, 4.5, c, r, size=1.2, color=(1.0, 0.1, 0.6), shape="RECTANGLE")
    add_area("NeonR", 110, 20, 4.5, c, r, size=1.2, color=(0.1, 0.7, 1.0), shape="RECTANGLE")
    add_area("Moon", 0, 60, 0.32, c, r, size=2.0, kelvin=9000)
    set_view(look="AgX - Medium High Contrast")


PRESETS = {
    "studio": preset_studio,
    "high_key": preset_high_key,
    "low_key": preset_low_key,
    "outdoor": preset_outdoor,
    "golden_hour": preset_golden_hour,
    "overcast": preset_overcast,
    "night_neon": preset_night_neon,
}


def apply_preset(name="studio", exclude=DEFAULT_EXCLUDE, clear=True, **kwargs):
    """Measure the subject, (optionally) remove existing lights, build the rig."""
    if clear:
        clear_lights()
    c, r, floor_z = subject_bounds(exclude)
    PRESETS[name](c, r, floor_z, **kwargs)
    print(f"[lighting] preset={name} center={tuple(round(v, 3) for v in c)} radius={r:.3f}")


# ------------------------------------------------------------ auto exposure
def measure_luminance(res=160, samples=8):
    """Render a tiny preview and return mean display luminance (0..1).
    Restores all render settings afterwards."""
    import numpy as np
    import os
    import tempfile
    scene = bpy.context.scene
    rs = scene.render
    saved = (rs.resolution_percentage, rs.filepath, rs.image_settings.file_format,
             scene.cycles.samples if rs.engine == "CYCLES" else scene.eevee.taa_render_samples)
    path = os.path.join(tempfile.gettempdir(), "_lum_probe.png")
    rs.resolution_percentage = max(1, int(100 * res / max(rs.resolution_x, rs.resolution_y)))
    rs.filepath, rs.image_settings.file_format = path, "PNG"
    if rs.engine == "CYCLES":
        scene.cycles.samples = samples
    else:
        scene.eevee.taa_render_samples = samples
    bpy.ops.render.render(write_still=True)
    rs.resolution_percentage, rs.filepath, rs.image_settings.file_format = saved[:3]
    if rs.engine == "CYCLES":
        scene.cycles.samples = saved[3]
    else:
        scene.eevee.taa_render_samples = saved[3]
    img = bpy.data.images.load(path, check_existing=False)
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(-1, 4)
    return float((px[:, :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)).mean())


def balance_exposure(target=0.42, tolerance=0.03, iterations=4):
    """Adjust view exposure until a tiny preview's mean luminance is near `target`.
    0.42 suits mid-grey subjects; ~0.6 high-key, ~0.25 low-key, ~0.2 night.
    Uses a secant step on log(luminance) vs exposure, so it usually converges in
    2-3 preview renders. Exposure is a linear scene multiplier (2**EV) applied
    before the view transform, i.e. equivalent to scaling every light."""
    vs = bpy.context.scene.view_settings
    slope = 0.35  # d ln(lum) / d EV for AgX mid-tones; refined after each probe
    prev = None
    for _ in range(iterations):
        lum = measure_luminance()
        print(f"[lighting] exposure={vs.exposure:+.2f} mean_lum={lum:.3f}")
        if abs(lum - target) <= tolerance or lum <= 1e-4:
            break
        if prev is not None and abs(vs.exposure - prev[0]) > 1e-3:
            measured = (math.log(lum) - math.log(prev[1])) / (vs.exposure - prev[0])
            if measured > 0.05:
                slope = measured
        prev = (vs.exposure, lum)
        vs.exposure += max(-4, min(4, (math.log(target) - math.log(lum)) / slope))
    return vs.exposure
