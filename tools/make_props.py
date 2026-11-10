# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds openmanager/props.json (the Property Selector table) for every engine.

    python mzp/tools/make_props.py <tables.json>

<tables.json> holds the per-engine property lists ({"corona_cam": [...], ...}). Extra Corona camera
overrides (tone mapping, direct / reflections / refractions / environment) are added here.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "package", "OpenManager", "openmanager", "props.json")

TABS = [
    (1, "Standard Camera", ["Freecamera", "Targetcamera"], None, "max_standard_cam", "Standard"),
    (1, "Physical Camera", ["Physical"], None, "max_physical_cam", "Physical Camera"),
    (1, "V-Ray Camera", ["VRayPhysicalCamera"], "vray", "vray_cam", "VRayPhysicalCamera"),
    (1, "Corona Camera", ["CoronaCam"], "corona", "corona_cam", "CoronaCam"),
    (1, "Corona Overrides", ["CoronaCam"], "corona", "corona_cam_overrides", "CoronaCam"),
    (1, "FStorm Camera", ["FStormCamera"], "fstorm", "fstorm_cam", "FStormCamera"),
    (3, "V-Ray Sun", ["VRaySun"], "vray", "vray_sun", "VRaySun"),
    (3, "V-Ray Clouds", ["VRaySun"], "vray", "vray_cloud", "VRaySun"),
    (3, "Corona Sun", ["CoronaSun"], "corona", "corona_sun", "CoronaSun"),
    (3, "FStorm Sun", ["FStormSunLight"], "fstorm", "fstorm_sun", "FStormSunLight"),
    (3, "Daylight", ["DaylightAssemblyHead"], None, "max_daylight", "DaylightAssemblyHead"),
    (4, "Bitmap", ["Bitmaptexture"], None, "max_bitmap", "Bitmaptexture"),
    (4, "ColorCorrection", ["Color_Correction"], None, "max_cc", "Color_Correction"),
    (4, "V-Ray Bitmap", ["VRayHDRI"], "vray", "vray_bitmap", "VRayHDRI"),
    (4, "V-Ray Dome", ["VRayLight"], "vray", "vray_dome", "VRayLight"),
    (6, "Bitmap", ["Bitmaptexture"], None, "max_bitmap", "Bitmaptexture"),
    (6, "Default CC", ["Color_Correction"], None, "max_cc", "Color_Correction"),
    (6, "V-Ray Bitmap", ["VRayHDRI"], "vray", "vray_bitmap", "VRayHDRI"),
    (6, "Corona Bitmap", ["CoronaBitmap"], "corona", "corona_bitmap", "CoronaBitmap"),
    (6, "Corona CC", ["CoronaColorCorrect"], "corona", "corona_cc", "CoronaColorCorrect"),
    (6, "Corona Select", ["CoronaSelect"], "corona", "corona_select", "CoronaSelect"),
    (6, "FStorm Bitmap", ["FStormBitmap"], "fstorm", "fstorm_bitmap", "FStormBitmap"),
    (6, "FStorm ColorCorrect", ["FStormColorCorrection"], "fstorm", "fstorm_cc", "FStormColorCorrection"),
    (6, "Corona Sky/Clouds", ["CoronaSky"], "corona", "corona_cloud", "CoronaSky"),
    (14, "Layers", None, None, "max_layers", "Layers"),
    (23, "General", None, None, "max_objects", "Objects"),
    (23, "V-Ray", None, "vray", "vray_objects", "Objects"),
    (25, "V-Ray", ["VRayRenderer"], "vray", "vray_render", "VRayRenderer"),
    (25, "V-Ray GPU", ["VRayGPURenderer"], "vraygpu", "vraygpu_render", "VRayGPURenderer"),
    (25, "Corona", ["CoronaRenderer"], "corona", "corona_render", "CoronaRenderer"),
    (25, "FStorm", ["FStormRenderer"], "fstorm", "fstorm_render", "FStormRenderer"),
    (26, "V-Ray Light", ["VRayLight"], "vray", "vray_light", "VRayLight"),
    (26, "Corona Light", ["CoronaLight"], "corona", "corona_light", "CoronaLight"),
    (26, "FStorm Light", ["FStormLight"], "fstorm", "fstorm_light", "FStormLight"),
]


def P(name, cls, short, long=None, mn=None, mx=None, step=None, value=None):
    d = {"name": name, "class": cls, "display": [short, long or short], "value": value}
    if mn is not None:
        d["min"], d["max"] = mn, mx
    if step is not None:
        d["step"] = step
    return d


