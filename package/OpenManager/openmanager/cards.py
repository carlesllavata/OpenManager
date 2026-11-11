# SPDX-License-Identifier: GPL-3.0-or-later
"""The cards of the board. Each one reads the active setup in fill() and writes it back on change."""
import datetime
import json
import os

from PySide6 import QtCore, QtGui, QtWidgets

from . import model
from .widgets import Blocker, Card, ColorButton, Combo, NumberRow, Spin, TabBar, icon, menu_tool, tool, blend, pal, text_color


def hrow(*widgets, stretch_index=None, spacing=4):
    w = QtWidgets.QWidget()
    l = QtWidgets.QHBoxLayout(w)
    l.setContentsMargins(0, 0, 0, 0)
    l.setSpacing(spacing)
    for i, x in enumerate(widgets):
        if x is None:
            l.addStretch(1)
        elif isinstance(x, int):
            l.addSpacing(x)
        else:
            l.addWidget(x, 1 if i == stretch_index else 0)
    return w


def muted(text):
    l = QtWidgets.QLabel(text)
    l.setEnabled(False)
    l.setWordWrap(True)
    return l


def fit_columns(table):
    """Every title stays readable: each column is as wide as its title, the name column takes what is left
    (never less than NAME_MIN) and the table scrolls sideways when they don't fit."""
    h = table.horizontalHeader()
    h.setStretchLastSection(False)
    h.setMinimumSectionSize(28)
    table.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
    table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
    fm = h.fontMetrics()
    others = 0
    for c in range(1, table.columnCount()):
        it = table.horizontalHeaderItem(c)
        text = it.text() if it else ""
        if it:
            it.setToolTip(text)
        h.setSectionResizeMode(c, QtWidgets.QHeaderView.Fixed)
        w = max(38, fm.horizontalAdvance(text) + 18)
        h.resizeSection(c, w)
        others += w
    if table.columnCount():
        h.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        h.resizeSection(0, max(NAME_MIN, table.viewport().width() - others))


NAME_MIN = 130


# ---------------------------------------------------------------- ticked settings shown as rows

class PropRows(QtWidgets.QWidget):
    """Rows for the settings ticked in the Property Selector: slider/number, tick box, text, file, color,
    map or tone-mapping chain, each with a pencil that takes the value from the scene."""
    SHOWN = ("BooleanClass", "Float", "Integer", "String", "Filename", "Color", "Texturemap", "Pipeline", "Date")

    def __init__(self, sm, card_id, parent=None):
        super(PropRows, self).__init__(parent)
        self.sm = sm
        self.card = card_id
        self.form = QtWidgets.QGridLayout(self)
        self.form.setContentsMargins(0, 2, 0, 0)
        self.form.setHorizontalSpacing(8)
        self.form.setVerticalSpacing(3)
        self.form.setColumnStretch(1, 1)
        self.signature = None
        self.editors = {}
        self.store = None
        self.entry = 0

    def fill(self, s, rows, store=None, entry=0):
        """rows: [(tab, prop)] or [(tab, prop, link, key class)] to show for this setup. store: the dict holding
        their values (the setup's props unless this is a second sun / environment); entry: its tab."""
        rows = [r for r in rows if r[1]["class"] in self.SHOWN]
        self.store = s["props"] if store is None else store
        self.entry = entry
        sig = tuple("%s|%s|%s" % (r[0]["name"], r[3] if len(r) > 3 else r[0]["v_class"], r[1]["name"]) for r in rows)
        if sig != self.signature:
            self._build(rows)
            self.signature = sig
        for key, (p, ed) in self.editors.items():
            v = self.store.get(key)
            if v is None:
                v = p.get("value")
            with Blocker(ed):
                if isinstance(ed, QtWidgets.QDateEdit):
                    d = model.solar_to_date(v)
                    ed.setDate(QtCore.QDate(d.year, d.month, d.day))
                elif isinstance(ed, QtWidgets.QCheckBox):
                    ed.setChecked(bool(v))
                elif isinstance(ed, NumberRow):
                    ed.set_value(v if v is not None else 0)
                elif isinstance(ed, ColorButton):
                    ed.set_color(v or "#000000")
                elif isinstance(ed, QtWidgets.QComboBox):
                    txt = v or ""
                    if ed.findData(txt) < 0:
                        ed.addItem((txt.replace("|", "  [", 1) + "]") if txt else "(none)", txt)
                    ed.setCurrentIndex(ed.findData(txt))
                elif isinstance(ed, QtWidgets.QLabel):
                    chain = []
                    try:
                        chain = json.loads(v) if isinstance(v, str) and v else (v or [])
                    except ValueError:
                        pass
                    names = [x.get("class", "?").replace("OperatorPlugin", "") for x in chain]
                    ed.setText(" > ".join(names) if names else "(not taken yet: use the pencil)")
                elif isinstance(ed, QtWidgets.QLineEdit):
                    ed.setText("" if v is None else str(v))
        self.setVisible(bool(rows))

    def _clear(self):
        while self.form.count():
            it = self.form.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.editors = {}

    def _build(self, rows):
        self._clear()
        r = 0
        last_tab = None
        for row in rows:
            t, p = row[0], row[1]
            link = row[2] if len(row) > 2 else None
            key_cls = row[3] if len(row) > 3 else t["v_class"]
            head = t["name"] + ("  -  %s" % link["name"] if link else "")
            if head != last_tab:
                h = QtWidgets.QLabel(head)
                f = h.font()
                f.setBold(True)
                h.setFont(f)
                h.setEnabled(False)
                self.form.addWidget(h, r, 0, 1, 3)
                r += 1
                last_tab = head
            key = "%d|%s|%s" % (self.card, key_cls, p["name"])
            cls = p["class"]
            label = QtWidgets.QLabel(p.get("short") or p["name"])
            label.setToolTip("%s\n%s (%s)" % (p.get("long") or "", p["name"], cls))
            widget = None
            if cls == "BooleanClass":
                ed = QtWidgets.QCheckBox()
                ed.toggled.connect(lambda v, k=key: self._set(k, bool(v)))
            elif cls == "Date":
                ed = QtWidgets.QDateEdit()
                ed.setCalendarPopup(True)
                ed.setDisplayFormat("dd / MM / yyyy")
                ed.dateChanged.connect(lambda d, k=key: self._set(k, model.date_to_solar(datetime.date(d.year(), d.month(), d.day()))))
                widget = hrow(ed, None)
            elif cls in ("Float", "Integer"):
                lo = p.get("min") if p.get("min") is not None else 0.0
                hi = p.get("max") if p.get("max") is not None else max(100.0, float(p.get("value") or 0) * 10)
                if p["name"] == "progressive_timeLimit":
                    hi = max(hi, 600)
                ed = NumberRow(lo, hi, p.get("step"), integer=(cls == "Integer" and p["name"] != "progressive_timeLimit"))
                ed.changed.connect(lambda v, k=key: self._set(k, v))
            elif cls == "Color":
                ed = ColorButton()
                ed.changed.connect(lambda v, k=key: self._set(k, v))
                widget = hrow(ed, None)
            elif cls == "Texturemap":
                ed = Combo()
                ed.addItem("(none)", "")
                ed.view().setMinimumWidth(260)
                ed.activated.connect(lambda i, e=ed, k=key: self._set(k, e.itemData(i) or ""))
                more = tool("refresh", "List the maps in the scene", size=14)
                more.clicked.connect(lambda _=False, e=ed: self._fill_maps(e))
                widget = hrow(ed, more, stretch_index=0)
            elif cls == "Pipeline":
                ed = QtWidgets.QLabel()
                ed.setWordWrap(True)
                ed.setToolTip("The camera's tone-mapping operators, taken from the scene with the pencil")
            else:
                ed = QtWidgets.QLineEdit()
                ed.editingFinished.connect(lambda e=ed, k=key: self._set(k, e.text()))
                if cls == "Filename":
                    b = tool("folder", "Choose a file", size=14)
                    b.clicked.connect(lambda _=False, e=ed, k=key: self._browse(e, k))
                    widget = hrow(ed, b, stretch_index=0)
            pen = tool("edit", "Take the current value from the scene", size=13)
            pen.clicked.connect(lambda _=False, tt=t, pp=p, ll=link, kk=key: self._fetch(tt, pp, ll, kk))
            self.editors[key] = (p, ed)
            self.form.addWidget(label, r, 0)
            self.form.addWidget(widget or ed, r, 1)
            self.form.addWidget(pen, r, 2)
            r += 1

    def _fill_maps(self, combo):
        cur = combo.currentData()
        with Blocker(combo):
            combo.clear()
            combo.addItem("(none)", "")
            for m in self.sm.scene_texmaps():
                combo.addItem(m.replace("|", "  [", 1) + "]", m)
            combo.setCurrentIndex(max(0, combo.findData(cur)))
        combo.showPopup()

    def _browse(self, edit, key):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose a file", os.path.dirname(edit.text()),
                                                     "Images (*.hdr *.exr *.jpg *.png *.tif *.tga);;All (*.*)")
        if f:
            edit.setText(f.replace("\\", "/"))
            self._set(key, edit.text())

    def _fetch(self, tab, prop, link, key):
        if self.sm.fetch_prop(self.card, tab, prop, link=link, key=key, store=self.store, entry=self.entry):
            self.sm.refresh_cards([self.card])

    def _set(self, key, v):
        s = self.sm.active()
        if s is None or self.store is None:
            return
        self.store[key] = v
        self.sm.changed(list_too=False)


