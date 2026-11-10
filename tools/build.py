"""Builds the two release outputs: draws the icons, then writes

- dist/OpenManager.mzp     the package dropped onto 3ds Max (install.ms copies it into the user's profile)
- dist/OpenManager.bundle  the Autodesk ApplicationPlugins bundle the Open3D launcher installs

    python -I tools/build.py

Pure Python, nothing to install.
"""
import math
import os
import re
import shutil
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "package")
BUNDLE_SRC = os.path.join(ROOT, "bundle")
DIST = os.path.join(ROOT, "dist")
ICON_NAME = "OpenManager"
SIZES = (16, 24, 30, 32, 36, 48)

# the bundle's identity for 3ds Max: never change these two
PRODUCT_CODE = "{6A36A415-E9A4-4DC7-9B99-1FF6EDB2C661}"
UPGRADE_CODE = "{757AF74F-AD01-4AEE-A3B6-43D92E4B9053}"
SERIES_MIN = "2025"
SERIES_MAX = "2099"  # 3ds Max 2027 silently ignores a package without SeriesMax: 2099 = no cap


# ---------------------------------------------------------------- icon: a stack of three setup cards, in greys

# cards front to back (x0, y0, x1, y1 in 0..1), corner radius and the gap that separates each card from the one before
CARDS = ((0.08, 0.38, 0.68, 0.92), (0.20, 0.23, 0.80, 0.77), (0.32, 0.08, 0.92, 0.62))
CARD_R = 0.08
CARD_GAP = 0.055


def _in_round_rect(x, y, x0, y0, x1, y1, r):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _in_card(x, y, c, grow=0.0):
    return _in_round_rect(x, y, c[0] - grow, c[1] - grow, c[2] + grow, c[3] + grow, CARD_R + grow)


def _in_logo(x, y):
    """Unit coordinates (0..1): the front card whole, each card behind it only where it shows past the gap."""
    if _in_card(x, y, CARDS[0]):
        return True
    for i in (1, 2):
        if _in_card(x, y, CARDS[i]) and not _in_card(x, y, CARDS[i - 1], CARD_GAP):
            return True
    return False


# 3ds Max picks the icon set of its theme: silver on the dark interface, graphite on the light one
THEMES = {"Dark": ((0xFF, 0xFF, 0xFF), (0xA4, 0xA4, 0xA4)), "Light": ((0x5C, 0x5C, 0x5C), (0x14, 0x14, 0x14))}


def draw_icon(size, theme="Dark", ss=6):
    c0, c1 = THEMES[theme]
    px = []
    for j in range(size):
        row = []
        for i in range(size):
            cov = 0
            for sj in range(ss):
                for si in range(ss):
                    if _in_logo((i + (si + 0.5) / ss) / size, (j + (sj + 0.5) / ss) / size):
                        cov += 1
            t = min(1.0, max(0.0, (i + j) / (2.0 * size)))
            row.append(tuple(int(round(c0[k] + (c1[k] - c0[k]) * t)) for k in range(3)) + (int(round(cov * 255.0 / (ss * ss))),))
        px.append(row)
    return px


def preview(size=128, pad=16):
    """Both versions side by side on the background they are meant for."""
    px = []
    n = size + pad * 2
    dark, light = draw_icon(size, "Dark", 3), draw_icon(size, "Light", 3)
    for j in range(n):
        row = []
        for side, bg, ic in ((0, (0x2B, 0x2B, 0x2B), dark), (1, (0xF0, 0xF0, 0xF0), light)):
            for i in range(n):
                c = bg
                if pad <= i < pad + size and pad <= j < pad + size:
                    p = ic[j - pad][i - pad]
                    a = p[3] / 255.0
                    c = tuple(int(round(bg[k] * (1 - a) + p[k] * a)) for k in range(3))
                row.append(c + (255,))
        px.append(row)
    return px


def write_png(path, px):
    h, w = len(px), len(px[0])
    raw = b"".join(b"\x00" + bytes(c for p in row for c in p) for row in px)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def build_icons():
    out = os.path.join(PKG, "icons")
    for f in os.listdir(out) if os.path.isdir(out) else []:  # older builds had one set
        if f.endswith(".png"):
            os.remove(os.path.join(out, f))
    for theme in THEMES:
        folder = os.path.join(out, theme)
        os.makedirs(folder, exist_ok=True)
        for s in SIZES:
            write_png(os.path.join(folder, "%s_%d.png" % (ICON_NAME, s)), draw_icon(s, theme))
    write_png(os.path.join(ROOT, "icon_preview_128.png"), preview())
    return out


# ---------------------------------------------------------------- package

def check_mzp_run():
    """3ds Max refuses the whole package, without a word to the user, when mzp.run doesn't compile. A "version" line
    must be a plain number (0.2, never 0.2.0); the app's version lives in openmanager/window.py instead."""
    for n, line in enumerate(open(os.path.join(PKG, "mzp.run"), encoding="utf-8-sig"), 1):
        parts = line.split(None, 1)
        if parts and parts[0].lower() == "version":
            try:
                float(parts[1])
            except (IndexError, ValueError):
                raise SystemExit("mzp.run line %d: 'version' must be a plain number, got: %s" % (n, line.strip()))


