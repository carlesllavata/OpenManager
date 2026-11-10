# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable pieces of the window: on/off switch, card frame, number row, and the grid board."""
import copy

from PySide6 import QtCore, QtGui, QtWidgets

from . import grid, icons, model

TINTS = {
    "space": "#9ca7d5", "yellow": "#ffba0a", "blue": "#48cae4", "lightgreen": "#3fdfac",
    "salmon": "#ff925b", "eton": "#77bfb2", "purple": "#6960af", "noted": "#ffd66d", "baby": "#89daff",
}
PRIMARY = "#289ad3"
CARD_GLYPH = {
    0: "list", 1: "camera", 2: "photo", 7: "clock", 15: "edit", 3: "sun", 26: "bulb", 28: "image", 6: "globe",
    4: "dome", 8: "mountain", 20: "wind", 14: "layers", 23: "cube", 16: "link", 30: "swatch", 9: "save",
    25: "settings", 19: "sliders", 18: "preset", 21: "elements", 29: "post", 17: "codefile", 22: "code",
    31: "eye", 13: "checklist", 12: "note",
}
HEADER_ICON = 15


PALETTE_OVERRIDE = None  # set by the window when the theme is forced to light or dark


def pal():
    return PALETTE_OVERRIDE if PALETTE_OVERRIDE is not None else QtWidgets.QApplication.palette()


def is_dark():
    return pal().color(QtGui.QPalette.Window).lightness() < 128


def blend(a, b, t):
    a, b = QtGui.QColor(a), QtGui.QColor(b)
    return QtGui.QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                        int(a.blue() + (b.blue() - a.blue()) * t))


def text_color(widget=None):
    p = widget.palette() if widget is not None else pal()
    return p.color(QtGui.QPalette.WindowText)


def icon(name, size=16, color=None):
    return icons.glyph(name, color or text_color(), size)


def tool(name, tip, parent=None, size=16, checkable=False, slot=None):
    b = QtWidgets.QToolButton(parent)
    b.setIcon(icon(name, size))
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setCheckable(checkable)
    b.setIconSize(QtCore.QSize(size, size))
    b.setFocusPolicy(QtCore.Qt.NoFocus)
    if slot:
        b.clicked.connect(slot)
    return b


def menu_tool(name, tip, size=16):
    b = tool(name, tip, size=size)
    b.setPopupMode(QtWidgets.QToolButton.InstantPopup)
    b.setStyleSheet("QToolButton::menu-indicator{image:none;width:0}")
    m = QtWidgets.QMenu(b)
    b.setMenu(m)
    return b, m


class Combo(QtWidgets.QComboBox):
    """A drop-down only changes when it is clicked: the wheel goes on to scroll the card under it.
    before_popup: called right before the list opens (to fill it with what the scene has now)."""

    def __init__(self, *a, **k):
        super(Combo, self).__init__(*a, **k)
        self.before_popup = None

    def wheelEvent(self, e):
        e.ignore()

    def showPopup(self):
        if self.before_popup is not None:
            try:
                self.before_popup()
            except Exception:
                import traceback
                traceback.print_exc()
        super(Combo, self).showPopup()


parse_number = model.parse_number


class Spin(QtWidgets.QSpinBox):
    def wheelEvent(self, e):
        e.ignore()


class DoubleSpin(QtWidgets.QDoubleSpinBox):
    """Takes ".5" (or "0,5") as 0.5; a number out of range goes to the nearest end instead of being refused."""

    def __init__(self, *a, **k):
        super(DoubleSpin, self).__init__(*a, **k)
        self.setLocale(QtCore.QLocale.c())

    def wheelEvent(self, e):
        e.ignore()

    def _strip(self, text):
        t = text
        if self.prefix() and t.startswith(self.prefix()):
            t = t[len(self.prefix()):]
        if self.suffix() and t.endswith(self.suffix()):
            t = t[: -len(self.suffix())]
        return t

    def validate(self, text, pos):
        t = self._strip(text).strip().replace(",", ".")
        allowed = set("0123456789.-+ ")
        if not set(t) <= allowed or t.count(".") > 1:
            return QtGui.QValidator.Invalid, text, pos
        if parse_number(t) is None:
            return QtGui.QValidator.Intermediate, text, pos
        return QtGui.QValidator.Acceptable, text, pos

    def valueFromText(self, text):
        v = parse_number(self._strip(text))
        if v is None:
            return self.value()
        return min(max(v, self.minimum()), self.maximum())

    def fixup(self, text):
        v = parse_number(self._strip(text))
        return self.textFromValue(self.value() if v is None else min(max(v, self.minimum()), self.maximum()))