# Corona Camera > Overrides: tone mapping and what the camera sees directly / in reflections / refractions
CORONA_CAM_OVERRIDES = [
    P("colorMappingOverride", "BooleanClass", "Override tone mapping", "Tone mapping: override global"),
    P("colorMappingEnabled", "BooleanClass", "Tone mapping enabled", "Tone mapping: enabled"),
    P("colorMappingPipeline", "Pipeline", "Tone mapping operators", "Tone mapping: operators (taken from the camera)"),
    P("directOverride", "BooleanClass", "Direct override", "Environment: direct visibility override"),
    P("directOverrideColor", "Color", "Direct color", "Environment: direct override color"),
    P("directOverrideTexmapUse", "BooleanClass", "Direct use map", "Environment: direct override uses map"),
    P("directOverrideTexmap", "Texturemap", "Direct map", "Environment: direct override map"),
    P("reflectOverride", "BooleanClass", "Reflections override", "Environment: reflections override"),
    P("reflectOverrideColor", "Color", "Reflections color", "Environment: reflections override color"),
    P("reflectOverrideTexmapUse", "BooleanClass", "Reflections use map", "Environment: reflections override uses map"),
    P("reflectOverrideTexmap", "Texturemap", "Reflections map", "Environment: reflections override map"),
    P("refractOverride", "BooleanClass", "Refractions override", "Environment: refractions override"),
    P("refractOverrideColor", "Color", "Refractions color", "Environment: refractions override color"),
    P("refractOverrideTexmapUse", "BooleanClass", "Refractions use map", "Environment: refractions override uses map"),
    P("refractOverrideTexmap", "Texturemap", "Refractions map", "Environment: refractions override map"),
    P("enviroOverride", "BooleanClass", "Environment override", "Environment: global environment override"),
    P("enviroOverrideColor", "Color", "Environment color", "Environment: override color"),
    P("enviroOverrideTexmapUse", "BooleanClass", "Environment use map", "Environment: override uses map"),
    P("enviroOverrideTexmap", "Texturemap", "Environment map", "Environment: override map"),
    P("overrideVisibility", "BooleanClass", "Override visibility", "Visibility: exclude list override"),
    P("overrideSharpening", "BooleanClass", "Override sharpening", "Sharpening/blurring: override"),
    P("enableSharpening", "BooleanClass", "Sharpening enabled", "Sharpening/blurring: enabled"),
    P("sharpeningAmount", "Float", "Sharpening amount", None, 0, 10, 0.01),
    P("sharpeningRadius", "Float", "Sharpening radius", None, 0, 10, 0.01),
    P("blurringRadius", "Float", "Blurring radius", None, 0, 10, 0.01),
    P("bloomGlareSize", "Float", "Bloom/glare size", None, 0, 100, 0.1),
    P("bloomGlareColorIntensity", "Float", "Bloom/glare color", "Bloom/glare: color intensity", 0, 1, 0.01),
    P("bloomGlareColorShift", "Float", "Bloom/glare color shift", None, 0, 1, 0.01),
    P("glareStreakCount", "Integer", "Glare streaks", "Glare: streak count", 1, 8, 1),
    P("glareRotation", "Float", "Glare rotation", None, 0, 360, 1),
    P("glareStreakBlur", "Float", "Glare streak blur", None, 0, 1, 0.01),
    P("overrideBokeh", "BooleanClass", "Override bokeh", "Bokeh: override"),
    P("bokehBladeCount", "Integer", "Bokeh blades", None, 3, 12, 1),
    P("bokehRotation", "Float", "Bokeh rotation", None, 0, 360, 1),
    P("shutterAngle", "Float", "Shutter angle", None, 0, 360, 1),
    P("projection", "Integer", "Projection", "Projection (0 perspective, 1 cylindrical, 2 spherical, 3 VR, 4 fisheye, 5 ortho)", 0, 5, 1),
]

CORONA_RENDER_EXTRA = [
    P("denoise_filterType", "Integer", "Denoiser", "Denoiser (0 none, 1 high quality, 2 NVIDIA, 3 Intel)", 0, 3, 1),
    P("denoise_blendAmount", "Float", "Denoise amount", None, 0, 1, 0.01),
    P("progressive_passLimit", "Integer", "Pass limit", None, 0, 500, 1),
    P("shading_secondarySolver", "Integer", "Secondary GI solver", "Secondary GI solver (0 path tracing, 3 UHD cache)", 0, 4, 1),
    P("lockSampling", "BooleanClass", "Lock sampling pattern"),
    P("system_numThreads", "Integer", "Render threads", "Render threads (0 = all)", 0, 256, 1),
]


def tab_props(raw):
    out = []
    for p in raw:
        disp = p.get("display")
        if isinstance(disp, list):
            short, long = (disp + [disp[0]])[:2]
        else:
            short = long = disp or p["name"]
        d = {"name": p["name"], "class": p.get("class", "Float"), "short": short, "long": long,
             "value": p.get("value"), "enabled": bool(p.get("enabled"))}
        for k in ("min", "max", "step"):
            if p.get(k) is not None:
                d[k] = p[k]
        if p.get("unit"):
            d["unit"] = p["unit"]
        out.append(d)
    return out


def main(tables_path):
    tables = json.load(open(tables_path, encoding="utf-8"))
    tables["corona_cam_overrides"] = CORONA_CAM_OVERRIDES
    have = set(p["name"] for p in tables.get("corona_render", []))
    tables["corona_render"] = tables.get("corona_render", []) + [p for p in CORONA_RENDER_EXTRA if p["name"] not in have]
    tabs = []
    for cid, name, cls, engine, key, v_class in TABS:
        props = tab_props(tables.get(key, []))
        if not props:
            print("no table for", key)
            continue
        tabs.append({"id": cid, "name": name, "cls": cls[0] if cls else None, "classes": cls, "engine": engine,
                     "v_class": v_class, "props": props})
    json.dump(tabs, open(OUT, "w", encoding="utf-8"), indent=1)
    print("wrote %s: %d tabs, %d settings" % (OUT, len(tabs), sum(len(t["props"]) for t in tabs)))


if __name__ == "__main__":
    main(sys.argv[1])