# ---------------------------------------------------------------- simple cards

class SceneNameCard(Card):
    CARD_ID = 15

    def build(self):
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("Name of this setup")
        self.edit.textEdited.connect(self._edited)
        self.body_layout.addWidget(self.edit)

    def fill(self, s):
        if self.edit.text() != s["scenename"]:
            with Blocker(self.edit):
                self.edit.setText(s["scenename"])

    def _edited(self, t):
        s = self.setup()
        if s:
            s["scenename"] = t
            self.sm.changed(apply=False)


class CameraCard(Card):
    CARD_ID = 1

    def build(self):
        self.combo = Combo()
        self.combo.activated.connect(self._chosen)
        self.pick = tool("pick", "Select this camera in the scene", slot=self._pick)
        self.lock = tool("unlock", "Lock / unlock the camera's move, rotate and scale", checkable=True, slot=self._lock)
        self.body_layout.addWidget(hrow(self.pick, self.combo, self.lock, stretch_index=1))
        self.rows = PropRows(self.sm, 1)
        self.body_layout.addWidget(self.rows)

    def fill(self, s):
        sc = self.sm.scene
        with Blocker(self.combo):
            self.combo.clear()
            self.combo.addItem("(no camera)", None)
            for c in sc.cameras:
                self.combo.addItem(c["name"], c["handle"])
            i = self.combo.findData(s["camera"]["handle"])
            if i < 0 and s["camera"]["handle"] is not None:
                self.combo.addItem("%s (missing)" % (s["camera"].get("name") or "camera"), s["camera"]["handle"])
                i = self.combo.count() - 1
            self.combo.setCurrentIndex(max(0, i))
        locked = bool(s["camera"]["locked"])
        with Blocker(self.lock):
            self.lock.setChecked(locked)
        self.lock.setIcon(icon("lock" if locked else "unlock"))
        cam = sc.camera(s["camera"]["handle"])
        cls = cam["class"] if cam else None
        self.rows.fill(s, [(t, p) for t, p in self.sm.enabled_rows(1) if model.tab_matches(t, cls)])

    def _chosen(self, i):
        s = self.setup()
        if not s:
            return
        h = self.combo.itemData(i)
        s["camera"]["handle"] = h
        cam = self.sm.scene.camera(h)
        s["camera"]["name"] = cam["name"] if cam else ""
        self.sm.query_values()
        self.fill(s)
        self.sm.changed()

    def _pick(self):
        s = self.setup()
        h = s["camera"].get("handle") if s else None
        if h is None:
            self.sm.toast("Choose a camera first")
        else:
            self.sm.select_handles([h])

    def _lock(self, on):
        s = self.setup()
        if s:
            s["camera"]["locked"] = bool(on)
            self.lock.setIcon(icon("lock" if on else "unlock"))
            self.sm.changed()


class ResolutionCard(Card):
    CARD_ID = 2

    def build(self):
        self.w = Spin()
        self.h = Spin()
        for sp in (self.w, self.h):
            sp.setRange(1, 32768)
            sp.setKeyboardTracking(False)
            sp.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.w.valueChanged.connect(self._width)
        self.h.valueChanged.connect(self._height)
        self.presets = tool("list", "Resolution presets")
        self.presets.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.presets.setStyleSheet("QToolButton::menu-indicator{image:none;width:0}")
        m = QtWidgets.QMenu(self.presets)
        m.aboutToShow.connect(lambda: self._fill_presets(m))
        self.presets.setMenu(m)
        dbl = tool("expand", "Double width and height (active and selected setups)", slot=lambda: self._scale(2.0))
        half = tool("shrink", "Half width and height (active and selected setups)", slot=lambda: self._scale(0.5))
        self.body_layout.addWidget(hrow(self.w, QtWidgets.QLabel("x"), self.h, self.presets, dbl, half, stretch_index=0))
        self.body_layout.itemAt(0).widget().layout().setStretch(2, 1)
        self.aspect = NumberRow(0.1, 10.0, 0.01)
        self.aspect.changed.connect(self._aspect)
        self.lock = tool("unlock", "Lock / unlock the image aspect", checkable=True, slot=self._lock)
        self.body_layout.addWidget(hrow(QtWidgets.QLabel("Image aspect"), self.aspect, self.lock, stretch_index=1))

    def fill(self, s):
        r = s["resolution"]
        with Blocker(self.w, self.h, self.lock):
            self.w.setValue(int(r["width"]))
            self.h.setValue(int(r["height"]))
            self.lock.setChecked(bool(r["locked"]))
        self.aspect.set_value(r["ratio"])
        self.aspect.setEnabled(not r["locked"])
        self.lock.setIcon(icon("lock" if r["locked"] else "unlock"))

    def _width(self, v):
        s = self.setup()
        if not s:
            return
        r = s["resolution"]
        r["width"] = v
        if r["locked"]:
            r["height"] = max(1, int(round(v / float(r["ratio"] or 1))))
        else:
            r["ratio"] = model.ratio(r["width"], r["height"])
        self.fill(s)
        self.sm.changed()

    def _height(self, v):
        s = self.setup()
        if not s:
            return
        r = s["resolution"]
        r["height"] = v
        if r["locked"]:
            r["width"] = max(1, int(round(v * float(r["ratio"]))))
        else:
            r["ratio"] = model.ratio(r["width"], r["height"])
        self.fill(s)
        self.sm.changed()

    def _aspect(self, v):
        s = self.setup()
        if not s or s["resolution"]["locked"]:
            return
        r = s["resolution"]
        r["ratio"] = round(v, 3)
        r["height"] = max(1, int(round(r["width"] / max(0.001, v))))
        with Blocker(self.h):
            self.h.setValue(r["height"])
        self.sm.changed()

    def _fill_presets(self, m):
        m.clear()
        for w, h in self.sm.resolution_presets():
            m.addAction("%d x %d" % (w, h), lambda w=w, h=h: self._preset(w, h))
        m.addSeparator()
        m.addAction(icon("settings"), "Edit Presets...", self.sm.open_settings)

    def _preset(self, w, h):
        s = self.setup()
        if not s:
            return
        s["resolution"].update(width=w, height=h, ratio=model.ratio(w, h))
        self.fill(s)
        self.sm.changed()

    def _scale(self, k):
        for s in self.sm.targets():
            r = s["resolution"]
            r["width"] = max(1, int(round(r["width"] * k)))
            r["height"] = max(1, int(round(r["height"] * k)))
        if self.setup():
            self.fill(self.setup())
        self.sm.changed()

    def _lock(self, on):
        s = self.setup()
        if s:
            s["resolution"]["locked"] = bool(on)
            self.fill(s)
            self.sm.changed(apply=False)


