"""Setups, the property table and the render-output path builder.

Pure Python (no 3ds Max, no Qt) so it can be tested on its own.
"""
import base64
import copy
import datetime
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_RATIO = 1.778
DEFAULT_FRAME_LIST = "1,3,5-12"
DEFAULT_DATE_FORMAT = "YYYYMMDD"

RESOLUTION_PRESETS = [
    (320, 240), (720, 486), (640, 480), (800, 600), (1280, 720),
    (1920, 1080), (2560, 1440), (3840, 2160), (5120, 2880), (7680, 4320),
]
EXTENSIONS = [".jpg", ".png", ".tif", ".tga", ".bmp", ".exr"]
DATE_FORMATS = ["YYYYMMDD", "YYYY-MM-DD", "MMDDYYYY", "MM-DD-YYYY", "YYMMDD", "YY-MM-DD", "MMDDYY", "MM-DD-YY"]
TOKEN_TYPES = [
    "Camera", "Date", "Date (Folder)", "Extension", "FileName (Full)", "FileName (Filtered)",
    "FileVersion", "Folder", "Index", "PcName", "SceneName", "Text", "UserName", "Version",
]
SKY_CLASSES = ["VRaySky", "CoronaSky", "FStormSky", "Physical_Sun___Sky_Environment"]

# cards: id -> (title, header tint, has on/off switch, has copy/paste, has property selector)
CARDS = {
    0: ("Setup List", None, False, False, False),
    1: ("Camera", "space", True, True, True),
    2: ("Resolution", "space", True, True, False),
    7: ("Time Output", "space", True, True, False),
    15: ("Scene Name", "space", False, True, False),
    3: ("Sun", "yellow", True, True, True),
    26: ("Lights", "yellow", True, True, True),
    28: ("Hdri Quick Browser", "yellow", False, False, False),
    6: ("Environment", "yellow", True, True, True),
    4: ("Dome", "yellow", True, True, True),
    8: ("Background", "blue", True, True, False),
    20: ("Atmosphere", "blue", True, True, False),
    14: ("Layers", "eton", True, True, True),
    23: ("Objects", "eton", True, True, True),
    16: ("Xref - Scene", "eton", True, True, False),
    30: ("Variants", "eton", True, True, False),
    9: ("Render Output - Common", "lightgreen", True, True, False),
    25: ("Render Settings - Custom", "salmon", True, True, True),
    19: ("Render Settings - Override", "salmon", True, True, False),
    18: ("Render Settings - Preset", "salmon", True, True, False),
    21: ("Render Elements", "salmon", True, True, False),
    29: ("Post-Production / VFB", "purple", True, True, False),
    17: ("Script - File", "baby", True, True, False),
    22: ("Script - Editor", "baby", True, True, False),
    31: ("Thumbnail", "noted", False, False, False),
    13: ("Todo", "noted", False, False, False),
    12: ("Notes", "noted", False, True, False),
}
# order of the side bar (a change of tint starts a new group) and of the "Cards" menu
CARD_ORDER = [1, 2, 7, 15, 3, 26, 28, 6, 4, 8, 20, 14, 23, 16, 30, 9, 25, 19, 18, 21, 29, 17, 22, 31, 13, 12]
DEFAULT_VISIBLE = [0, 1, 2, 15, 3, 28, 6, 14, 23, 9, 25]
# engines a card works with (empty = all)
CARD_ENGINES = {4: ["vray", "vraygpu"], 26: ["vray", "vraygpu", "corona", "fstorm"],
                25: ["vray", "vraygpu", "corona", "fstorm"], 19: ["vray", "vraygpu", "corona", "fstorm"],
                21: ["vray", "vraygpu", "corona", "fstorm"], 29: ["corona"]}
# setup key holding the on/off switch of each card
CARD_KEY = {1: "camera", 2: "resolution", 7: "frames", 3: "sun", 26: "lights", 4: "dome", 6: "environment",
            14: "layers", 23: "objects", 16: "xref", 9: "output", 25: "render_custom", 8: "background",
            20: "atmosphere", 30: "variants", 19: "rs_override", 18: "render_preset", 21: "elements",
            29: "post", 17: "scripts", 22: "snippet"}
# smallest size of each card in grid units (columns, rows); a row is about 11 px
MIN_SIZE = {0: (6, 20), 9: (6, 20), 22: (6, 20), 1: (3, 10), 2: (3, 10), 7: (3, 10), 15: (3, 10), 3: (3, 10),
            6: (3, 10), 8: (3, 10), 18: (3, 10)}