class Slider(QtWidgets.QSlider):
    def wheelEvent(self, e):
        e.ignore()


class TabBar(QtWidgets.QTabBar):
    def wheelEvent(self, e):
        e.ignore()


class FlowLayout(QtWidgets.QLayout):
    """Lays its items in a line and goes on to the next line when they don't fit (several small values in one row)."""

    def __init__(self, parent=None, hspacing=6, vspacing=3):
        super(FlowLayout, self).__init__(parent)
        self._items = []
        self._h = hspacing
        self._v = vspacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return QtCore.Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._place(QtCore.QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super(FlowLayout, self).setGeometry(r)
        self._place(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QtCore.QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _place(self, rect, test):
        x, y, line = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x = rect.x()
                y += line + self._v
                line = 0
            if not test:
                it.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x += hint.width() + self._h
            line = max(line, hint.height())
        return y + line - rect.y()


class Blocker(object):
    """with Blocker(w1, w2): ... — no signals while filling widgets from data."""

    def __init__(self, *widgets):
        self.widgets = [w for w in widgets if w is not None]

    def __enter__(self):
        self.old = [w.blockSignals(True) for w in self.widgets]

    def __exit__(self, *a):
        for w, o in zip(self.widgets, self.old):
            w.blockSignals(o)


class Toggle(QtWidgets.QAbstractButton):
    """The small on/off pill of a card header."""

    def __init__(self, parent=None):
        super(Toggle, self).__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedSize(34, 18)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = self.isChecked()
        track = QtGui.QColor(PRIMARY) if on else blend(pal().color(QtGui.QPalette.Base), text_color(), 0.35)
        if not self.isEnabled():
            track = blend(track, pal().color(QtGui.QPalette.Window), 0.6)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.right() - d - 2 if on else r.left() + 2
        p.setBrush(QtGui.QColor("#ffffff"))
        p.drawEllipse(QtCore.QRectF(x, r.top() + 2, d, d))


class NumberRow(QtWidgets.QWidget):
    """Slider + number box for one setting; `changed(value)` when the person moves either."""
    changed = QtCore.Signal(object)

    def __init__(self, minimum, maximum, step=None, integer=False, parent=None):
        super(NumberRow, self).__init__(parent)
        self.integer = integer
        self.lo, self.hi = float(minimum), float(maximum)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.slider = Slider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setFocusPolicy(QtCore.Qt.NoFocus)
        if integer:
            self.spin = Spin()
            self.spin.setRange(int(self.lo), int(self.hi))
        else:
            self.spin = DoubleSpin()
            self.spin.setRange(self.lo, self.hi)
            st = step or (0.01 if self.hi - self.lo <= 10 else 0.1)
            self.spin.setSingleStep(st)
            self.spin.setDecimals(3 if st < 0.01 else 2 if st < 1 else 1)
        self.spin.setKeyboardTracking(False)
        self.spin.setFixedWidth(78)
        self.spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def value(self):
        return self.spin.value()

    def set_value(self, v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = self.lo
        with Blocker(self.spin, self.slider):
            self.spin.setValue(int(round(v)) if self.integer else v)
            span = (self.hi - self.lo) or 1.0
            self.slider.setValue(int(round((min(max(v, self.lo), self.hi) - self.lo) / span * 1000)))

    def _from_slider(self, pos):
        v = self.lo + (self.hi - self.lo) * pos / 1000.0
        with Blocker(self.spin):
            self.spin.setValue(int(round(v)) if self.integer else v)
        self.changed.emit(self.value())

    def _from_spin(self, v):
        self.set_value(v)
        self.changed.emit(self.value())


class ColorButton(QtWidgets.QToolButton):
    changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(ColorButton, self).__init__(parent)
        self.color = "#000000"
        self.setFixedSize(46, 20)
        self.clicked.connect(self._pick)

    def set_color(self, c):
        self.color = QtGui.QColor(c).name() if c else "#000000"
        self.setStyleSheet("QToolButton{background:%s;border:1px solid #777;border-radius:3px}" % self.color)

    def _pick(self):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.color), self, "Color")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit(self.color)


class _Veil(QtWidgets.QWidget):
    """Drawn over the body of a card that is switched off: faded look, still clickable through."""

    def __init__(self, parent):
        super(_Veil, self).__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.color = QtGui.QColor(0, 0, 0, 0)
        self.hide()

    def paintEvent(self, e):
        QtGui.QPainter(self).fillRect(self.rect(), self.color)


class _Grip(QtWidgets.QWidget):
    """Bottom-right corner: drag to change the card's size in grid steps."""

    def __init__(self, card):
        super(_Grip, self).__init__(card)
        self.card = card
        self.setFixedSize(14, 14)
        self.setCursor(QtCore.Qt.SizeFDiagCursor)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = blend(pal().color(QtGui.QPalette.Window), text_color(), 0.45)
        p.setPen(QtGui.QPen(c, 1.2))
        for k in (4, 8, 12):
            p.drawLine(QtCore.QPointF(13, 13 - k + 1), QtCore.QPointF(13 - k + 1, 13))

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.LeftButton:
            self.card.board().resize_start(self.card, e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        self.card.board().resize_move(e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e):
        self.card.board().resize_end()


class Card(QtWidgets.QFrame):
    """A card: tinted title bar with its buttons, and a scrolling body the subclass fills."""
    CARD_ID = None
    NEEDS_SETUP = True

    def __init__(self, sm, parent=None):
        super(Card, self).__init__(parent)
        self.sm = sm
        cid = self.CARD_ID
        title, tint, switch, clip, props = model.CARDS[cid]
        self.setObjectName("omCard")
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = QtWidgets.QWidget()
        self.header.setObjectName("omCardHeader")
        self.header.setFixedHeight(30)
        self.header.setCursor(QtCore.Qt.OpenHandCursor)
        self.header.installEventFilter(self)
        hl = QtWidgets.QHBoxLayout(self.header)
        hl.setContentsMargins(8, 0, 4, 0)
        hl.setSpacing(2)
        self.title_icon = QtWidgets.QLabel()
        hl.addWidget(self.title_icon)
        hl.addSpacing(4)
        self.title = QtWidgets.QLabel(title)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        hl.addWidget(self.title)
        hl.addStretch(1)
        self.header_layout = hl
        self.header_tools_at = hl.count()  # subclasses insert their own header buttons here
        # on/off first, then copy / paste, Property Selector and close
        self.switch = None
        if switch:
            self.switch = Toggle()
            self.switch.setToolTip("Use this card in the setup")
            self.switch.toggled.connect(self._switched)
            hl.addWidget(self.switch)
            hl.addSpacing(2)
        if clip:
            b, m = menu_tool("copy", "Copy / Paste this card", size=HEADER_ICON)
            self.act_copy = m.addAction(icon("copy"), "Copy", self.copy)
            self.act_paste = m.addAction(icon("paste"), "Paste (active and selected setups)", self.paste)
            m.aboutToShow.connect(lambda: self.act_paste.setEnabled(self.sm.clipboard_has(cid)))
            hl.addWidget(b)
        if props:
            hl.addWidget(tool("menu", "Property Selector: choose the settings this card shows", size=HEADER_ICON,
                              slot=lambda: self.sm.open_property_selector(cid)))
        if cid != 0:
            hl.addWidget(tool("close", "Hide this card (bring it back from the side bar)", size=12,
                              slot=lambda: self.sm.set_card_visible(cid, False)))
        outer.addWidget(self.header)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.stack = QtWidgets.QStackedWidget()
        self.body = QtWidgets.QWidget()
        self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 6, 8, 8)
        self.body_layout.setSpacing(5)
        self.empty = QtWidgets.QLabel("Select a setup in the list")
        self.empty.setAlignment(QtCore.Qt.AlignCenter)
        self.empty.setEnabled(False)
        self.empty.setMinimumHeight(10)
        self.stack.addWidget(self.body)
        self.stack.addWidget(self.empty)
        self.scroll.setWidget(self.stack)
        outer.addWidget(self.scroll, 1)
        self.veil = _Veil(self)
        self.grip = _Grip(self)
        self.tint = tint
        self.restyle()
        self.build()
        # content sits at the top; a list / table / text box (if any) takes the spare height
        grow = None
        for i in range(self.body_layout.count()):
            w = self.body_layout.itemAt(i).widget()
            if isinstance(w, (QtWidgets.QAbstractScrollArea, QtWidgets.QTabWidget)) or getattr(w, "grows", False):
                grow = w
        if grow is not None:
            self.body_layout.setStretchFactor(grow, 1)
        else:
            self.body_layout.addStretch(1)

    def board(self):
        return self.parentWidget()

    # -- look
    def restyle(self):
        self.title_icon.setPixmap(icon(CARD_GLYPH.get(self.CARD_ID, "list"), HEADER_ICON).pixmap(HEADER_ICON, HEADER_ICON))
        base = pal().color(QtGui.QPalette.Window)
        card = blend(base, pal().color(QtGui.QPalette.Base), 0.6)
        colored = self.sm.settings.get("theme", {}).get("header", "colored") != "default"
        head = blend(card, TINTS.get(self.tint, "#808080"), 0.42 if (self.tint and colored) else 0.12)
        border = blend(base, text_color(), 0.15)
        self.setStyleSheet(
            "#omCard{background:%s;border:1px solid %s;border-radius:4px}"
            "#omCardHeader{background:%s;border-top-left-radius:4px;border-top-right-radius:4px}"
            % (card.name(), border.name(), head.name()))
        self.scroll.viewport().setAutoFillBackground(False)
        self.stack.setAutoFillBackground(False)
        v = QtGui.QColor(card)
        v.setAlpha(150)
        self.veil.color = v

    def resizeEvent(self, e):
        super(Card, self).resizeEvent(e)
        self.grip.move(self.width() - self.grip.width() - 1, self.height() - self.grip.height() - 1)
        self.grip.raise_()
        self.veil.setGeometry(self.scroll.geometry())

    # -- moving the card by its title bar
    def eventFilter(self, obj, ev):
        if obj is self.header:
            t = ev.type()
            if t == QtCore.QEvent.MouseButtonPress and ev.button() == QtCore.Qt.LeftButton:
                self._press = ev.globalPosition().toPoint()
                self._dragging = False
            elif t == QtCore.QEvent.MouseMove and getattr(self, "_press", None) is not None:
                gp = ev.globalPosition().toPoint()
                if not self._dragging and (gp - self._press).manhattanLength() > QtWidgets.QApplication.startDragDistance():
                    self._dragging = True
                    self.header.setCursor(QtCore.Qt.ClosedHandCursor)
                    self.board().drag_start(self, self._press)
                if self._dragging:
                    self.board().drag_move(gp)
            elif t == QtCore.QEvent.MouseButtonRelease:
                if getattr(self, "_dragging", False):
                    self.board().drag_end()
                self._press = None
                self._dragging = False
                self.header.setCursor(QtCore.Qt.OpenHandCursor)
        return super(Card, self).eventFilter(obj, ev)

    # -- data
    def setup(self):
        return self.sm.active()

    def _switched(self, on):
        s = self.setup()
        key = model.CARD_KEY.get(self.CARD_ID)
        if s is None or key is None:
            return
        for t in self.sm.targets():
            t[key]["enabled"] = bool(on)
        self.set_faded(not on)
        self.sm.last_sent = []
        self.sm.changed()

    def set_faded(self, faded):
        """A card that is switched off stays editable but is drawn faded, and the setup ignores it."""
        self.veil.setGeometry(self.scroll.geometry())
        self.veil.setVisible(bool(faded))
        if faded:
            self.veil.raise_()
            self.grip.raise_()

    def refresh(self):
        s = self.setup()
        if s is None and self.NEEDS_SETUP:
            self.stack.setCurrentWidget(self.empty)
            if self.switch:
                with Blocker(self.switch):
                    self.switch.setChecked(False)
                self.switch.setEnabled(False)
            self.set_faded(False)
            return
        self.stack.setCurrentWidget(self.body)
        key = model.CARD_KEY.get(self.CARD_ID)
        if self.switch and s is not None:
            self.switch.setEnabled(True)
            with Blocker(self.switch):
                self.switch.setChecked(bool(s[key]["enabled"]))
            self.set_faded(not s[key]["enabled"])
        self.body.setEnabled(not self.sm.locked())
        self.fill(s)

    def build(self):
        pass

    def fill(self, s):
        pass

    def copy(self):
        self.sm.copy_card(self.CARD_ID)

    def paste(self):
        self.sm.paste_card(self.CARD_ID)


class GridBoard(QtWidgets.QWidget):
    """Cards on a grid like the original: drag a card by its title anywhere, stretch it from its corner.
    12 columns when wide, 6 when narrow; rows of ~11 px; every card floats up so nothing overlaps."""
    layout_changed = QtCore.Signal()

    def __init__(self, sm, parent=None):
        super(GridBoard, self).__init__(parent)
        self.sm = sm
        self.cards = {}
        self.items = {}
        self.cols = 12
        self.drag = None
        self.sizing = None
        self.placeholder = QtWidgets.QFrame(self)
        self.placeholder.setStyleSheet("background:rgba(40,154,211,40);border:1px dashed %s;border-radius:4px" % PRIMARY)
        self.placeholder.hide()
        self.autoscroll = QtCore.QTimer(self)
        self.autoscroll.setInterval(30)
        self.autoscroll.timeout.connect(self._autoscroll)
        self._last_gp = None

    # -- metrics
    def s(self):
        return max(1.0, self.fontMetrics().height() / 16.0)

    def margin(self):
        return 10 * self.s()

    def unit(self):
        return 11 * self.s()

    def wanted_cols(self):
        return 12 if self.width() >= 1000 * self.s() else 6

    def colw(self):
        m = self.margin()
        return max(20.0, (self.width() - m * (self.cols + 1)) / self.cols)

    def rect(self, p):
        m, u, cw = self.margin(), self.unit(), self.colw()
        return QtCore.QRect(int(round(m + p[0] * (cw + m))), int(round(m + p[1] * u)),
                            int(round(p[2] * cw + (p[2] - 1) * m)), int(round(p[3] * u - m)))

    def min_size(self, cid):
        mw, mh = model.MIN_SIZE.get(cid, (3, 20))
        if cid not in model.MIN_SIZE:
            mh = 10
        return min(mw, self.cols), mh

    # -- which cards and where
    def stored(self, cols):
        return self.sm.settings.setdefault("layouts", {}).setdefault(str(cols), {})

    def default_place(self, cid, cols):
        src = model.LAYOUT_LG if cols >= 12 else model.LAYOUT_MD
        return list(src.get(cid, [0, 9999, 3, 20]))

    def set_cards(self, cards):
        """cards: {id: Card} that are shown now."""
        for cid, c in self.cards.items():
            if cid not in cards:
                c.hide()
        self.cards = dict(cards)
        for c in cards.values():
            if c.parentWidget() is not self:
                c.setParent(self)
        self.cols = self.wanted_cols()
        self._load_items()
        self.apply()

    def _load_items(self):
        st = self.stored(self.cols)
        items = {}
        new = []
        for cid in self.cards:
            p = st.get(str(cid))
            if p:
                items[cid] = list(p)
            else:
                new.append(cid)
        grid.fit_columns(items, self.cols, {c: self.min_size(c)[0] for c in items})
        for cid in new:
            grid.place_new(items, cid, self.default_place(cid, self.cols))
        grid.fit_columns(items, self.cols, {c: self.min_size(c)[0] for c in items})
        self.items = items
        self.store()

    def store(self):
        st = self.stored(self.cols)
        for cid, p in self.items.items():
            st[str(cid)] = list(p)

    def apply(self, skip=None):
        for cid, p in self.items.items():
            c = self.cards[cid]
            if cid != skip:
                c.setGeometry(self.rect(p))
            c.show()
        bottom = self.rect([0, grid.bottom(self.items), 1, 1]).top() + int(self.margin())
        self.setMinimumHeight(bottom)

    def resizeEvent(self, e):
        super(GridBoard, self).resizeEvent(e)
        if self.drag or self.sizing:
            return
        if self.wanted_cols() != self.cols:
            self.store()
            self.cols = self.wanted_cols()
            self._load_items()
        self.apply()

    def scroll_area(self):
        w = self.parentWidget()
        while w is not None and not isinstance(w, QtWidgets.QScrollArea):
            w = w.parentWidget()
        return w

    def _autoscroll(self):
        sa = self.scroll_area()
        if sa is None or self._last_gp is None:
            return
        vp = sa.viewport()
        y = vp.mapFromGlobal(self._last_gp).y()
        bar = sa.verticalScrollBar()
        step = 0
        if y < 30:
            step = -18
        elif y > vp.height() - 30:
            step = 18
        if step:
            if step > 0:
                self.setMinimumHeight(max(self.minimumHeight(), bar.value() + vp.height() + 60))
            bar.setValue(bar.value() + step)
            if self.drag:
                self.drag_move(self._last_gp)
            elif self.sizing:
                self.resize_move(self._last_gp)

    # -- dragging
    def drag_start(self, card, global_press):
        cid = card.CARD_ID
        if cid not in self.items:
            return
        self.drag = {"id": cid, "grab": card.mapFromGlobal(global_press), "snap": copy.deepcopy(self.items)}
        self.placeholder.setGeometry(card.geometry())
        self.placeholder.show()
        self.placeholder.raise_()
        card.raise_()
        self.autoscroll.start()

    def drag_move(self, gp):
        d = self.drag
        if not d:
            return
        self._last_gp = gp
        cid = d["id"]
        card = self.cards[cid]
        tl = self.mapFromGlobal(gp) - d["grab"]
        card.move(tl)
        m, u, cw = self.margin(), self.unit(), self.colw()
        w = d["snap"][cid][2]
        gx = int(round((tl.x() - m) / (cw + m)))
        gx = max(0, min(self.cols - w, gx))
        gy = max(0, int(round((tl.y() - m) / u)))
        items = copy.deepcopy(d["snap"])
        grid.move(items, cid, gx, gy)
        if items != self.items:
            self.items = items
            self.apply(skip=cid)
        self.placeholder.setGeometry(self.rect(self.items[cid]))

    def drag_end(self):
        if not self.drag:
            return
        self.autoscroll.stop()
        self.drag = None
        self.placeholder.hide()
        self.apply()
        self.store()
        self.layout_changed.emit()

    # -- stretching
    def resize_start(self, card, gp):
        cid = card.CARD_ID
        if cid not in self.items:
            return
        self.sizing = {"id": cid, "snap": copy.deepcopy(self.items)}
        self.placeholder.setGeometry(card.geometry())
        self.placeholder.show()
        self.placeholder.raise_()
        card.raise_()
        self.autoscroll.start()

    def resize_move(self, gp):
        d = self.sizing
        if not d:
            return
        self._last_gp = gp
        cid = d["id"]
        p = d["snap"][cid]
        pos = self.mapFromGlobal(gp)
        top_left = self.rect(p).topLeft()
        m, u, cw = self.margin(), self.unit(), self.colw()
        mw, mh = self.min_size(cid)
        w = int(round((pos.x() - top_left.x() + m) / (cw + m)))
        h = int(round((pos.y() - top_left.y() + m) / u))
        w = max(mw, min(self.cols - p[0], w))
        h = max(mh, h)
        self.cards[cid].resize(max(60, pos.x() - top_left.x()), max(40, pos.y() - top_left.y()))
        items = copy.deepcopy(d["snap"])
        grid.resize(items, cid, w, h)
        if items != self.items:
            self.items = items
            self.apply(skip=cid)
        self.placeholder.setGeometry(self.rect(self.items[cid]))

    def resize_end(self):
        if not self.sizing:
            return
        self.autoscroll.stop()
        self.sizing = None
        self.placeholder.hide()
        self.apply()
        self.store()
        self.layout_changed.emit()

    def grow(self, cid, rows):
        """Makes a card taller (used when settings are ticked in the Property Selector)."""
        if cid in self.items:
            p = self.items[cid]
            grid.resize(self.items, cid, p[2], max(p[3], rows))
            self.apply()
            self.store()
            self.layout_changed.emit()

    def reset(self):
        self.sm.settings["layouts"] = {}
        self._load_items()
        self.apply()
        self.layout_changed.emit()
