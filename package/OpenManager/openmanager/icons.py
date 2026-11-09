"""Small icons drawn at run time: Windows' own symbol font plus a few hand-drawn shapes.
Nothing to ship, sharp at any DPI."""
from PySide6 import QtCore, QtGui

_FONT = None
_CACHE = {}
_ORIGIN = {}  # cacheKey of a glyph icon -> (name, color, size): lets a theme change redraw icons that already exist

GLYPH = {
    "add": "", "delete": "", "copy": "", "paste": "", "camera": "",
    "refresh": "", "lock": "", "unlock": "", "color": "", "import": "",
    "export": "", "list": "", "stop": "", "sun": "", "globe": "",
    "folder": "", "eye": "", "hide": "", "edit": "", "more": "",
    "close": "", "filter": "", "photo": "", "clock": "", "layers": "",
    "link": "", "bulb": "", "save": "", "grip": "", "menu": "",
    "pick": "", "up": "", "down": "", "expand": "", "shrink": "",
    "fetch": "", "cube": "", "settings": "", "note": "", "check": "",
    "checklist": "", "cards": "", "cut": "", "select": "", "dup": "",
    "transfer": "", "text": "", "resolution": "", "image": "",
    "dome": "", "mountain": "", "wind": "", "swatch": "", "sliders": "",
    "preset": "", "elements": "", "post": "", "codefile": "", "code": "",
    "view": "", "sync": "", "bake": "", "play": "", "pin": "",
    "wand": "", "magic": "", "gear": "", "folderopen": "", "minus": "",
}


def _font(px):
    f = QtGui.QFont("Segoe Fluent Icons")
    if not QtGui.QFontInfo(f).exactMatch():
        f = QtGui.QFont("Segoe MDL2 Assets")
    f.setPixelSize(px)
    return f


def glyph(name, color, size=16):
    key = ("g", name, QtGui.QColor(color).rgba(), size)
    if key in _CACHE:
        return _CACHE[key]
    icon = QtGui.QIcon()
    for scale in (1, 2):
        pm = QtGui.QPixmap(size * scale, size * scale)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        p.setPen(QtGui.QColor(color))
        p.setFont(_font(int(size * scale * 0.8)))
        p.drawText(pm.rect(), QtCore.Qt.AlignCenter, GLYPH.get(name, name))
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    _CACHE[key] = icon
    _ORIGIN[icon.cacheKey()] = (name, QtGui.QColor(color).rgba(), size)
    return icon


def recolor(icon, old_color, new_color):
    """The same glyph in the new colour, or None when this icon isn't a glyph drawn in old_color."""
    o = _ORIGIN.get(icon.cacheKey())
    if o is None or o[1] != QtGui.QColor(old_color).rgba():
        return None
    return glyph(o[0], new_color, o[2])


def teapot_path(r):
    """A teapot silhouette inside rect r (body, lid with knob, curved spout, ring handle)."""
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    P = lambda fx, fy: QtCore.QPointF(x + w * fx, y + h * fy)
    path = QtGui.QPainterPath()
    path.addEllipse(QtCore.QRectF(P(0.20, 0.36), P(0.80, 0.88)))
    lid = QtGui.QPainterPath()
    lid.addEllipse(QtCore.QRectF(P(0.33, 0.28), P(0.67, 0.44)))
    path = path.united(lid)
    knob = QtGui.QPainterPath()
    knob.addEllipse(P(0.50, 0.22), w * 0.07, h * 0.07)
    path = path.united(knob)
    spout = QtGui.QPainterPath()
    spout.moveTo(P(0.27, 0.52))
    spout.quadTo(P(0.12, 0.54), P(0.02, 0.30))
    spout.lineTo(P(0.12, 0.30))
    spout.quadTo(P(0.17, 0.46), P(0.30, 0.74))
    spout.closeSubpath()
    path = path.united(spout)
    handle = QtGui.QPainterPath()
    handle.addEllipse(QtCore.QRectF(P(0.68, 0.42), P(0.98, 0.76)))
    hole = QtGui.QPainterPath()
    hole.addEllipse(QtCore.QRectF(P(0.75, 0.50), P(0.91, 0.68)))
    return path.united(handle.subtracted(hole)).simplified()


def teapot(color, filled=True, size=18):
    key = ("t", QtGui.QColor(color).rgba(), filled, size)
    if key in _CACHE:
        return _CACHE[key]
    icon = QtGui.QIcon()
    for scale in (1, 2):
        pm = QtGui.QPixmap(size * scale, size * scale)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        path = teapot_path(QtCore.QRectF(0.5, 0.5, size * scale - 1, size * scale - 1))
        c = QtGui.QColor(color)
        if filled:
            p.fillPath(path, c)
        else:
            p.setPen(QtGui.QPen(c, 1.1 * scale))
            p.drawPath(path)
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    _CACHE[key] = icon
    return icon


def logo_path(r):
    """The logo inside rect r: a stack of three setup cards (same shape as the toolbar icon drawn by tools/build.py)."""
    cards = ((0.08, 0.38, 0.68, 0.92), (0.20, 0.23, 0.80, 0.77), (0.32, 0.08, 0.92, 0.62))
    rad, gap = 0.08, 0.055
    x, y, w, h = r.x(), r.y(), r.width(), r.height()

    def card(c, grow=0.0):
        p = QtGui.QPainterPath()
        p.addRoundedRect(QtCore.QRectF(x + w * (c[0] - grow), y + h * (c[1] - grow), w * (c[2] - c[0] + 2 * grow),
                                       h * (c[3] - c[1] + 2 * grow)), w * (rad + grow), h * (rad + grow))
        return p

    path = card(cards[0])
    for i in (1, 2):
        path = path.united(card(cards[i]).subtracted(card(cards[i - 1], gap)))
    return path


def app_icon(dark=True):
    """The logo: a stack of setup cards in greys. Silver on dark interfaces, graphite on light ones."""
    key = ("app", bool(dark))
    if key in _CACHE:
        return _CACHE[key]
    a, b = ("#ffffff", "#a4a4a4") if dark else ("#5c5c5c", "#141414")
    icon = QtGui.QIcon()
    for size in (16, 24, 32, 48, 64):
        pm = QtGui.QPixmap(size, size)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        g = QtGui.QLinearGradient(0, 0, size, size)
        g.setColorAt(0, QtGui.QColor(a))
        g.setColorAt(1, QtGui.QColor(b))
        p.fillPath(logo_path(QtCore.QRectF(0, 0, size, size)), QtGui.QBrush(g))
        p.end()
        icon.addPixmap(pm)
    _CACHE[key] = icon
    return icon