# default places [x, y, w, h]: 12 columns (wide window) and 6 columns (narrow)
LAYOUT_LG = {0: [0, 0, 6, 40], 15: [0, 40, 3, 10], 1: [3, 40, 3, 14], 7: [0, 50, 3, 12], 2: [3, 54, 3, 10],
             9: [0, 64, 6, 20], 3: [6, 0, 3, 20], 28: [9, 0, 3, 30], 6: [6, 20, 3, 30], 4: [9, 30, 3, 20],
             26: [9, 50, 3, 20], 14: [6, 50, 3, 24], 23: [9, 70, 3, 20], 16: [6, 74, 3, 20], 30: [9, 90, 3, 20],
             8: [0, 84, 3, 10], 20: [3, 84, 3, 20], 25: [6, 94, 3, 20], 19: [9, 110, 3, 24], 18: [6, 114, 3, 10],
             21: [6, 124, 3, 20], 29: [9, 134, 3, 30], 17: [0, 104, 3, 20], 22: [0, 124, 6, 22], 31: [3, 104, 3, 20],
             13: [0, 146, 3, 20], 12: [3, 146, 3, 20]}
LAYOUT_MD = {0: [0, 0, 6, 34], 15: [0, 34, 3, 10], 1: [3, 34, 3, 14], 7: [0, 44, 3, 12], 2: [3, 48, 3, 10],
             3: [0, 58, 3, 14], 28: [3, 58, 3, 30], 6: [0, 72, 3, 30], 4: [3, 88, 3, 20], 26: [3, 108, 3, 20],
             14: [0, 102, 3, 24], 23: [3, 128, 3, 20], 16: [0, 126, 3, 20], 30: [3, 148, 3, 20], 9: [0, 168, 6, 20],
             8: [0, 188, 3, 10], 20: [3, 188, 3, 20], 25: [0, 198, 3, 20], 19: [3, 208, 3, 24], 18: [0, 218, 3, 10],
             21: [0, 228, 3, 20], 29: [3, 232, 3, 30], 17: [0, 248, 3, 20], 22: [0, 268, 6, 22], 31: [3, 262, 3, 20],
             13: [0, 290, 3, 20], 12: [3, 290, 3, 20]}
BACKGROUND_TYPES = ["Gradient", "Solid", "Environment", "Custom file"]


def engine_id(name):
    for n, i in (("V-Ray", "vray"), ("Corona", "corona"), ("Arnold", "arnold"), ("FStorm", "fstorm")):
        if n in (name or ""):
            return i
    return None


def parse_number(text):
    """What a person types in a number box: ".5", "-.5", ",5", "1,25", "2." are numbers too. None if it isn't one."""
    t = (text or "").strip().replace(" ", "").replace(",", ".")
    if t.startswith("+"):
        t = t[1:]
    if t in ("", "-", ".", "-."):
        return None
    if t.startswith("."):
        t = "0" + t
    elif t.startswith("-."):
        t = "-0" + t[1:]
    try:
        return float(t)
    except ValueError:
        return None


# ---------------------------------------------------------------- property table

_TABS = None


def all_tabs():
    global _TABS
    if _TABS is None:
        with open(os.path.join(HERE, "props.json"), "r", encoding="utf-8") as f:
            _TABS = json.load(f)
    return _TABS


def tabs_for(card, engine):
    return [t for t in all_tabs() if t["id"] == card and (t.get("engine") in (None, engine))]


def tab_matches(tab, cls):
    """Is this Property Selector tab for objects of class cls?"""
    if not cls:
        return False
    return cls in (tab.get("classes") or []) or tab.get("cls") == cls


def prop_key(tab, prop):
    return "%s|%s" % (tab["v_class"], prop["name"])


def default_enabled(card):
    if card == 6:
        return ["CoronaBitmap|uAngle", "CoronaBitmap|uvwOffset.y", "CoronaBitmap|output.output_amount",
                "CoronaSky|intensityMultiplier", "CoronaSky|HorizonBlur", "CoronaSky|altitude",
                "CoronaSky|cloudsEnable", "CoronaSky|cloudsSeed", "CoronaSky|cloudsContrailsStrength"]
    out = []
    for t in all_tabs():
        if t["id"] == card:
            out.extend(prop_key(t, p) for p in t["props"] if p.get("enabled"))
    return out


def enabled_rows(card, engine, enabled_keys):
    """(tab, prop) pairs ticked for a card, in table order."""
    on = set(enabled_keys)
    rows = []
    for t in tabs_for(card, engine):
        for p in t["props"]:
            if prop_key(t, p) in on:
                rows.append((t, p))
    return rows


# Daylight: controller.solar_date counts days from June 21 of the current year (what the Motion panel shows)
def solar_base(today=None):
    return datetime.date((today or datetime.date.today()).year, 6, 21)


def solar_to_date(v, today=None):
    try:
        return solar_base(today) + datetime.timedelta(days=int(round(float(v or 0))))
    except (TypeError, ValueError, OverflowError):
        return solar_base(today)


def date_to_solar(d, today=None):
    return float((d - solar_base(today)).days)


# ---------------------------------------------------------------- more than one sun / environment in a setup