class TimeCard(Card):
    CARD_ID = 7

    def build(self):
        self.group = QtWidgets.QButtonGroup(self)
        radios = []
        for i, t in enumerate(("Single", "Range", "List")):
            r = QtWidgets.QRadioButton(t)
            self.group.addButton(r, i)
            radios.append(r)
        self.group.idClicked.connect(self._kind)
        self.body_layout.addWidget(hrow(*radios, None))
        self.single = Spin()
        self.start = Spin()
        self.end = Spin()
        self.nth = Spin()
        for sp in (self.single, self.start, self.end):
            sp.setRange(-100000, 100000)
            sp.setKeyboardTracking(False)
        self.nth.setRange(1, 10000)
        self.nth.setKeyboardTracking(False)
        self.list = QtWidgets.QLineEdit()
        self.list.setPlaceholderText("1,3,5-12")
        self.single.valueChanged.connect(lambda v: self._set("single", v))
        self.start.valueChanged.connect(lambda v: self._set("start", v))
        self.end.valueChanged.connect(lambda v: self._set("end", v))
        self.nth.valueChanged.connect(lambda v: self._set("nth", v))
        self.list.editingFinished.connect(lambda: self._set("list", self.list.text()))
        self.p_single = hrow(QtWidgets.QLabel("Frame"), self.single, None)
        self.p_range = hrow(self.start, QtWidgets.QLabel("to"), self.end, QtWidgets.QLabel("Every Nth"), self.nth, None)
        self.p_list = hrow(self.list, stretch_index=0)
        for w in (self.p_single, self.p_range, self.p_list):
            self.body_layout.addWidget(w)
        self.count = muted("")
        self.body_layout.addWidget(self.count)

    def fill(self, s):
        f = s["frames"]
        with Blocker(self.single, self.start, self.end, self.nth, self.list):
            self.single.setValue(int(f["single"]))
            self.start.setValue(int(f["start"]))
            self.end.setValue(int(f["end"]))
            self.nth.setValue(max(1, int(f["nth"])))
            self.list.setText(f["list"])
        self.group.button(int(f["kind"])).setChecked(True)
        self.p_single.setVisible(f["kind"] == 0)
        self.p_range.setVisible(f["kind"] == 1)
        self.p_list.setVisible(f["kind"] == 2)
        n = model.frame_count(dict(s, frames=dict(f, enabled=True)))
        self.count.setText("%d frame%s" % (n, "" if n == 1 else "s"))

    def _kind(self, i):
        s = self.setup()
        if s:
            s["frames"]["kind"] = i
            self.fill(s)
            self.sm.changed()

    def _set(self, k, v):
        s = self.setup()
        if s:
            s["frames"][k] = v
            self.fill(s)
            self.sm.changed()


class EntryTabs(QtWidgets.QWidget):
    """The tabs of a card that can hold more than one sun or environment. Hidden while there is only one."""
    picked = QtCore.Signal(int)
    closed = QtCore.Signal(int)

    def __init__(self, parent=None):
        super(EntryTabs, self).__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.bar = TabBar()
        self.bar.setExpanding(False)
        self.bar.setTabsClosable(True)
        self.bar.setDrawBase(False)
        self.bar.setElideMode(QtCore.Qt.ElideMiddle)
        self.bar.currentChanged.connect(self.picked)
        self.bar.tabCloseRequested.connect(self.closed)
        lay.addWidget(self.bar, 1)

    def set_tabs(self, titles, current):
        with Blocker(self.bar):
            while self.bar.count() > len(titles):
                self.bar.removeTab(self.bar.count() - 1)
            while self.bar.count() < len(titles):
                self.bar.addTab("")
            for i, t in enumerate(titles):
                self.bar.setTabText(i, t)
            self.bar.setCurrentIndex(current)
            # the first one can't be closed: remove it by choosing nothing in the list
            btn = self.bar.tabButton(0, QtWidgets.QTabBar.RightSide) if titles else None
            if btn:
                btn.hide()
        self.setVisible(len(titles) > 1)


class LightPickCard(Card):
    """Sun and Dome: the chosen light of that kind on, the others off. The arrow selects it in the scene."""
    KIND = "sun"
    NONE_TEXT = "Disable sun lights"
    MULTI = False

    def build(self):
        self.tab = 0
        self.combo = Combo()
        self.combo.activated.connect(self._chosen)
        self.combo.before_popup = lambda: self.sm.sync_scene(force=True)
        what = "sun" if self.KIND == "sun" else "dome light"
        pick = tool("pick", "Select this %s in the scene" % what, slot=self._pick)
        parts = [pick, self.combo]
        if self.MULTI:
            self.entry_tabs = EntryTabs()
            self.entry_tabs.picked.connect(self._tab_picked)
            self.entry_tabs.closed.connect(self._tab_closed)
            self.body_layout.addWidget(self.entry_tabs)
            parts.append(tool("add", "Add another %s to this setup (a tab for each one)" % what, slot=self._add_entry))
        self.body_layout.addWidget(hrow(*parts, stretch_index=1))
        self.rows = PropRows(self.sm, self.CARD_ID)
        self.body_layout.addWidget(self.rows)
        self.hint = muted("")
        self.body_layout.addWidget(self.hint)

    def _entry(self, s):
        ents = model.entries(s[self.KIND])
        self.tab = min(self.tab, len(ents) - 1)
        return ents[self.tab]

    def _pick(self):
        s = self.setup()
        h = self._entry(s).get("handle") if s else None
        if h is None:
            self.sm.toast("Choose a %s first" % ("sun" if self.KIND == "sun" else "dome light"))
        else:
            self.sm.select_handles([h])

    def items(self):
        return self.sm.scene.suns() if self.KIND == "sun" else self.sm.scene.domes()

    def fill(self, s):
        c = self._entry(s)
        if self.MULTI:
            titles = []
            for i, e in enumerate(model.entries(s[self.KIND])):
                l = self.sm.scene.light(e.get("handle"))
                titles.append(l["name"] if l else "%s %d" % (model.CARDS[self.CARD_ID][0], i + 1))
            self.entry_tabs.set_tabs(titles, self.tab)
        with Blocker(self.combo):
            self.combo.clear()
            self.combo.addItem(self.NONE_TEXT if self.tab == 0 else "(choose one)", None)
            # every sun / Daylight of the scene is always listed; one another tab already uses is shown but can't be taken twice
            used = {}
            for i, e in enumerate(model.entries(s[self.KIND])):
                if e is not c and e.get("handle") is not None:
                    used.setdefault(e.get("handle"), i + 1)
            for l in self.items():
                text = l["name"]
                if l.get("class") == "DaylightAssemblyHead":
                    text += "  (Daylight%s)" % (": " + l["sun_class"] if l.get("sun_class") else "")
                if l["handle"] in used:
                    text += "  - in tab %d" % used[l["handle"]]
                self.combo.addItem(text, l["handle"])
                if l["handle"] in used:
                    it = self.combo.model().item(self.combo.count() - 1)
                    if it is not None:
                        it.setEnabled(False)
            i = self.combo.findData(c.get("handle"))
            self.combo.setCurrentIndex(max(0, i))
        l = self.sm.scene.light(c.get("handle"))
        classes = model.light_tabs_classes(l)
        rows = [(t, p) for t, p in self.sm.enabled_rows(self.CARD_ID) if any(model.tab_matches(t, x) for x in classes)]
        self.rows.fill(s, rows, store=model.entry_store(s, s[self.KIND], self.tab), entry=self.tab)
        if l and not rows:
            self.hint.setText("No settings of %s are ticked: choose them with the puzzle piece (Property Selector)."
                              % " / ".join(classes))
        self.hint.setVisible(bool(l) and not rows)

    def _chosen(self, i):
        s = self.setup()
        if not s:
            return
        h = self.combo.itemData(i)
        c = self._entry(s)
        c["handle"] = h
        l = self.sm.scene.light(h)
        c["name"] = l["name"] if l else ""
        self.sm.query_values()
        self.sm.changed()
        self.fill(s)

    def _add_entry(self):
        s = self.setup()
        if s:
            b = s[self.KIND]
            b.setdefault("extra", []).append({"handle": None, "name": "", "props": {}})
            self.tab = len(b["extra"])
            self.fill(s)
            self.sm.changed(apply=False)

    def _tab_picked(self, i):
        s = self.setup()
        if s and i >= 0:
            self.tab = i
            self.fill(s)

    def _tab_closed(self, i):
        s = self.setup()
        if s and i > 0:
            del s[self.KIND]["extra"][i - 1]
            self.tab = min(self.tab, len(s[self.KIND]["extra"]))
            self.fill(s)
            self.sm.last_sent = []
            self.sm.changed()