def build_mzp():
    check_mzp_run()
    os.makedirs(DIST, exist_ok=True)
    target = os.path.join(DIST, "OpenManager.mzp")
    if os.path.exists(target):
        os.remove(target)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(PKG):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith((".pyc", ".pyo")):
                    continue
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, PKG).replace(os.sep, "/"))
    return target


# ---------------------------------------------------------------- bundle

def read_version():
    """VERSION in openmanager/window.py; the README status line must say the same."""
    with open(os.path.join(PKG, "OpenManager", "openmanager", "window.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSION = "(\d+\.\d+\.\d+)"', f.read(), re.M)
    if not m:
        raise SystemExit('openmanager/window.py: no VERSION = "X.Y.Z" line')
    version = m.group(1)
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        if "(v%s)" % version not in f.read():
            raise SystemExit("README.md: the status line doesn't say v%s (VERSION in window.py)" % version)
    return version


# Component types as other bundles installed with 3ds Max 2027 use them (macroscripts, dark/light icon paths) and as
# OpenTools uses and has verified (post-start-up scripts).
COMPONENTS = (
    ("macroscripts parts", "./Contents/macroscripts/OpenManager.mcr"),
    ("dark icon paths parts", "./Contents/icons/Dark"),
    ("light icon paths parts", "./Contents/icons/Light"),
    ("post-start-up scripts parts", "./Contents/scripts/OpenManager_bundle.ms"),
)


def package_contents(version):
    req = '<RuntimeRequirements OS="Win64" Platform="3ds Max" SeriesMin="%s" SeriesMax="%s" />' % (SERIES_MIN, SERIES_MAX)
    parts = "".join(
        '    <Components Description="%s">\n        %s\n'
        '        <ComponentEntry AppName="OpenManager" Version="%s" ModuleName="%s" />\n    </Components>\n'
        % (desc, req, version, module) for desc, module in COMPONENTS)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<ApplicationPackage\n'
            '    SchemaVersion="1.0"\n'
            '    AutodeskProduct="3ds Max"\n'
            '    ProductType="Application"\n'
            '    Name="OpenManager"\n'
            '    Description="Open-source scene setups and batch render manager for 3ds Max."\n'
            '    AppVersion="%s"\n'
            '    ProductCode="%s"\n'
            '    UpgradeCode="%s">\n'
            '    <CompanyDetails Name="OpenManager contributors" />\n'
            '    %s\n%s'
            '</ApplicationPackage>\n') % (version, PRODUCT_CODE, UPGRADE_CODE, req, parts)


def check_bundle(target, version):
    """Refuses a bundle 3ds Max would load wrongly or not at all: versions that differ, a missing SeriesMax, a part
    that points nowhere."""
    root = ET.parse(os.path.join(target, "PackageContents.xml")).getroot()
    problems = []
    if root.get("AppVersion") != version:
        problems.append("AppVersion %s != VERSION %s" % (root.get("AppVersion"), version))
    for req in root.iter("RuntimeRequirements"):
        if not req.get("SeriesMin") or not req.get("SeriesMax"):
            problems.append("RuntimeRequirements without SeriesMin/SeriesMax")
    for entry in root.iter("ComponentEntry"):
        if entry.get("Version") != version:
            problems.append("%s: Version %s != %s" % (entry.get("ModuleName"), entry.get("Version"), version))
        if not os.path.exists(os.path.join(target, entry.get("ModuleName"))):
            problems.append("%s: missing" % entry.get("ModuleName"))
    if problems:
        raise SystemExit("OpenManager.bundle refused:\n  " + "\n  ".join(problems))


def build_bundle(version, dist=DIST, icons=None):
    icons = icons or os.path.join(PKG, "icons")
    target = os.path.join(dist, "OpenManager.bundle")
    if os.path.exists(target):
        # moved aside first: on the NAS a deleted folder lingers for a moment and the new one can't be made in its place
        old = "%s.old-%d" % (target, os.getpid())
        os.rename(target, old)
        shutil.rmtree(old, ignore_errors=True)
    for stale in [f for f in os.listdir(dist) if f.startswith("OpenManager.bundle.old-")] if os.path.isdir(dist) else []:
        shutil.rmtree(os.path.join(dist, stale), ignore_errors=True)
    contents = os.path.join(target, "Contents")
    skip = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    shutil.copytree(os.path.join(PKG, "OpenManager"), os.path.join(contents, "OpenManager"), ignore=skip)
    for theme in THEMES:
        shutil.copytree(os.path.join(icons, theme), os.path.join(contents, "icons", theme))
    os.makedirs(os.path.join(contents, "macroscripts"))
    shutil.copy2(os.path.join(PKG, "OpenManager.mcr"), os.path.join(contents, "macroscripts"))
    os.makedirs(os.path.join(contents, "scripts"))
    shutil.copy2(os.path.join(BUNDLE_SRC, "OpenManager_bundle.ms"), os.path.join(contents, "scripts"))
    with open(os.path.join(target, "PackageContents.xml"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(package_contents(version))
    check_bundle(target, version)
    return target


if __name__ == "__main__":
    v = read_version()
    build_icons()
    t = build_mzp()
    print("built %s (%d KB)" % (t, os.path.getsize(t) // 1024))
    print("built %s (%s)" % (build_bundle(v), v))