def entries(block):
    """The tabs of a Sun / Environment card: the block itself, then its extra entries."""
    return [block] + list(block.get("extra") or [])


def entry_store(s, block, i):
    """Where tab i keeps its settings: the first one in the setup's props, the others in their own."""
    if i <= 0:
        return s["props"]
    return block["extra"][i - 1].setdefault("props", {})


def new_env_entry():
    return {"cls": "", "name": "", "props": {}, "on": True, "amount": 1.0}


def env_mixing(block, engine):
    """Several environment tabs are added together in the environment slot (like a LightMix): Corona, two tabs or more."""
    return engine == "corona" and len(entries(block)) > 1 and bool(block.get("mix", True))


def env_mix_items(block, find_map):
    """(class, name, intensity) of the tabs that go in the mix: chosen, found in the scene and on."""
    out = []
    for en in entries(block):
        m = find_map(en.get("cls"), en.get("name")) if en.get("cls") else None
        if m and en.get("on", True):
            try:
                a = float(en.get("amount", 1.0))
            except (TypeError, ValueError):
                a = 1.0
            out.append((m["class"], m["name"], round(max(0.0, a), 4)))
    return tuple(out)


def env_rows(m, enabled_rows_):
    """Ticked settings of an environment map and of every map linked below it: (tab, prop, link, key class).
    A second map of the same class (two bitmaps under a select) gets its own key."""
    rows = []
    seen = {}
    for link in (m.get("chain") or [m]):
        cls = link["class"]
        n = seen.get(cls, 0)
        seen[cls] = n + 1
        key_cls = cls if n == 0 else "%s@%s" % (cls, link["name"])
        for t, p in enabled_rows_:
            if t["v_class"] == cls:
                rows.append((t, p, link, key_cls))
    return rows


def light_tabs_classes(l):
    """Classes whose tabs apply to a sun: a Daylight shows its own tab and the one of the sun inside it."""
    if not l:
        return []
    return [c for c in (l.get("class"), l.get("sun_class")) if c]


def light_prop(l, tab, prop):
    """Property path on the node: settings of the sun inside a Daylight go through .sun"""
    if l and l.get("sun_class") and tab_matches(tab, l.get("sun_class")) and not tab_matches(tab, l.get("class")):
        return "sun." + prop["name"]
    return prop["name"]


# ---------------------------------------------------------------- Post-Production / VFB (Corona)

# category: title and the renderer settings it holds; the first one turns the category on in the VFB
POST_CATS = [
    ("bloom", "Bloom and Glare", ["bloomGlare_enabled", "bloomGlare_bloomIntensity", "bloomGlare_glareIntensity", "bloomGlare_threshold",
                                  "bloomGlare_size", "bloomGlare_colorIntensity", "bloomGlare_colorShift", "bloomGlare_streakCount",
                                  "bloomGlare_rotation", "bloomGlare_streakBlur"]),
    ("sharpen", "Sharpening / Blurring", ["sharpening_blurring_enable", "sharpening_amount", "sharpening_radius", "blurring_radius"]),
    ("denoise", "Denoising", ["denoise_blendEnabled", "denoise_blendAmount"]),
    ("auto", "Auto Adjust", ["autoAdjust_on", "autoAdjust_expOn", "autoAdjust_expStrength", "autoAdjust_wbOn", "autoAdjust_wbStrength"]),
    ("lens", "Lens Effects", ["lensEffects_peripheralGrating_enabled", "lensEffects_peripheralGrating_strength",
                              "lensEffects_occlusion_enabled", "lensEffects_occlusion_ratio",
                              "lensEffects_scratches_enabled", "lensEffects_scratches_strength",
                              "lensEffects_dust_enabled", "lensEffects_dust_strength"]),
]
POST_ORDER = ["tonemap", "lightmix", "bloom", "sharpen", "denoise", "auto", "lens"]
POST_TITLES = dict([("tonemap", "Tone Mapping"), ("lightmix", "LightMix")] + [(k, t) for k, t, _ in POST_CATS])
POST_OPERATORS = {
    "SimpleExposureOperatorPlugin": "Simple Exposure", "PhotographicExposureOperatorPlugin": "Photographic Exposure",
    "ContrastOperatorPlugin": "Contrast", "SaturationOperatorPlugin": "Saturation", "FilmicOperatorPlugin": "Filmic",
    "AdvancedFilmicOperatorPlugin": "Advanced Filmic", "ReinhardOperatorPlugin": "Highlight Compression",
    "WhiteBalanceOperatorPlugin": "White Balance", "WhiteBalanceImprovedOperatorPlugin": "White Balance",
    "GreenMagentaTintOperatorPlugin": "Green-Magenta Tint", "TintOperatorPlugin": "Tint", "ToneCurveOperatorPlugin": "Tone Curve",
    "CurvesOperatorPlugin": "Curves", "LiftGammaGainOperatorPlugin": "Lift Gamma Gain", "VignetteOperatorPlugin": "Vignette",
    "LutOperatorPlugin": "LUT", "AcesOtOperatorPlugin": "ACES OT",
}
POST_RANGE = {"simpleExposure": (-10, 10), "contrast": (0, 10), "saturation": (-1, 1), "highlightCompression": (1, 99),
              "colorTemperature": (1000, 20000), "greenMagentaTint": (-1, 1), "opacity": (0, 1), "richShadows": (0, 1),
              "highlights": (-1, 1), "lights": (-1, 1), "darks": (-1, 1), "shadows": (-1, 1), "intensity": (0, 2), "falloff": (0, 2),
              "lift": (0, 2), "gamma": (0, 5), "gain": (0, 5), "toeStrength": (0, 1), "toeLength": (0, 1),
              "shoulderStrength": (0, 1), "shoulderLength": (0, 1), "shoulderAngle": (0, 1),
              "bloomIntensity": (0, 100), "glareIntensity": (0, 100), "threshold": (0, 100), "size": (0, 100),
              "colorIntensity": (0, 1), "colorShift": (0, 1), "streakCount": (1, 8), "rotation": (0, 360), "streakBlur": (0, 1),
              "amount": (0, 10), "radius": (0, 10), "blendAmount": (0, 1), "expStrength": (0, 1), "wbStrength": (0, 1),
              "strength": (0, 2), "ratio": (0, 1)}