class SunCard(LightPickCard):
    CARD_ID = 3
    KIND = "sun"
    NONE_TEXT = "Disable sun lights"
    MULTI = True


class DomeCard(LightPickCard):
    CARD_ID = 4
    KIND = "dome"
    NONE_TEXT = "Disable dome lights"


class EnvironmentCard(Card):
    """3ds Max has one environment slot. With Corona the tabs are mixed in it like a LightMix (each tab on/off with its
    intensity); otherwise the first tab goes in it and the others keep their settings up to date."""
    CARD_ID = 6

    def build(self):
        self.tab = 0
        self.combo = Combo()
        self.combo.activated.connect(self._chosen)
        self.combo.before_popup = lambda: self.sm.sync_scene(force=True)
        add = tool("add", "Add another environment to this setup (a tab for each one, mixed like a LightMix)", slot=self._add_entry)
        more, m = menu_tool("more", "Environment map tools")
        m.addAction(icon("fetch"), "Fetch Current (environment map of the scene)", self._fetch_current)
        m.addAction(icon("image"), "Create New Hdri...", self._new_hdri)
        m.addAction(icon("sun"), "Create New Sky", self._new_sky)
        m.addSeparator()
        m.addAction(icon("eye"), "Show in the Material Editor", self._show)
        m.addAction(icon("refresh"), "List the maps of the scene again", lambda: self.sm.sync_scene(force=True))
        self.entry_tabs = EntryTabs()
        self.entry_tabs.picked.connect(self._tab_picked)
        self.entry_tabs.closed.connect(self._tab_closed)
        self.body_layout.addWidget(self.entry_tabs)
        self.body_layout.addWidget(hrow(self.combo, add, more, stretch_index=0))
        # the mix: one switch for the card, and on/off + intensity for the tab shown
        self.mix_box = QtWidgets.QCheckBox("Mix the tabs (LightMix)")
        self.mix_box.setToolTip("All the tabs that are on go in the environment at once, added together, each one\n"
                                "multiplied by its intensity. Off: only the first tab is the environment.")
        self.mix_box.toggled.connect(self._mix_toggled)
        self.mix_on = QtWidgets.QCheckBox()
        self.mix_on.setToolTip("This tab is part of the environment")
        self.mix_on.toggled.connect(self._on_toggled)
        self.mix_amount = NumberRow(0.0, 10.0, 0.01)
        self.mix_amount.setToolTip("Intensity of this tab in the mix")
        self.mix_amount.changed.connect(self._amount)
        self.mix_row = hrow(self.mix_on, QtWidgets.QLabel("Intensity"), self.mix_amount, stretch_index=2, spacing=6)
        self.body_layout.addWidget(self.mix_box)
        self.body_layout.addWidget(self.mix_row)
        self.path = muted("")
        self.body_layout.addWidget(self.path)
        self.rows = PropRows(self.sm, 6)
        self.body_layout.addWidget(self.rows)

    def _entry(self, s):
        ents = model.entries(s["environment"])
        self.tab = max(0, min(self.tab, len(ents) - 1))
        return ents[self.tab]

    def _mixing(self, s):
        return model.env_mixing(s["environment"], self.sm.scene.engine_id)

    def fill(self, s):
        e = self._entry(s)
        block = s["environment"]
        ents = model.entries(block)
        mixing = self._mixing(s)
        titles = []
        for i, x in enumerate(ents):
            t = x.get("name") or "Environment %d" % (i + 1)
            if mixing and not x.get("on", True):
                t += " (off)"
            titles.append(t)
        self.entry_tabs.set_tabs(titles, self.tab)
        keep = [(x.get("cls"), x.get("name")) for x in ents if x.get("cls")]
        with Blocker(self.combo):
            self.combo.clear()
            self.combo.addItem("No environment map" if self.tab == 0 else "(choose one)", None)
            for m in self.sm.scene.offered_maps(keep):
                self.combo.addItem("%s  [%s]" % (m["name"], m["class"]), "%s|%s" % (m["class"], m["name"]))
            i = self.combo.findData("%s|%s" % (e.get("cls"), e.get("name"))) if e.get("cls") else 0
            self.combo.setCurrentIndex(max(0, i))
        many = len(ents) > 1 and self.sm.scene.engine_id == "corona"
        with Blocker(self.mix_box, self.mix_on):
            self.mix_box.setChecked(bool(block.get("mix", True)))
            self.mix_on.setChecked(bool(e.get("on", True)))
        self.mix_amount.set_value(e.get("amount", 1.0))
        self.mix_box.setVisible(many)
        self.mix_row.setVisible(mixing)
        m = self.sm.scene.map(e.get("cls"), e.get("name"))
        store = model.entry_store(s, block, self.tab)
        files = []
        for link in ((m.get("chain") or [m]) if m else []):
            # a file typed in the Filename row is what this setup really uses
            f = store.get("6|%s|filename" % link["class"]) or link.get("path")
            if f:
                files.append(os.path.basename(f))
        self.path.setText("  /  ".join(files))
        self.path.setVisible(bool(files))
        rows = model.env_rows(m, self.sm.enabled_rows(6)) if m else []
        self.rows.fill(s, rows, store=store, entry=self.tab)

    def use(self, cls, name):
        """This map is now the environment of the tab shown; the list, the rows and the scene all follow."""
        s = self.setup()
        if not s:
            return
        self.sm.reload_scene()
        e = self._entry(s)
        e.update(cls=cls, name=name)
        if not s["environment"]["enabled"]:
            s["environment"]["enabled"] = True
        self.sm.query_values()
        self.refresh()
        self.sm.changed()

    def _fetch_current(self):
        self.sm.reload_scene()
        if self.sm.scene.env_is_mix():
            self.sm.toast("The environment is the mix of the tabs of this card")
        elif self.sm.scene.env_class:
            self.use(self.sm.scene.env_class, self.sm.scene.env_name)
        else:
            self.sm.toast("The scene has no environment map")

    def _new_hdri(self):
        from . import maxlink
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "HDRI", "", "HDRI (*.hdr *.exr);;Images (*.jpg *.png *.tif);;All (*.*)")
        if f:
            m = maxlink.new_hdri(os.path.normpath(f))
            self.use(m["class"], m["name"])

    def _new_sky(self):
        from . import maxlink
        m = maxlink.new_sky()
        self.use(m["class"], m["name"])

    def _show(self):
        from . import maxlink
        s = self.setup()
        e = self._entry(s) if s else None
        if e and e.get("cls"):
            maxlink.show_in_medit(e["cls"], e["name"])

    def _chosen(self, i):
        s = self.setup()
        if not s:
            return
        d = self.combo.itemData(i)
        e = self._entry(s)
        e["cls"], e["name"] = d.split("|", 1) if d else ("", "")
        self.sm.query_values()
        self.sm.changed()
        self.fill(s)

    def _mix_toggled(self, on):
        s = self.setup()
        if s:
            s["environment"]["mix"] = bool(on)
            self.fill(s)
            self.sm.changed()

    def _on_toggled(self, on):
        s = self.setup()
        if s:
            self._entry(s)["on"] = bool(on)
            self.fill(s)
            self.sm.changed()

    def _amount(self, v):
        s = self.setup()
        if s:
            self._entry(s)["amount"] = float(v)
            self.sm.changed(list_too=False)

    def _add_entry(self):
        s = self.setup()
        if s:
            b = s["environment"]
            b.setdefault("extra", []).append(model.new_env_entry())
            self.tab = len(b["extra"])
            self.fill(s)
            self.sm.changed()

    def _tab_picked(self, i):
        s = self.setup()
        if s and i >= 0:
            self.tab = i
            self.fill(s)

    def _tab_closed(self, i):
        s = self.setup()
        if s and i > 0:
            del s["environment"]["extra"][i - 1]
            self.tab = min(self.tab, len(s["environment"]["extra"]))
            self.fill(s)
            self.sm.last_sent = []
            self.sm.changed()


