"""Builds dist/OpenManager.mzp: draws the icons, then zips the package.

    python mzp/tools/build.py

Pure Python, nothing to install.
"""
import math
import os
import struct
import zipfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "package")
DIST = os.path.join(ROOT, "dist")
ICON_NAME = "OpenManager"
SIZES = (16, 24, 30, 32, 36, 48)


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

def build_mzp():
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


if __name__ == "__main__":
    build_icons()
    t = build_mzp()
    print("built %s (%d KB)" % (t, os.path.getsize(t) // 1024))