def post_label(name):
    """colorMappingOperator_highlightCompression -> Highlight Compression; bloomGlare_size -> Size."""
    leaf = name.split("_")[-1]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", leaf[:1].upper() + leaf[1:])


def post_range(name, value=None):
    leaf = name.split("_")[-1]
    lo, hi = POST_RANGE.get(leaf, (0, 10))
    try:
        v = float(value)
        lo, hi = min(lo, v), max(hi, v)
    except (TypeError, ValueError):
        pass
    return lo, hi


# 3ds Max keeps the time limit in milliseconds, the card shows minutes
def to_max(name, v):
    return v * 60000.0 if name == "progressive_timeLimit" else v


def from_max(name, v):
    return v / 60000.0 if name == "progressive_timeLimit" else v


# ---------------------------------------------------------------- setups

def new_token(kind):
    value = {"Extension": ".jpg", "Date": DEFAULT_DATE_FORMAT, "Date (Folder)": DEFAULT_DATE_FORMAT,
             "Version": "1", "Text": "_"}.get(kind, "")
    return {"kind": kind, "value": value, "digits": 3 if kind in ("Index", "Version") else 1, "folder": kind == "Folder"}


def empty_setup(sid):
    return {
        "id": sid,
        "color": "#ffffff",
        "render": True,
        "scenename": "",
        "camera": {"enabled": True, "handle": None, "name": "", "locked": False},
        "resolution": {"enabled": True, "width": DEFAULT_WIDTH, "height": DEFAULT_HEIGHT, "ratio": DEFAULT_RATIO, "locked": False},
        "sun": {"enabled": False, "handle": None, "name": "", "extra": []},
        "dome": {"enabled": False, "handle": None, "name": ""},
        "environment": {"enabled": False, "cls": "", "name": "", "extra": [], "mix": True, "on": True, "amount": 1.0},
        "frames": {"enabled": False, "kind": 0, "single": 0, "start": 0, "end": 100, "nth": 1, "list": DEFAULT_FRAME_LIST},
        "layers": {"enabled": False, "set": []},
        "objects": {"enabled": False, "set": []},
        "lights": {"enabled": False, "set": []},
        "xref": {"enabled": False, "set": []},
        "output": {"enabled": False, "project_path": "", "preset": [new_token("Camera"), new_token("Extension")]},
        "render_custom": {"enabled": False},
        "background": {"enabled": False, "type": 0, "path": ""},
        "atmosphere": {"enabled": False, "set": []},
        "variants": {"enabled": False, "set": []},
        "elements": {"enabled": False, "set": []},
        "render_preset": {"enabled": False, "path": ""},
        "rs_override": {"enabled": False, "set": {}},
        "post": {"enabled": False, "conf": "", "lightmix": {}, "cats": {}},
        "scripts": {"enabled": False, "pre_render": {"enabled": False, "path": ""}, "post_render": {"enabled": False, "path": ""}},
        "snippet": {"enabled": False, "pre_setup": "", "post_setup": "", "pre_render": "", "post_render": ""},
        "thumbnail": "",
        "notes": "",
        "status": "#WIP",
        "props": {},
    }


def normalize(s, sid=None):
    """Fills in anything missing from a stored setup (older versions, hand edits)."""
    base = empty_setup(s.get("id", sid) if sid is None else sid)
    for k, v in base.items():
        if k not in s:
            s[k] = v
        elif isinstance(v, dict) and isinstance(s[k], dict):
            for k2, v2 in v.items():
                s[k].setdefault(k2, v2)
    return s