class XrefCard(Card):
    CARD_ID = 16

    def build(self):
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumHeight(160)
        self.list.itemChanged.connect(self._changed)
        self.body_layout.addWidget(muted("Ticked xref scenes are on in this setup, the others off."))
        self.body_layout.addWidget(self.list)

    def fill(self, s):
        on = set(s["xref"]["set"])
        with Blocker(self.list):
            self.list.clear()
            for x in self.sm.scene.xrefs:
                it = QtWidgets.QListWidgetItem(x["file"])
                it.setToolTip(x["path"])
                it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
                it.setCheckState(QtCore.Qt.Checked if x["file"] in on else QtCore.Qt.Unchecked)
                self.list.addItem(it)
            if not self.sm.scene.xrefs:
                it = QtWidgets.QListWidgetItem("There are no xref scenes in this file")
                it.setFlags(QtCore.Qt.NoItemFlags)
                self.list.addItem(it)

    def _changed(self, it):
        s = self.setup()
        if not s:
            return
        s["xref"]["set"] = [self.list.item(i).text() for i in range(self.list.count())
                            if self.list.item(i).checkState() == QtCore.Qt.Checked]
        self.sm.changed()


class RenderCustomCard(Card):
    CARD_ID = 25

    def build(self):
        self.info = muted("")
        self.body_layout.addWidget(self.info)
        self.rows = PropRows(self.sm, 25)
        self.body_layout.addWidget(self.rows)

    def fill(self, s):
        rows = self.sm.enabled_rows(25)
        self.info.setText("" if rows else "Use the Property Selector (three stripes) to choose render settings.")
        self.info.setVisible(not rows)
        self.rows.fill(s, rows)


class NotesCard(Card):
    CARD_ID = 12

    def build(self):
        self.text = QtWidgets.QPlainTextEdit()
        self.text.setPlaceholderText("Notes for this setup")
        self.text.setMinimumHeight(90)
        self.text.textChanged.connect(self._changed)
        self.body_layout.addWidget(self.text)

    def fill(self, s):
        if self.text.toPlainText() != s["notes"]:
            with Blocker(self.text):
                self.text.setPlainText(s["notes"])

    def _changed(self):
        s = self.setup()
        if s:
            s["notes"] = self.text.toPlainText()
            self.sm.changed(apply=False, list_too=False)


class TodoCard(Card):
    CARD_ID = 13
    NEEDS_SETUP = False

    def build(self):
        self.list = QtWidgets.QListWidget()
        self.list.setMinimumHeight(90)
        self.list.itemChanged.connect(self._changed)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("New task, then Enter")
        self.edit.returnPressed.connect(self._add)
        rm = tool("delete", "Remove the selected task", slot=self._remove)
        self.body_layout.addWidget(self.list)
        self.body_layout.addWidget(hrow(self.edit, rm, stretch_index=0))

    def fill(self, s):
        with Blocker(self.list):
            self.list.clear()
            for t in self.sm.todo:
                it = QtWidgets.QListWidgetItem(t.get("text", ""))
                it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable)
                it.setCheckState(QtCore.Qt.Checked if t.get("done") else QtCore.Qt.Unchecked)
                self.list.addItem(it)

    def _changed(self, it):
        self.sm.todo = [{"text": self.list.item(i).text(), "done": self.list.item(i).checkState() == QtCore.Qt.Checked}
                        for i in range(self.list.count())]
        self.sm.changed(apply=False, list_too=False)

    def _add(self):
        t = self.edit.text().strip()
        if t:
            self.sm.todo.append({"text": t, "done": False})
            self.edit.clear()
            self.fill(None)
            self.sm.changed(apply=False, list_too=False)

    def _remove(self):
        r = self.list.currentRow()
        if 0 <= r < len(self.sm.todo):
            del self.sm.todo[r]
            self.fill(None)
            self.sm.changed(apply=False, list_too=False)


# ---------------------------------------------------------------- tables: layers, objects, lights

class FlagTable(QtWidgets.QTableWidget):
    def __init__(self, parent=None):
        super(FlagTable, self).__init__(parent)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setDefaultSectionSize(22)
        self.horizontalHeader().setHighlightSections(False)
        self.setMinimumHeight(150)
        self.setShowGrid(False)
        self.setWordWrap(False)

    def resizeEvent(self, e):
        super(FlagTable, self).resizeEvent(e)
        fit_columns(self)

    def flag_item(self, on):
        it = QtWidgets.QTableWidgetItem()
        it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsSelectable)
        it.setCheckState(QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)
        return it


class LayersCard(Card):
    CARD_ID = 14
    FIELD = {"on": "visible", "isfrozen": "freeze", "renderable": "render", "primaryVisibility": "vcam"}

    def build(self):
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Search layers")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _: self.fill(self.setup()) if self.setup() else None)
        fetch = tool("fetch", "Take every layer as it is now in the scene", slot=self._fetch)
        self.add = tool("add", "Add the selected layers (in the Layer Explorer, or those of the selected objects)", slot=self._add_selected)
        rm = tool("delete", "Remove the selected layers from this setup", slot=self._remove)
        self.body_layout.addWidget(hrow(self.filter, fetch, self.add, rm, stretch_index=0))
        self.table = FlagTable()
        self.table.itemChanged.connect(self._changed)
        self.body_layout.addWidget(self.table)

    def columns(self):
        return [p for _, p in self.sm.enabled_rows(14) if p["class"] == "BooleanClass"]

    def fill(self, s):
        cols = self.columns()
        flt = self.filter.text().lower()
        rows = [l for l in s["layers"]["set"] if flt in l["name"].lower()]
        with Blocker(self.table):
            self.table.clear()
            self.table.setColumnCount(1 + len(cols))
            self.table.setHorizontalHeaderLabels(["Name"] + [p.get("short") or p["name"] for p in cols])
            self.table.setRowCount(len(rows))
            names = set(x["name"] for x in self.sm.scene.layers)
            for r, l in enumerate(rows):
                it = QtWidgets.QTableWidgetItem(l["name"] if l["name"] in names else l["name"] + " (missing)")
                it.setData(QtCore.Qt.UserRole, l["name"])
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                self.table.setItem(r, 0, it)
                for c, p in enumerate(cols):
                    f = self.FIELD.get(p["name"])
                    on = l[f] if f else l.get("extra", {}).get(p["name"], p.get("value", False) is True)
                    fi = self.table.flag_item(on)
                    fi.setData(QtCore.Qt.UserRole, p["name"])
                    self.table.setItem(r, c + 1, fi)
            fit_columns(self.table)

    def _entry(self, s, name):
        return next((l for l in s["layers"]["set"] if l["name"] == name), None)

    def _changed(self, it):
        s = self.setup()
        if not s or it.column() == 0:
            return
        name = self.table.item(it.row(), 0).data(QtCore.Qt.UserRole)
        l = self._entry(s, name)
        if l is None:
            return
        on = it.checkState() == QtCore.Qt.Checked
        prop = it.data(QtCore.Qt.UserRole)
        # the same change goes to every selected row (quick for many layers)
        rows = set(i.row() for i in self.table.selectedItems())
        targets = [l]
        if it.row() in rows and len(rows) > 1:
            targets = [self._entry(s, self.table.item(r, 0).data(QtCore.Qt.UserRole)) for r in rows]
        for l in targets:
            if l is None:
                continue
            f = self.FIELD.get(prop)
            if f:
                l[f] = on
            else:
                l.setdefault("extra", {})[prop] = on
        if len(targets) > 1:
            self.fill(s)
        self.sm.changed()

    def _fetch(self):
        s = self.setup()
        if not s:
            return
        s["layers"]["set"] = [model.layer_entry(l["name"], l["visible"], l.get("frozen", False), l.get("render", True))
                              for l in self.sm.scene.layers]
        if not s["layers"]["enabled"]:
            s["layers"]["enabled"] = True
            self.refresh()
        else:
            self.fill(s)
        self.sm.changed()

    def _add_selected(self):
        from . import maxlink
        s = self.setup()
        if not s:
            return
        names = maxlink.selected_layers()
        have = set(l["name"] for l in s["layers"]["set"])
        new = [l for l in self.sm.scene.layers if l["name"] in names and l["name"] not in have]
        if not new:
            self.sm.toast("Those layers are already in this setup" if names else "Select a layer first")
        self._add(new)

    def _add(self, layers):
        s = self.setup()
        if not s:
            return
        for l in layers:
            s["layers"]["set"].append(model.layer_entry(l["name"], l["visible"], l.get("frozen", False), l.get("render", True)))
        self.fill(s)
        self.sm.changed()

    def _remove(self):
        s = self.setup()
        if not s:
            return
        names = set(self.table.item(r, 0).data(QtCore.Qt.UserRole) for r in set(i.row() for i in self.table.selectedItems()))
        s["layers"]["set"] = [l for l in s["layers"]["set"] if l["name"] not in names]
        self.fill(s)
        self.sm.changed()