def layer_entry(name, visible=True, freeze=False, render=True, vcam=True):
    return {"name": name, "visible": visible, "freeze": freeze, "render": render, "vcam": vcam, "extra": {}}


def object_entry(handle, name, visible=True, renderable=True):
    return {"handle": handle, "name": name, "visible": visible, "renderable": renderable, "extra": {}}


def ratio(w, h):
    if not h:
        return DEFAULT_RATIO
    return round(w / float(h), 3)


def parse_frame_list(text):
    out = []
    for part in (text or "").split(","):
        p = part.strip()
        if not p:
            continue
        m = re.match(r"^(-?\d+)\s*-\s*(-?\d+)$", p)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a <= b and b - a < 100000:
                out.extend(range(a, b + 1))
        else:
            try:
                out.append(int(p))
            except ValueError:
                pass
    return out


def frame_count(s):
    f = s["frames"]
    if not f["enabled"]:
        return 1
    if f["kind"] == 1:
        return max(1, (f["end"] - f["start"]) // max(1, f["nth"]) + 1) if f["end"] >= f["start"] else 1
    if f["kind"] == 2:
        return len(parse_frame_list(f["list"]))
    return 1


def encode(setups, todo=None, extra=None):
    d = {"format": "openmanager", "version": 1, "setups": setups, "todo": todo or []}
    d.update(extra or {})
    return json.dumps(d, separators=(",", ":"))


def decode(text):
    """Stored text -> {"setups": [...], "todo": [...]}, or None when it isn't ours."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("setups"), list):
        return {"setups": [normalize(s) for s in data["setups"] if isinstance(s, dict)],
                "todo": [t for t in data.get("todo", []) if isinstance(t, dict)],
                "rs_default": data.get("rs_default") or {},
                "base": base_from_json(data.get("base"))}
    return None


# ---------------------------------------------------------------- output path

def _strip_ext(name):
    i = name.rfind(".")
    if i > 0 and "/" not in name[i:] and "\\" not in name[i:]:
        return name[:i]
    return name


def file_version(name):
    m = re.search(r"(\d+)$", _strip_ext(name))
    return m.group(1) if m else ""


def filtered_file_name(name):
    base = _strip_ext(name)
    ver = file_version(name)
    if not ver:
        return base
    return re.sub(r"^[^0-9A-Za-z]+|[^0-9A-Za-z]+$", "", base[: len(base) - len(ver)])


def format_date(fmt, now=None):
    now = now or datetime.datetime.now()
    f = (fmt or DEFAULT_DATE_FORMAT).replace("YYYY", "%Y").replace("YY", "%y").replace("MM", "%m").replace("DD", "%d")
    return now.strftime(f)


INVALID_NAME_CHARS = '<>:"/\\|?*'


def is_valid_file_path(p):
    return not any(c in p for c in '*?"<>|') and p.count(":") <= 1 and not any(ord(c) < 32 for c in p)


def clean_name(text, keep_folders=False):
    """A token value made safe for a Windows file name: characters Windows refuses (and control characters) become
    "_", and each folder level loses the trailing dots and spaces Windows would drop silently. With keep_folders,
    "/" and "\\" stay as folder separators (typed tokens may build sub-folders)."""
    out = []
    for c in text or "":
        if keep_folders and c in "/\\":
            out.append("/")
        elif ord(c) < 32 or c in INVALID_NAME_CHARS:
            out.append("_")
        else:
            out.append(c)
    parts = "".join(out).split("/")
    # a piece can sit in the middle of a name ("." between two tokens), so only finished folder levels are trimmed
    return "/".join([p.rstrip(" .") for p in parts[:-1]] + parts[-1:])


def build_path(out, file_name, camera_name, scene_name, index, pc_name, user_name):
    """Project path + the tokens in order. Returns (path, problem): problem is None when the path is a complete file
    path, else a short sentence saying why it isn't (a token with no value stops the build)."""
    project = (out.get("project_path") or "").strip()
    if not project:
        return "", "No project path"
    path = project.replace("\\", "/")
    if not path.endswith("/"):
        path += "/"
    ext = ""
    for t in out.get("preset", []):
        kind = t.get("kind")
        val = (t.get("value") or "").strip()
        digits = int(t.get("digits") or 1)
        if kind == "Camera":
            piece = clean_name(camera_name) or None
        elif kind == "Version":
            piece = clean_name(val).zfill(digits) if val else None
        elif kind == "Index":
            piece = str(index + 1).zfill(digits)
        elif kind == "FileName (Full)":
            piece = clean_name(_strip_ext(file_name)) or None
        elif kind == "FileName (Filtered)":
            piece = clean_name(filtered_file_name(file_name)) or None
        elif kind == "FileVersion":
            piece = file_version(file_name) or None
        elif kind == "PcName":
            piece = clean_name(pc_name) or None
        elif kind == "UserName":
            piece = clean_name(user_name) or None
        elif kind == "SceneName":
            piece = clean_name((scene_name or "").strip()) or None
        elif kind == "Extension":
            ext = clean_name(t.get("value") or "")
            piece = ext or None
        elif kind == "Date":
            piece = format_date(val)
        elif kind == "Date (Folder)":
            piece = format_date(val) + "/"
        else:  # Text, Folder
            piece = clean_name(val, keep_folders=True) or None
        if piece is None:
            why = {"Camera": "the setup has no camera", "FileName (Full)": "the scene is not saved yet",
                   "FileName (Filtered)": "the scene is not saved yet",
                   "FileVersion": "the scene name doesn't end in a number",
                   "SceneName": "the setup has no scene name"}.get(kind, "it is empty")
            return path, "The %s token has no value (%s)" % (kind, why)
        path += piece
        if t.get("folder") and not path.endswith("/"):
            path = path.rstrip(" .") + "/"  # Windows drops trailing dots and spaces of a folder name
    if not ext:
        return path, "No Extension token"
    stem = path[path.rfind("/") + 1:]
    if not stem.endswith(ext) or not stem[:-len(ext)].strip(" ."):
        return path, "The file name is empty"
    if not is_valid_file_path(path):
        return path, "The project path has characters Windows doesn't allow"
    return path, None


def final_path(out, file_name, camera_name, scene_name, index, pc_name, user_name):
    """Like build_path, but returns (path, valid)."""
    path, problem = build_path(out, file_name, camera_name, scene_name, index, pc_name, user_name)
    return path, problem is None


# ---------------------------------------------------------------- batch render checks

def check_jobs(jobs):
    """Checks every setup of a batch before anything renders. jobs: dicts with
        label           text shown for the setup
        output          True when its Render Output card is on
        path, problem   what build_path gave (output on)
        scene_output    the scene's own render output file, "" when the scene saves nothing (output off)
        camera_missing  name of a camera the setup uses that is not in the scene, else ""
    Returns one dict per job: {"path": file it would write or "", "errors": [...], "warnings": [...]}.
    A job with errors is skipped: it would render without saving, or render the wrong view."""
    out = []
    for j in jobs:
        errors, warnings = [], []
        if j.get("camera_missing"):
            errors.append("Camera '%s' is not in the scene" % j["camera_missing"])
        if j.get("output"):
            path = j.get("path") or ""
            if j.get("problem"):
                errors.append("Output path is not valid: %s" % j["problem"])
                path = ""
        else:
            path = j.get("scene_output") or ""
            if not path:
                errors.append("Nothing would be saved: the Render Output card is off and the scene has no output file")
        out.append({"path": path, "errors": errors, "warnings": warnings})
    seen = {}
    for i, r in enumerate(out):
        if r["errors"] or not r["path"]:
            continue
        key = r["path"].replace("\\", "/").lower()
        if key in seen:
            r["warnings"].append("Saves to the same file as %s, which it will overwrite" % jobs[seen[key]].get("label", "another setup"))
        else:
            seen[key] = i
    return out


# ---------------------------------------------------------------- base state
#
# A setup only sets what its cards control. So that nothing it changed stays behind when another setup is applied,
# the value each change replaces is kept (the "base") while a setup controls it, and put back when the next setup
# doesn't control it. The base only holds what the applied setup controls; anything else is the scene as it is.

def action_key(a):
    """What a change controls, so two changes of the same thing have the same key. None: not put back (the
    viewport camera and background are views, not scene settings; scripts and render presets can't be undone)."""
    k = a[0]
    if k == "rs":
        return ("rs", a[1])
    if k in ("node", "layer"):
        return (k, a[1], a[2])
    if k == "map":
        return ("map", a[1], a[2], a[3])
    if k in ("res", "time", "sun", "dome", "output", "posttone", "postlm"):
        return (k,)
    if k in ("env", "envmix", "envoff"):
        return ("env",)
    if k in ("xref", "atmos", "element"):
        return (k, a[1])
    return None


def base_step(base, acts, capture):
    """Applying `acts` with `base` ({key: change that puts the value back}) for the setup applied before.
    Returns (restore, new_base): restore puts back what the new setup doesn't control (run it before acts);
    new_base keeps the saved values the new setup still controls and captures, through capture(action) -> change or
    None, the current value of anything it starts to control."""
    wanted = {}
    for a in acts:
        k = action_key(a)
        if k is not None and k not in wanted:
            wanted[k] = a
    restore = [r for k, r in base.items() if k not in wanted and r is not None]
    new = {}
    for k, a in wanted.items():
        if k in base:
            new[k] = base[k]
        else:
            r = capture(a)
            if r is not None:
                new[k] = r
    return restore, new


def as_tuples(v):
    """JSON lists back into the tuples changes are made of."""
    if isinstance(v, list):
        return tuple(as_tuples(x) for x in v)
    return v


def base_to_json(base):
    return [[list(k), r] for k, r in base.items()]


def base_from_json(data):
    out = {}
    for item in data or []:
        try:
            k, r = item
            out[as_tuples(k)] = as_tuples(r)
        except (TypeError, ValueError):
            pass
    return out


def find_written(path, since):
    """Files a render wrote for this output path since `since` (time.time()): the file itself, or the numbered frames
    3ds Max makes from it for an animation (name0000.png...). Empty when nothing was written."""
    if not path:
        return []
    path = os.path.normpath(path)
    try:
        if os.path.isfile(path) and os.path.getmtime(path) >= since - 2:
            return [path]
    except OSError:
        pass
    folder = os.path.dirname(path)
    stem, ext = os.path.splitext(os.path.basename(path))
    found = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for n in names:
        s, e = os.path.splitext(n)
        if e.lower() == ext.lower() and s.lower().startswith(stem.lower()) and s[len(stem):].isdigit():
            full = os.path.join(folder, n)
            try:
                if os.path.getmtime(full) >= since - 2:
                    found.append(full)
            except OSError:
                pass
    return sorted(found)


# ---------------------------------------------------------------- HDRI folder

THUMB_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
_SEPARATORS = ("_", "-", ".", " ")


def find_thumbnail(stem, images):
    """The preview of an HDRI among {lower-case stem: file name}: the same name; or, as HDRI libraries name them, the
    name without what follows it (bell_park_dawn_16k.hdr -> bell_park_dawn.webp); or the name with something added
    (studio.hdr -> studio_preview.jpg, studio.hdr.jpg). The closest match wins."""
    low = stem.lower()
    if low in images:
        return images[low]
    best, best_len = None, -1
    for name in images:
        if low.startswith(name) and low[len(name):len(name) + 1] in _SEPARATORS and len(name) > best_len:
            best, best_len = name, len(name)
    if best is not None:
        return images[best]
    for name in sorted(images, key=len):
        if name.startswith(low) and name[len(low):len(low) + 1] in _SEPARATORS:
            return images[name]
    return None


def _pictures_in(names, prefix=""):
    images = {}
    # when a stem has several pictures, the first extension of the list wins
    for ext in reversed(THUMB_EXTENSIONS):
        for n in names:
            stem, e = os.path.splitext(n)
            if e.lower() == ext:
                images[stem.lower()] = os.path.join(prefix, n) if prefix else n
    return images


def read_image_thumbnails(folder):
    """This folder only: *.hdr and *.exr with the picture that goes with each one, looked for next to it first and
    then in its sub-folders (thumbs, previews, jpg...)."""
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    here = _pictures_in(names)
    below = {}
    for d in sorted(names):
        sub = os.path.join(folder, d)
        if d.startswith(".") or not os.path.isdir(sub):
            continue
        try:
            for k, v in _pictures_in(os.listdir(sub), d).items():
                below.setdefault(k, v)
        except OSError:
            pass
    for ext in (".exr", ".hdr"):
        for n in sorted(x for x in names if x.lower().endswith(ext)):
            raw = os.path.join(folder, n)
            if not os.path.isfile(raw):
                continue
            stem = n[: -len(ext)]
            t = find_thumbnail(stem, here) or find_thumbnail(stem, below)
            out.append({"raw": raw, "name": n, "thumb": os.path.join(folder, t) if t else None})
    return out


def preview_cache_name(raw, size=0, mtime=0.0):
    """File name of the picture made from an HDRI that has none: changes when the HDRI changes."""
    import hashlib
    key = "%s|%d|%d" % (os.path.normcase(os.path.abspath(raw)), int(size), int(mtime))
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(os.path.basename(raw))[0])[:40]
    return "%s_%s.jpg" % (stem, hashlib.md5(key.encode("utf-8")).hexdigest()[:10])