class ObjectsCard(Card):
    CARD_ID = 23

    def build(self):
        add = tool("add", "Add the objects selected in the scene", slot=self._add_selected)
        rm = tool("delete", "Remove the selected rows from this setup", slot=self._remove)
        sel = tool("select", "Select these objects in the scene", slot=self._select)
        self.count = muted("")
        self.body_layout.addWidget(hrow(self.count, None, sel, add, rm))
        self.table = FlagTable()
        self.table.itemChanged.connect(self._changed)
        self.body_layout.addWidget(self.table)

    def columns(self):
        return [p for _, p in self.sm.enabled_rows(23) if p["class"] == "BooleanClass"]

    def _value(self, o, name):
        if name == "isNodeHidden":
            return o["visible"]
        if name == "renderable":
            return o["renderable"]
        return o.get("extra", {}).get(name, True)

    def fill(self, s):
        cols = self.columns()
        rows = s["objects"]["set"]
        self.count.setText("%d object%s" % (len(rows), "" if len(rows) == 1 else "s") if rows else "Select objects in the scene, then +")
        with Blocker(self.table):
            self.table.clear()
            self.table.setColumnCount(1 + len(cols))
            self.table.setHorizontalHeaderLabels(["Name"] + [("Visible" if p["name"] == "isNodeHidden" else p.get("short") or p["name"]) for p in cols])
            self.table.setRowCount(len(rows))
            for r, o in enumerate(rows):
                so = self.sm.scene.obj(o["handle"])
                name = so["name"] if so else (o.get("name") or "#%s" % o["handle"]) + " (missing)"
                it = QtWidgets.QTableWidgetItem(name)
                it.setData(QtCore.Qt.UserRole, o["handle"])
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                self.table.setItem(r, 0, it)
                for c, p in enumerate(cols):
                    fi = self.table.flag_item(self._value(o, p["name"]))
                    fi.setData(QtCore.Qt.UserRole, p["name"])
                    self.table.setItem(r, c + 1, fi)
            fit_columns(self.table)

    def _changed(self, it):
        s = self.setup()
        if not s or it.column() == 0:
            return
        on = it.checkState() == QtCore.Qt.Checked
        prop = it.data(QtCore.Qt.UserRole)
        rows = set(i.row() for i in self.table.selectedItems())
        if it.row() not in rows:
            rows = {it.row()}
        handles = set(self.table.item(r, 0).data(QtCore.Qt.UserRole) for r in rows)
        for o in s["objects"]["set"]:
            if o["handle"] in handles:
                if prop == "isNodeHidden":
                    o["visible"] = on
                elif prop == "renderable":
                    o["renderable"] = on
                else:
                    o.setdefault("extra", {})[prop] = on
        if len(rows) > 1:
            self.fill(s)
        self.sm.changed()

    def _add_selected(self):
        s = self.setup()
        if not s:
            return
        have = set(o["handle"] for o in s["objects"]["set"])
        added = 0
        for so in self.sm.selected_objects():
            if so["handle"] in have:
                continue
            s["objects"]["set"].append(model.object_entry(so["handle"], so["name"], so["visible"], True))
            added += 1
        if not added:
            self.sm.toast("Select geometry in the scene first")
        self.fill(s)
        self.sm.changed()

    def _remove(self):
        s = self.setup()
        if not s:
            return
        hs = set(self.table.item(r, 0).data(QtCore.Qt.UserRole) for r in set(i.row() for i in self.table.selectedItems()))
        s["objects"]["set"] = [o for o in s["objects"]["set"] if o["handle"] not in hs]
        self.fill(s)
        self.sm.changed()

    def _select(self):
        s = self.setup()
        if s:
            self.sm.select_handles([o["handle"] for o in s["objects"]["set"]])


class LightsCard(Card):
    CARD_ID = 26

    def build(self):
        self.add = tool("add", "Add a light")
        self.add.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.add.setStyleSheet("QToolButton::menu-indicator{image:none;width:0}")
        self.add_menu = QtWidgets.QMenu(self.add)
        self.add_menu.aboutToShow.connect(self._fill_add_menu)
        self.add.setMenu(self.add_menu)
        rm = tool("delete", "Remove the selected lights from this setup", slot=self._remove)
        self.body_layout.addWidget(hrow(muted("Lights and their settings in this setup"), None, self.add, rm))
        self.table = FlagTable()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed)
        self.table.setMinimumHeight(140)
        self.table.itemChanged.connect(self._changed)
        self.body_layout.addWidget(self.table)

    def columns(self):
        return [p for _, p in self.sm.enabled_rows(26) if p["class"] not in ("String", "Matrix3")]

    def fill(self, s):
        cols = self.columns()
        hs = s["lights"]["set"]
        with Blocker(self.table):
            self.table.clear()
            self.table.setColumnCount(1 + len(cols))
            self.table.setHorizontalHeaderLabels(["Name"] + [p.get("short") or p["name"] for p in cols])
            self.table.setRowCount(len(hs))
            for r, h in enumerate(hs):
                l = self.sm.scene.light(h)
                it = QtWidgets.QTableWidgetItem(l["name"] if l else "#%s (missing)" % h)
                it.setData(QtCore.Qt.UserRole, h)
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                self.table.setItem(r, 0, it)
                for c, p in enumerate(cols):
                    v = s["props"].get("26|%s|%s" % (h, p["name"]))
                    it = QtWidgets.QTableWidgetItem()
                    it.setData(QtCore.Qt.UserRole, p["name"])
                    if p["class"] == "BooleanClass":
                        it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsSelectable)
                        it.setCheckState(QtCore.Qt.Checked if (v if v is not None else p.get("value")) else QtCore.Qt.Unchecked)
                    else:
                        it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable)
                        it.setText("" if v is None else ("%g" % float(v)))
                        it.setToolTip("Empty = left as it is in the scene")
                    self.table.setItem(r, c + 1, it)
            fit_columns(self.table)

    def _changed(self, it):
        s = self.setup()
        if not s or it.column() == 0:
            return
        h = self.table.item(it.row(), 0).data(QtCore.Qt.UserRole)
        name = it.data(QtCore.Qt.UserRole)
        key = "26|%s|%s" % (h, name)
        if it.flags() & QtCore.Qt.ItemIsUserCheckable:
            s["props"][key] = it.checkState() == QtCore.Qt.Checked
        else:
            try:
                s["props"][key] = float(it.text().replace(",", "."))
            except ValueError:
                s["props"].pop(key, None)
        self.sm.changed()

    def _fill_add_menu(self):
        self.add_menu.clear()
        s = self.setup()
        if not s:
            return
        self.add_menu.addAction("Lights selected in the scene", self._add_selected)
        self.add_menu.addSeparator()
        have = set(s["lights"]["set"])
        for l in self.sm.scene.other_lights()[:300]:
            if l["handle"] not in have:
                self.add_menu.addAction(l["name"], lambda h=l["handle"]: self._add([h]))

    def _add_selected(self):
        hs = [h for h in self.sm.selected_handles() if self.sm.scene.light(h)]
        if not hs:
            self.sm.toast("Select lights in the scene first")
        self._add(hs)

    def _add(self, hs):
        s = self.setup()
        if not s:
            return
        for h in hs:
            if h not in s["lights"]["set"]:
                s["lights"]["set"].append(h)
                self.sm.query_light(s, h)
        self.fill(s)
        self.sm.changed()

    def _remove(self):
        s = self.setup()
        if not s:
            return
        hs = set(self.table.item(r, 0).data(QtCore.Qt.UserRole) for r in set(i.row() for i in self.table.selectedItems()))
        s["lights"]["set"] = [h for h in s["lights"]["set"] if h not in hs]
        for k in [k for k in s["props"] if k.startswith("26|") and int(k.split("|")[1]) in hs]:
            del s["props"][k]
        self.fill(s)
        self.sm.changed()


# ---------------------------------------------------------------- render output

class OutputCard(Card):
    CARD_ID = 9

    def build(self):
        self.project = QtWidgets.QLineEdit()
        self.project.setPlaceholderText("Project path (folder the render goes into)")
        self.project.editingFinished.connect(self._project)
        browse = tool("folder", "Choose the folder", slot=self._browse)
        more = tool("more", "Project path presets / output presets")
        more.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        more.setStyleSheet("QToolButton::menu-indicator{image:none;width:0}")
        m = QtWidgets.QMenu(more)
        m.addAction("Current Max Folder", lambda: self._set_project(self.sm.scene.folder))
        m.addAction("Default Render Output", lambda: self._set_project(self.sm.scene.output_dir))
        m.addSeparator()
        m.addAction(icon("export"), "Export output preset (.smp)...", self.sm.export_output_preset)
        m.addAction(icon("import"), "Import output preset (.smp)...", self.sm.import_output_preset)
        more.setMenu(m)
        self.body_layout.addWidget(hrow(self.project, browse, more, stretch_index=0))
        self.tokens = QtWidgets.QWidget()
        self.tok_layout = QtWidgets.QVBoxLayout(self.tokens)
        self.tok_layout.setContentsMargins(0, 0, 0, 0)
        self.tok_layout.setSpacing(3)
        self.body_layout.addWidget(self.tokens)
        add = QtWidgets.QToolButton()
        add.setText(" Add token")
        add.setIcon(icon("add", 14))
        add.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        add.setAutoRaise(True)
        add.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        add.setStyleSheet("QToolButton::menu-indicator{image:none;width:0}")
        am = QtWidgets.QMenu(add)
        for k in model.TOKEN_TYPES:
            am.addAction(k, lambda k=k: self._add(k))
        add.setMenu(am)
        self.body_layout.addWidget(hrow(add, None))
        self.final = QtWidgets.QLabel()
        self.final.setWordWrap(True)
        self.final.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.body_layout.addWidget(self.final)
        self.signature = None

    def fill(self, s):
        o = s["output"]
        if self.project.text() != o["project_path"]:
            self.project.setText(o["project_path"])
        sig = tuple(t["kind"] for t in o["preset"])
        if sig != self.signature or self.tok_layout.count() != len(o["preset"]):
            self._build_tokens(s)
            self.signature = sig
        else:
            self._fill_tokens(s)
        self.update_final(s)

    def update_final(self, s):
        path, problem = self.sm.build_path(s)
        color = "#23d160" if problem is None else "#ff3860"
        text = '<span style="color:%s">%s</span> %s' % (color, "●", path.replace("<", "&lt;") or "(empty)")
        if problem:
            text += '<br><span style="color:%s">%s</span>' % (color, problem.replace("<", "&lt;"))
        self.final.setText(text)
        self.final.setToolTip("This path is used when rendering" if problem is None else
                              "Not a complete file path yet: the render output is left as it is, and Batch Render skips this setup")

    def _build_tokens(self, s):
        while self.tok_layout.count():
            it = self.tok_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.rows = []
        for i, t in enumerate(s["output"]["preset"]):
            row = self._token_row(i, t)
            self.tok_layout.addWidget(row)
        self._fill_tokens(s)

    def _token_row(self, i, t):
        kind = Combo()
        kind.addItems(model.TOKEN_TYPES)
        kind.setCurrentText(t["kind"])
        kind.currentTextChanged.connect(lambda k, i=i: self._kind(i, k))
        k = t["kind"]
        if k == "Extension":
            val = Combo()
            val.addItems(model.EXTENSIONS)
            val.currentTextChanged.connect(lambda v, i=i: self._value(i, v))
        elif k in ("Date", "Date (Folder)"):
            val = Combo()
            val.addItems(model.DATE_FORMATS)
            val.currentTextChanged.connect(lambda v, i=i: self._value(i, v))
        elif k in ("Text", "Folder", "Version"):
            val = QtWidgets.QLineEdit()
            val.textEdited.connect(lambda v, i=i: self._value(i, v, rebuild=False))
        else:
            val = QtWidgets.QLineEdit()
            val.setReadOnly(True)
            val.setEnabled(False)
        digits = None
        if k in ("Index", "Version"):
            digits = Spin()
            digits.setRange(1, 5)
            digits.setPrefix("pad ")
            digits.valueChanged.connect(lambda v, i=i: self._digits(i, v))
        folder = QtWidgets.QCheckBox("/")
        folder.setToolTip("Ends a folder")
        folder.toggled.connect(lambda v, i=i: self._folder(i, v))
        up = tool("up", "Move up", size=12, slot=lambda _=False, i=i: self._move(i, -1))
        down = tool("down", "Move down", size=12, slot=lambda _=False, i=i: self._move(i, 1))
        rm = tool("close", "Remove", size=10, slot=lambda _=False, i=i: self._remove(i))
        parts = [kind, val] + ([digits] if digits else []) + [folder, up, down, rm]
        row = hrow(*parts, stretch_index=1)
        row.kind, row.val, row.digits, row.folder = kind, val, digits, folder
        self.rows.append(row)
        return row

    def _fill_tokens(self, s):
        cam = self.sm.scene.camera(s["camera"]["handle"])
        preview = {
            "Camera": cam["name"] if cam else "(no camera)",
            "FileName (Full)": os.path.splitext(self.sm.scene.file)[0],
            "FileName (Filtered)": model.filtered_file_name(self.sm.scene.file),
            "FileVersion": model.file_version(self.sm.scene.file),
            "Index": str(self.sm.index_of(s) + 1),
            "PcName": self.sm.pc_name, "UserName": self.sm.user_name,
            "SceneName": s["scenename"],
        }
        for row, t in zip(self.rows, s["output"]["preset"]):
            with Blocker(row.val, row.folder, *( [row.digits] if row.digits else [])):
                if isinstance(row.val, QtWidgets.QComboBox):
                    row.val.setCurrentText(t["value"])
                elif row.val.isReadOnly():
                    row.val.setText(preview.get(t["kind"], ""))
                elif row.val.text() != t["value"]:
                    row.val.setText(t["value"])
                if row.digits:
                    row.digits.setValue(int(t.get("digits") or 1))
                row.folder.setChecked(bool(t.get("folder")))

    def _tok(self):
        s = self.setup()
        return (s, s["output"]["preset"]) if s else (None, None)

    def _done(self, s, rebuild):
        if rebuild:
            self.signature = None
            self.fill(s)
        else:
            self.update_final(s)
        self.sm.changed()

    def _kind(self, i, k):
        s, p = self._tok()
        if s:
            p[i] = model.new_token(k)
            self._done(s, True)

    def _value(self, i, v, rebuild=False):
        s, p = self._tok()
        if s:
            p[i]["value"] = v
            self._done(s, rebuild)

    def _digits(self, i, v):
        s, p = self._tok()
        if s:
            p[i]["digits"] = v
            self._done(s, False)

    def _folder(self, i, v):
        s, p = self._tok()
        if s:
            p[i]["folder"] = bool(v)
            self._done(s, False)

    def _move(self, i, d):
        s, p = self._tok()
        j = i + d
        if s and 0 <= j < len(p):
            p[i], p[j] = p[j], p[i]
            self._done(s, True)

    def _remove(self, i):
        s, p = self._tok()
        if s:
            del p[i]
            self._done(s, True)

    def _add(self, k):
        s, p = self._tok()
        if s:
            ext = next((n for n, t in enumerate(p) if t["kind"] == "Extension"), None)
            if ext is not None and k != "Extension":
                p.insert(ext, model.new_token(k))
            else:
                p.append(model.new_token(k))
            self._done(s, True)

    def _project(self):
        s = self.setup()
        if s and s["output"]["project_path"] != self.project.text():
            s["output"]["project_path"] = self.project.text()
            self.update_final(s)
            self.sm.changed()

    def _set_project(self, path):
        s = self.setup()
        if s:
            s["output"]["project_path"] = (path or "").replace("\\", "/")
            self.fill(s)
            self.sm.changed()

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Project path", self.project.text() or self.sm.scene.folder)
        if d:
            self._set_project(d)


# ---------------------------------------------------------------- HDRI quick browser