# ---------------------------------------------------------------- setups saved by Pulze Scene Manager

def _b(v, d=None):
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in ("true", "false"):
        return v.lower() == "true"
    return d


def _n(v, d):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _h(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _props_into(card, lst, out):
    for p in lst or []:
        name, cls = p.get("name"), p.get("v_class")
        if not name or not cls or p.get("value") is None:
            continue
        v = p["value"]
        if isinstance(v, str):
            b = _b(v)
            if b is not None:
                v = b
            else:
                try:
                    v = float(v)
                except ValueError:
                    pass
        if name == "progressive_timeLimit":
            v = from_max(name, _n(v, 0.0))
        out["%d|%s|%s" % (card, cls, name)] = v


def import_pulze(data, first_id):
    """Reads Pulze's SceneManager_Dat (base64 JSON) into our setups. The original data is left as it is."""
    try:
        raw = base64.b64decode(data + "=" * (-len(data) % 4))
        lst = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(lst, list):
        return None
    out = []
    for i, v in enumerate(lst):
        g = lambda k: v.get(k) or {}
        s = empty_setup(first_id + i)
        s["render"] = _b(g("render").get("enabled"), True)
        c = v.get("color")
        if isinstance(c, str) and re.match(r"^#[0-9a-fA-F]{6}$", c):
            s["color"] = c.lower()
        s["scenename"] = g("scenename").get("text") or ""
        s["status"] = v.get("status") or "#WIP"
        cam = g("camera")
        s["camera"].update(enabled=_b(cam.get("enabled"), True), handle=_h(cam.get("handle")), locked=_b(cam.get("locked"), False))
        _props_into(1, cam.get("props"), s["props"])
        r = g("resolution")
        s["resolution"].update(enabled=_b(r.get("enabled"), True), width=int(_n(r.get("width"), DEFAULT_WIDTH)),
                               height=int(_n(r.get("height"), DEFAULT_HEIGHT)), ratio=_n(r.get("ratio"), DEFAULT_RATIO),
                               locked=_b(r.get("locked"), False))
        for key, card in (("sun", 3), ("dome", 4)):
            x = g(key)
            s[key].update(enabled=_b(x.get("enabled"), False), handle=_h(x.get("handle")))
            _props_into(card, x.get("props"), s["props"])
        e = g("environment")
        mat = e.get("mat") or {}
        s["environment"].update(enabled=_b(e.get("enabled"), False), cls=mat.get("class") or "", name=mat.get("name") or "")
        _props_into(6, e.get("props"), s["props"])
        f = g("frames")
        s["frames"].update(enabled=_b(f.get("enabled"), False), kind=int(_n(f.get("type"), 0)), single=int(_n(f.get("single"), 0)),
                           start=int(_n(f.get("start"), 0)), end=int(_n(f.get("end"), 100)), nth=int(_n(f.get("nth"), 1)))
        if isinstance(f.get("list"), str):
            s["frames"]["list"] = f["list"]
        s["layers"]["enabled"] = _b(g("layers").get("enabled"), False)
        for l in g("layers").get("set") or []:
            ent = layer_entry(l.get("handle") or l.get("name") or "")
            for p in l.get("props") or []:
                b = _b(p.get("value"))
                n = p.get("name")
                if b is None or n == "name":
                    continue
                key = {"on": "visible", "isfrozen": "freeze", "renderable": "render", "primaryVisibility": "vcam"}.get(n)
                if key:
                    ent[key] = b
                else:
                    ent["extra"][n] = b
            s["layers"]["set"].append(ent)
        s["objects"]["enabled"] = _b(g("objects").get("enabled"), False)
        for o in g("objects").get("set") or []:
            h = _h(o.get("handle"))
            if h is None:
                continue
            ent = object_entry(h, o.get("name") or "")
            for p in o.get("props") or []:
                b = _b(p.get("value"))
                n = p.get("name")
                if b is None or n == "name":
                    continue
                if n == "isNodeHidden":
                    ent["visible"] = not b
                elif n == "renderable":
                    ent["renderable"] = b
                else:
                    ent["extra"][n] = b
            s["objects"]["set"].append(ent)
        s["lights"]["enabled"] = _b(g("lights").get("enabled"), False)
        for l in g("lights").get("set") or []:
            h = _h(l.get("handle"))
            if h is None:
                continue
            s["lights"]["set"].append(h)
            for p in l.get("props") or []:
                if p.get("name") and p.get("name") != "name" and p.get("value") is not None:
                    s["props"]["26|%d|%s" % (h, p["name"])] = p["value"]
        rc = g("renderCustom")
        s["render_custom"]["enabled"] = _b(rc.get("enabled"), False)
        _props_into(25, rc.get("props"), s["props"])
        x = g("xrefScene")
        s["xref"]["enabled"] = _b(x.get("enabled"), False)
        for it in x.get("set") or []:
            on = True
            for p in it.get("props") or []:
                if p.get("name") == "enabled":
                    on = _b(p.get("value"), True)
            if on and it.get("name"):
                s["xref"]["set"].append(re.split(r"[\\/]", it["name"])[-1])
        o = g("output_Common")
        s["output"]["enabled"] = _b(o.get("enabled"), False)
        s["output"]["project_path"] = o.get("projectPath") or ""
        toks = []
        for t in o.get("preset") or []:
            tok = new_token(t.get("type") or "Text")
            if isinstance(t.get("value"), str):
                tok["value"] = t["value"]
            elif isinstance(t.get("value"), (int, float)):
                tok["value"] = str(int(t["value"]))
            if isinstance(t.get("settings"), int):
                tok["digits"] = t["settings"]
            tok["folder"] = bool(t.get("folder"))
            toks.append(tok)
        if toks:
            s["output"]["preset"] = toks
        s["notes"] = g("notes").get("text") or ""
        out.append(s)
    return out


def clone(s, new_id):
    c = copy.deepcopy(s)
    c["id"] = new_id
    return c