class HdriCard(Card):
    """HDRIs of a folder with their pictures. An HDRI without a picture gets one made by 3ds Max from the HDRI itself
    (kept in a cache folder, so only once): small files straight away, big ones with the "Make previews" button."""
    CARD_ID = 28
    NEEDS_SETUP = False
    AUTO_MB = 60  # HDRIs up to this size get their preview made without asking

    def build(self):
        self.folders = Combo()
        self.folders.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.folders.setMinimumContentsLength(8)  # a long path must not push the buttons out of the card
        self.folders.activated.connect(self._folder_chosen)
        add = tool("add", "Add a folder of HDRIs", slot=self._add)
        rm = tool("close", "Remove this folder from the list", size=12, slot=self._remove)
        rf = tool("refresh", "Read the folder again", slot=self._load)
        self.body_layout.addWidget(hrow(rm, self.folders, rf, add, stretch_index=1))
        self.grid = QtWidgets.QListWidget()
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setIconSize(QtCore.QSize(150, 75))
        self.grid.setGridSize(QtCore.QSize(162, 112))
        self.grid.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.grid.setSpacing(4)
        self.grid.setUniformItemSizes(True)
        self.grid.setMinimumHeight(220)
        self.grid.setWordWrap(True)
        self.grid.itemDoubleClicked.connect(self._apply)
        self.grid.setToolTip("Click to select, double click to use it as the environment")
        self.body_layout.addWidget(self.grid)
        self.make = QtWidgets.QPushButton(icon("image", 14), " Make previews")
        self.make.setToolTip("Make a picture from each HDRI that has none (3ds Max reads the HDRI; it is done once)")
        self.make.clicked.connect(self._make_clicked)
        self.make.hide()
        self.body_layout.addWidget(hrow(self.make, None))
        self.msg = muted('Press "+" to add a folder of .hdr / .exr files with their pictures (.jpg, .png, .webp).')
        self.body_layout.addWidget(self.msg)
        self._queue = []
        self._missing = []
        self._making = False
        self._made = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._load_next_thumb)
        self._gen = QtCore.QTimer(self)
        self._gen.setInterval(30)
        self._gen.timeout.connect(self._make_next)
        self._loaded_for = None

    @staticmethod
    def cache_dir():
        try:
            from pymxs import runtime as rt
            base = str(rt.getDir(rt.Name("plugcfg")))
        except Exception:
            base = os.path.expanduser("~")
        return os.path.join(base, "OpenManager_hdri")

    def cache_file(self, raw):
        try:
            st = os.stat(raw)
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            size, mtime = 0, 0
        return os.path.join(self.cache_dir(), model.preview_cache_name(raw, size, mtime)), size

    def fill(self, s):
        st = self.sm.settings
        fs = st.setdefault("hdri_folders", [])
        with Blocker(self.folders):
            self.folders.clear()
            for f in fs:
                self.folders.addItem(f, f)
                self.folders.setItemData(self.folders.count() - 1, f, QtCore.Qt.ToolTipRole)
            self.folders.setCurrentIndex(min(max(0, st.get("hdri_selected", 0)), max(0, len(fs) - 1)))
        cur = self.folders.currentData()
        if cur != self._loaded_for:
            self._load()

    def _folder_chosen(self, i):
        self.sm.settings["hdri_selected"] = i
        self.sm.save_settings()
        self._load()

    def _add(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder with HDRIs")
        if d:
            fs = self.sm.settings.setdefault("hdri_folders", [])
            d = d.replace("\\", "/")
            if d not in fs:
                fs.append(d)
            self.sm.settings["hdri_selected"] = fs.index(d)
            self.sm.save_settings()
            self._loaded_for = None
            self.fill(None)

    def _remove(self):
        fs = self.sm.settings.setdefault("hdri_folders", [])
        i = self.folders.currentIndex()
        if 0 <= i < len(fs):
            del fs[i]
            self.sm.settings["hdri_selected"] = max(0, i - 1)
            self.sm.save_settings()
            self._loaded_for = None
            self.fill(None)

    def _load(self):
        self._stop_making()
        self.grid.clear()
        self._timer.stop()
        self._missing = []
        folder = self.folders.currentData()
        self._loaded_for = folder
        if not folder:
            self.msg.setText('Press "+" to add a folder of .hdr / .exr files with their pictures (.jpg, .png, .webp).')
            self.msg.show()
            self._update_make()
            return
        items = model.read_image_thumbnails(folder)
        self.msg.setVisible(not items)
        self.msg.setText("No .hdr or .exr files in this folder.")
        placeholder = icon("image", 48, blend(pal().color(QtGui.QPalette.Window), text_color(), 0.4))
        self._queue = []
        for t in items:
            it = QtWidgets.QListWidgetItem(placeholder, t["name"])
            # the cell is as big as a picture plus its name (not as the small placeholder it starts with)
            it.setSizeHint(QtCore.QSize(158, 108))
            it.setData(QtCore.Qt.UserRole, t["raw"])
            it.setToolTip(t["raw"])
            self.grid.addItem(it)
            thumb = t["thumb"]
            if not thumb:
                cached, _ = self.cache_file(t["raw"])
                thumb = cached if os.path.isfile(cached) else None
            if thumb:
                self._queue.append((it, thumb, t["raw"]))
            else:
                self._missing.append((it, t["raw"]))
        self._timer.start()
        self._update_make()
        # small HDRIs get their picture made right away; big ones wait for the button
        if any(self._size_mb(raw) <= self.AUTO_MB for _, raw in self._missing):
            self._start_making(auto=True)

    @staticmethod
    def _size_mb(raw):
        try:
            return os.path.getsize(raw) / 1048576.0
        except OSError:
            return 0.0

    def _load_next_thumb(self):
        # one thumbnail per event-loop turn so the window never freezes on big folders
        if not self._queue:
            self._timer.stop()
            return
        it, path, raw = self._queue.pop(0)
        if not self._set_picture(it, path):
            # a picture Qt can't read (a .webp without its plugin...): 3ds Max makes one from the HDRI instead
            cached, _ = self.cache_file(raw)
            if path != cached:
                self._missing.append((it, raw))
                self._update_make()

    def _set_picture(self, it, path):
        r = QtGui.QImageReader(path)
        r.setAutoTransform(True)
        sz = r.size()
        if sz.isValid():
            r.setScaledSize(sz.scaled(300, 150, QtCore.Qt.KeepAspectRatio))
        img = r.read()
        if img.isNull():
            return False
        try:
            it.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(img)))
        except RuntimeError:
            pass
        return True

    def _update_make(self):
        n = len(self._missing)
        if self._making:
            self.make.setText(" Making previews... %d left (stop)" % n)
        else:
            self.make.setText(" Make %d preview%s" % (n, "" if n == 1 else "s"))
        self.make.setVisible(n > 0 or self._making)

    def _make_clicked(self):
        if self._making:
            self._stop_making()
        else:
            self._start_making(auto=False)

    def _start_making(self, auto):
        if not self._missing:
            return
        self._auto = auto
        self._making = True
        self._gen.start()
        self._update_make()

    def _stop_making(self):
        self._making = False
        self._gen.stop()
        self._update_make()

    def _make_next(self):
        if self.sm.rendering:
            return
        nxt = None
        for k, (it, raw) in enumerate(self._missing):
            if not self._auto or self._size_mb(raw) <= self.AUTO_MB:
                nxt = k
                break
        if nxt is None:
            self._stop_making()
            return
        it, raw = self._missing.pop(nxt)
        from . import maxlink
        cached, _ = self.cache_file(raw)
        ok = False
        try:
            ok = maxlink.hdri_preview(raw, cached)
        except Exception as ex:
            print("OpenManager: preview of %s -> %s" % (raw, ex))
        if ok:
            try:
                self._set_picture(it, cached)
            except RuntimeError:
                pass
        self._update_make()

    def _apply(self, it):
        self.sm.apply_hdri(it.data(QtCore.Qt.UserRole))


CARD_CLASSES = [SceneNameCard, CameraCard, ResolutionCard, TimeCard, SunCard, LightsCard, DomeCard, EnvironmentCard,
                HdriCard, LayersCard, ObjectsCard, XrefCard, OutputCard, RenderCustomCard, NotesCard, TodoCard]
