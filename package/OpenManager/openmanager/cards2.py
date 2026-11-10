# SPDX-License-Identifier: GPL-3.0-or-later
"""Cards added to match the original module list: Background, Atmosphere, Variants, Render Elements,
Render Settings Preset / Override, Post-Production, Scripts and Thumbnail."""
import os

from PySide6 import QtCore, QtGui, QtWidgets

from . import maxlink, model
from .cards import FlagTable, fit_columns, hrow, muted
from .widgets import Blocker, Card, ColorButton, Combo, DoubleSpin, FlowLayout, NumberRow, Spin, TabBar, icon, menu_tool, tool

# short names for the values of a tone-mapping operator that shows several of them in one line
POST_SHORT = {"highlightCompression": "H. Compr.", "richShadows": "Rich Shadows", "toeStrength": "Toe Str.", "toeLength": "Toe Len.",
              "shoulderStrength": "Shoulder Str.", "shoulderLength": "Shoulder Len.", "shoulderAngle": "Shoulder Ang.",
              "linear": "Lin", "logarithmic": "Log", "opacity": "Opacity", "intensity": "Intensity", "falloff": "Falloff"}
LUT_FILES = "LUT (*.cube *.3dl *.csp *.lut *.spi1d *.spi3d *.cc *.ccc);;All (*.*)"


class BackgroundCard(Card):
    """What the viewport shows behind the scene."""
    CARD_ID = 8

    def build(self):
        self.group = QtWidgets.QButtonGroup(self)
        radios = []
        for i, t in enumerate(model.BACKGROUND_TYPES):
            r = QtWidgets.QRadioButton(t)
            self.group.addButton(r, i + 1)
            radios.append(r)
        self.group.idClicked.connect(self._kind)
        self.body_layout.addWidget(hrow(*radios, None))
        self.path = QtWidgets.QLineEdit()
        self.path.setPlaceholderText("Background image (Custom file)")
        self.path.editingFinished.connect(self._path)
        browse = tool("folder", "Browse for a background image", slot=self._browse)
        clear = tool("close", "Remove background image", size=12, slot=self._clear)
        self.body_layout.addWidget(hrow(clear, self.path, browse, stretch_index=1))

    def fill(self, s):
        b = s["background"]
        t = int(b.get("type", 0)) or 1
        btn = self.group.button(t)
        if btn:
            btn.setChecked(True)
        with Blocker(self.path):
            self.path.setText(b.get("path", ""))

    def _kind(self, i):
        s = self.setup()
        if s:
            s["background"]["type"] = i
            self.sm.changed()

    def _path(self):
        s = self.setup()
        if s and s["background"].get("path") != self.path.text():
            s["background"]["path"] = self.path.text()
            self.sm.changed()

    def _browse(self):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Background image", self.path.text(),
                                                     "Images (*.jpg *.jpeg *.png *.tif *.tga *.bmp *.exr *.hdr);;All (*.*)")
        if f:
            s = self.setup()
            if s:
                s["background"].update(path=f.replace("\\", "/"), type=4)
                self.fill(s)
                self.sm.changed()

    def _clear(self):
        s = self.setup()
        if s:
            s["background"]["path"] = ""
            self.fill(s)
            self.sm.changed()


class AtmosphereCard(Card):
    """Which atmospheric effects (fog, volume light...) are on in this setup."""
    CARD_ID = 20

    def build(self):
        self.add, self.add_menu = menu_tool("add", "Choose atmosphere effects from the scene")
        self.add_menu.aboutToShow.connect(self._fill_menu)
        rm = tool("delete", "Remove the selected effects from this setup", slot=self._remove)
        self.body_layout.addWidget(hrow(muted("Atmosphere effects of this setup"), None, self.add, rm))
        self.table = FlagTable()
        self.table.setMinimumHeight(80)
        self.table.itemChanged.connect(self._changed)
        self.body_layout.addWidget(self.table)

    def fill(self, s):
        items = s["atmosphere"]["set"]
        with Blocker(self.table):
            self.table.clear()
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(["Name", "Active"])
            self.table.setRowCount(len(items))
            for r, a in enumerate(items):
                it = QtWidgets.QTableWidgetItem(a["name"])
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                self.table.setItem(r, 0, it)
                self.table.setItem(r, 1, self.table.flag_item(a.get("active", True)))
            fit_columns(self.table)

    def _fill_menu(self):
        self.add_menu.clear()
        s = self.setup()
        if not s:
            return
        have = set(a["name"] for a in s["atmosphere"]["set"])
        found = maxlink.atmospherics()
        if not found:
            self.add_menu.addAction("There are no atmosphere effects in the scene").setEnabled(False)
        for a in found:
            act = self.add_menu.addAction("%s  [%s]" % (a["name"], a["class"]), lambda a=a: self._add(a))
            act.setEnabled(a["name"] not in have)

    def _add(self, a):
        s = self.setup()
        if s:
            s["atmosphere"]["set"].append({"name": a["name"], "active": a["active"]})
            self.fill(s)
            self.sm.changed()

    def _changed(self, it):
        s = self.setup()
        if s and it.column() == 1:
            s["atmosphere"]["set"][it.row()]["active"] = it.checkState() == QtCore.Qt.Checked
            self.sm.changed()

    def _remove(self):
        s = self.setup()
        if s:
            rows = set(i.row() for i in self.table.selectedItems())
            s["atmosphere"]["set"] = [a for r, a in enumerate(s["atmosphere"]["set"]) if r not in rows]
            self.fill(s)
            self.sm.changed()


class VariantsCard(Card):
    """Layer variants: a group of layers where only the chosen one is visible in this setup."""
    CARD_ID = 30

    def build(self):
        self.box = QtWidgets.QWidget()
        self.box_layout = QtWidgets.QVBoxLayout(self.box)
        self.box_layout.setContentsMargins(0, 0, 0, 0)
        self.box_layout.setSpacing(4)
        self.body_layout.addWidget(self.box)
        add = QtWidgets.QPushButton(icon("add", 14), " Add New Layer Variant")
        add.clicked.connect(self._new)
        self.body_layout.addWidget(add)
        self.body_layout.addStretch(1)

    def fill(self, s):
        while self.box_layout.count():
            w = self.box_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, v in enumerate(s["variants"]["set"]):
            name = QtWidgets.QLineEdit(v.get("name", "Variant"))
            name.editingFinished.connect(lambda e=name, i=i: self._rename(i, e.text()))
            combo = Combo()
            combo.addItems(v.get("layers", []))
            combo.setCurrentIndex(max(0, int(v.get("value", 1)) - 1))
            combo.currentIndexChanged.connect(lambda k, i=i: self._pick(i, k + 1))
            edit_b = tool("layers", "Use the layers selected in the Layer Explorer (or pick from the list)", slot=lambda _=False, i=i: self._layers(i))
            rm = tool("delete", "Delete variation set", slot=lambda _=False, i=i: self._delete(i))
            self.box_layout.addWidget(hrow(name, combo, edit_b, rm, stretch_index=1))

    def _new(self):
        s = self.setup()
        if not s:
            return
        layers = self._choose_layers([])
        if layers:
            s["variants"]["set"].append({"name": "Variant %d" % (len(s["variants"]["set"]) + 1), "layers": layers, "value": 1})
            self.fill(s)
            self.sm.changed()

    def _choose_layers(self, current):
        from .dialogs import Dialog
        dlg = Dialog(self)
        dlg.setWindowTitle("Layers of this variant")
        v = QtWidgets.QVBoxLayout(dlg)
        v.addWidget(muted("Tick the layers that take turns: only one of them is visible per setup."))
        lst = QtWidgets.QListWidget()
        for l in self.sm.scene.layers:
            it = QtWidgets.QListWidgetItem(l["name"])
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if l["name"] in current else QtCore.Qt.Unchecked)
            lst.addItem(it)
        v.addWidget(lst)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.resize(360, 420)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return None
        return [lst.item(i).text() for i in range(lst.count()) if lst.item(i).checkState() == QtCore.Qt.Checked]

    def _layers(self, i):
        s = self.setup()
        if s:
            v = s["variants"]["set"][i]
            layers = self._choose_layers(v.get("layers", []))
            if layers is not None:
                v["layers"] = layers
                v["value"] = min(int(v.get("value", 1)), max(1, len(layers)))
                self.fill(s)
                self.sm.changed()

    def _rename(self, i, t):
        s = self.setup()
        if s:
            s["variants"]["set"][i]["name"] = t
            self.sm.changed(apply=False)

    def _pick(self, i, k):
        s = self.setup()
        if s:
            s["variants"]["set"][i]["value"] = k
            self.sm.changed()

    def _delete(self, i):
        s = self.setup()
        if s:
            del s["variants"]["set"][i]
            self.fill(s)
            self.sm.changed()


class ElementsCard(Card):
    """Which render elements are on in this setup."""
    CARD_ID = 21

    def build(self):
        fetch = QtWidgets.QPushButton(icon("fetch", 14), " Fetch")
        fetch.setToolTip("Take the render elements of the scene as they are now")
        fetch.clicked.connect(self._fetch)
        clear = QtWidgets.QPushButton(icon("close", 12), " Clear")
        clear.clicked.connect(self._clear)
        self.body_layout.addWidget(hrow(fetch, clear))
        self.table = FlagTable()
        self.table.setMinimumHeight(80)
        self.table.itemChanged.connect(self._changed)
        self.body_layout.addWidget(self.table)

    def fill(self, s):
        items = s["elements"]["set"]
        with Blocker(self.table):
            self.table.clear()
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(["Element", "On"])
            self.table.setRowCount(len(items))
            for r, e in enumerate(items):
                it = QtWidgets.QTableWidgetItem(e["name"])
                it.setToolTip(e.get("class", ""))
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                self.table.setItem(r, 0, it)
                self.table.setItem(r, 1, self.table.flag_item(e.get("enabled", True)))
            fit_columns(self.table)

    def _fetch(self):
        s = self.setup()
        if s:
            s["elements"]["set"] = maxlink.elements()
            if not s["elements"]["set"]:
                self.sm.toast("There are no render elements in the scene")
            self.fill(s)
            self.sm.changed()

    def _clear(self):
        s = self.setup()
        if s:
            s["elements"]["set"] = []
            self.fill(s)
            self.sm.changed()

    def _changed(self, it):
        s = self.setup()
        if s and it.column() == 1:
            rows = set(i.row() for i in self.table.selectedItems())
            if it.row() not in rows:
                rows = {it.row()}
            on = it.checkState() == QtCore.Qt.Checked
            for r in rows:
                s["elements"]["set"][r]["enabled"] = on
            if len(rows) > 1:
                self.fill(s)
            self.sm.changed()


class RenderPresetCard(Card):
    """A 3ds Max render preset (.rps) loaded with the setup."""
    CARD_ID = 18

    def build(self):
        self.path = QtWidgets.QLineEdit()
        self.path.setPlaceholderText("Render preset file (.rps)")
        self.path.editingFinished.connect(self._path)
        browse = tool("folder", "Choose a render preset", slot=self._browse)
        save = tool("save", "Save the current render settings as a preset and use it here", slot=self._save)
        clear = tool("close", "Clear", size=12, slot=lambda: self._set(""))
        self.body_layout.addWidget(hrow(clear, self.path, browse, save, stretch_index=1))
        self.state = muted("")
        self.body_layout.addWidget(self.state)

    def fill(self, s):
        p = s["render_preset"].get("path", "")
        with Blocker(self.path):
            self.path.setText(p)
        self.state.setText("" if not p else ("" if os.path.isfile(p) else "This file doesn't exist"))

    def _set(self, p):
        s = self.setup()
        if s:
            s["render_preset"]["path"] = p.replace("\\", "/")
            self.fill(s)
            self.sm.changed()

    def _path(self):
        s = self.setup()
        if s and s["render_preset"].get("path") != self.path.text():
            self._set(self.path.text())

    def _browse(self):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Render preset", self.path.text() or self.sm.scene.folder,
                                                     "Render Presets (*.rps)")
        if f:
            self._set(f)

    def _save(self):
        f, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save render preset", os.path.join(self.sm.scene.folder or "", "setup.rps"),
                                                     "Render Presets (*.rps)")
        if f and maxlink.save_preset(f):
            self._set(f)


class RenderOverrideCard(Card):
    """A default set of render settings (for the whole file) and, per setup, only what differs from it."""
    CARD_ID = 19

    def build(self):
        self.body_layout.addWidget(muted("Default Render Settings (for every setup)"))
        fd = QtWidgets.QPushButton(icon("fetch", 14), " Fetch")
        fd.setToolTip("Take the current render settings as the default")
        fd.clicked.connect(self._fetch_default)
        cd = QtWidgets.QPushButton(icon("close", 12), " Clear")
        cd.clicked.connect(self._clear_default)
        self.body_layout.addWidget(hrow(fd, cd))
        self.default_info = muted("")
        self.body_layout.addWidget(self.default_info)
        self.body_layout.addWidget(muted("Render Settings Overrides (this setup)"))
        fo = QtWidgets.QPushButton(icon("fetch", 14), " Fetch")
        fo.setToolTip("Keep the settings that are now different from the default")
        fo.clicked.connect(self._fetch_over)
        co = QtWidgets.QPushButton(icon("close", 12), " Clear")
        co.clicked.connect(self._clear_over)
        self.body_layout.addWidget(hrow(fo, co))
        self.list = QtWidgets.QListWidget()
        self.list.setMinimumHeight(60)
        self.body_layout.addWidget(self.list)

    def fill(self, s):
        if s is None:
            return
        d = self.sm.rs_default
        self.default_info.setText("%d settings stored" % len(d) if d else "You have no default render settings yet!")
        self.list.clear()
        for k, v in sorted(s["rs_override"]["set"].items()):
            self.list.addItem("%s = %s" % (k, v))
        if not s["rs_override"]["set"]:
            self.list.addItem("You have no overrides in this setup")

    def _fetch_default(self):
        self.sm.rs_default = maxlink.rs_snapshot()
        self.sm.changed(apply=False)
        self.fill(self.setup())

    def _clear_default(self):
        self.sm.rs_default = {}
        self.sm.changed(apply=False)
        self.fill(self.setup())

    def _fetch_over(self):
        s = self.setup()
        if not s:
            return
        if not self.sm.rs_default:
            self.sm.toast("Fetch the default render settings first")
            return
        now = maxlink.rs_snapshot()
        s["rs_override"]["set"] = {k: v for k, v in now.items() if self.sm.rs_default.get(k) != v}
        self.fill(s)
        self.sm.changed()

    def _clear_over(self):
        s = self.setup()
        if s:
            s["rs_override"]["set"] = {}
            self.fill(s)
            self.sm.changed()


class PostSection(QtWidgets.QFrame):
    """One category of the VFB: its name, an eyedropper that takes it from the VFB, and its values to edit."""

    def __init__(self, card, key):
        super(PostSection, self).__init__()
        self.card = card
        self.key = key
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 4)
        v.setSpacing(3)
        self.title = QtWidgets.QLabel(model.POST_TITLES[key])
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        take = tool("fetch", "Eyedropper: take the %s that is on in the VFB, with its values" % model.POST_TITLES[key], slot=lambda: card.take(key))
        drop = tool("close", "Stop controlling this category in this setup", size=11, slot=lambda: card.drop(key))
        self.drop = drop
        v.addWidget(hrow(self.title, None, take, drop))
        self.box = QtWidgets.QWidget()
        self.grid = QtWidgets.QGridLayout(self.box)
        self.grid.setContentsMargins(6, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(2)
        self.grid.setColumnStretch(1, 1)
        v.addWidget(self.box)

    def clear(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()

    def header(self, r, text):
        l = QtWidgets.QLabel(text)
        l.setEnabled(False)
        self.grid.addWidget(l, r, 0, 1, 2)

    def small_editor(self, name, value, on_change):
        """A compact editor for one value of a line with several: tick box, small number box or colour."""
        if isinstance(value, bool):
            ed = QtWidgets.QCheckBox()
            ed.setChecked(value)
            ed.toggled.connect(lambda v: on_change(bool(v)))
        elif isinstance(value, dict) and "$color" in value:
            ed = ColorButton()
            c = value["$color"]
            ed.set_color(QtGui.QColor(int(c[0]), int(c[1]), int(c[2])).name())
            ed.changed.connect(lambda hexa: on_change({"$color": [QtGui.QColor(hexa).red(), QtGui.QColor(hexa).green(), QtGui.QColor(hexa).blue()]}))
        elif isinstance(value, (int, float)):
            lo, hi = model.post_range(name, value)
            if isinstance(value, int):
                ed = Spin()
                ed.setRange(int(lo), int(hi))
            else:
                ed = DoubleSpin()
                ed.setRange(lo, hi)
                ed.setDecimals(3 if hi - lo <= 2 else 2)
                ed.setSingleStep(0.01 if hi - lo <= 10 else 0.1)
            ed.setValue(value)
            ed.setKeyboardTracking(False)
            ed.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            ed.setFixedWidth(58)
            ed.valueChanged.connect(on_change)
        else:
            ed = QtWidgets.QLineEdit(str(value))
            ed.editingFinished.connect(lambda e=ed: on_change(e.text()))
        return ed

    def line_row(self, r, label, pairs):
        """One line for an operator with several values: its name, then 'short name + editor' for each, wrapping
        to a new line only when the card is too narrow."""
        box = QtWidgets.QWidget()
        flow = FlowLayout(box, hspacing=10)
        for short, name, value, on_change in pairs:
            flow.addWidget(hrow(QtWidgets.QLabel(short), self.small_editor(name, value, on_change), spacing=3))
        if label is not None:
            self.grid.addWidget(QtWidgets.QLabel(label), r, 0, QtCore.Qt.AlignTop)
            self.grid.addWidget(box, r, 1, 1, 2)
        else:
            self.grid.addWidget(box, r, 0, 1, 3)

    def lut_rows(self, r, props, on_change):
        """LUT: its name and file on one line; Lin, Log and Opacity together on the next one."""
        path = props.get("colorMappingOperator_path") or ""
        name = QtWidgets.QLabel(os.path.basename(path) or "(no file)")
        name.setToolTip(path or "No LUT file")
        name.setMinimumWidth(20)
        name.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)

        def browse():
            f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "LUT file", os.path.dirname(path), LUT_FILES)
            if f:
                on_change("colorMappingOperator_path", os.path.normpath(f))
                self.card.refresh()
        pick = tool("folder", "Choose the LUT file", size=14, slot=browse)
        self.grid.addWidget(QtWidgets.QLabel("LUT"), r, 0)
        self.grid.addWidget(hrow(name, pick, stretch_index=0), r, 1, 1, 2)
        pairs = []
        for n in ("colorMappingOperator_linear", "colorMappingOperator_logarithmic", "colorMappingOperator_opacity"):
            if n in props:
                leaf = n.split("_")[-1]
                pairs.append((POST_SHORT.get(leaf, model.post_label(n)), n, props[n], lambda x, n=n: on_change(n, x)))
        if pairs:
            self.line_row(r + 1, "", pairs)
            return r + 2
        return r + 1

    def value_row(self, r, label, value, on_change):
        """An editor that fits the value: tick box, slider and number, colour or text."""
        l = QtWidgets.QLabel(label)
        if isinstance(value, bool):
            ed = QtWidgets.QCheckBox()
            ed.setChecked(value)
            ed.toggled.connect(lambda v: on_change(bool(v)))
        elif isinstance(value, dict) and "$color" in value:
            ed = ColorButton()
            c = value["$color"]
            ed.set_color(QtGui.QColor(int(c[0]), int(c[1]), int(c[2])).name())

            def from_button(hexa):
                q = QtGui.QColor(hexa)
                on_change({"$color": [q.red(), q.green(), q.blue()]})
            ed.changed.connect(from_button)
            ed = hrow(ed, None)
        elif isinstance(value, (int, float)):
            ed = NumberRow(*self.card.value_range(label, value), integer=isinstance(value, int))
            ed.set_value(value)
            ed.changed.connect(on_change)
        else:
            ed = QtWidgets.QLineEdit(str(value))
            ed.editingFinished.connect(lambda e=ed: on_change(e.text()))
        self.grid.addWidget(l, r, 0)
        self.grid.addWidget(ed, r, 1)


class PostCard(Card):
    """Corona post-production of the VFB by category, like the VFB shows it: tone mapping (each operator that is on,
    with its values), LightMix, bloom and glare... An eyedropper takes a category; its values can then be edited here."""
    CARD_ID = 29

    def build(self):
        fetch = QtWidgets.QPushButton(icon("fetch", 14), " Fetch VFB")
        fetch.setToolTip("Take every category that is on in the VFB, with its values")
        fetch.clicked.connect(self._fetch_all)
        clear = QtWidgets.QPushButton(icon("close", 12), " Clear")
        clear.clicked.connect(self._clear)
        self.body_layout.addWidget(hrow(fetch, clear, None))
        self.note = muted("")
        self.body_layout.addWidget(self.note)
        self.sections = {}
        for key in model.POST_ORDER:
            sec = PostSection(self, key)
            self.sections[key] = sec
            self.body_layout.addWidget(sec)
        self._ranges = {}

    def value_range(self, label, value):
        return self._ranges.get(label) or model.post_range(label.replace(" ", ""), value)

    def fill(self, s):
        p = s["post"]
        cats = p.get("cats") or {}
        self.note.setText("Stored by an older version: press Fetch VFB to see it by category." if (p.get("conf") and not cats) else "")
        self.note.setVisible(bool(p.get("conf") and not cats))
        for key, sec in self.sections.items():
            sec.clear()
            data = cats.get(key)
            sec.box.setVisible(bool(data))
            sec.drop.setVisible(bool(data))
            if data:
                getattr(self, "_fill_" + key if key in ("tonemap", "lightmix") else "_fill_props")(sec, key, data)

    def _fill_tonemap(self, sec, key, data):
        """Each operator that is on, without a title of its own: one value -> a row named after the operator; several
        -> one line with all of them; LUT -> its file, then Lin / Log / Opacity in one line."""
        r = 0
        for i, op in enumerate(data.get("ops", [])):
            title = model.POST_OPERATORS.get(op["class"], op["class"].replace("OperatorPlugin", ""))
            props = op["props"]
            vals = [(n, v) for n, v in props.items() if not n.endswith(("_enabled", "_id", "_nextOperator"))]
            if op["class"] == "LutOperatorPlugin":
                r = sec.lut_rows(r, props, lambda n, x, i=i: self._set_op(i, n, x))
                continue
            if not vals:
                continue
            if len(vals) == 1:
                n, v = vals[0]
                self._ranges[title] = model.post_range(n, v)
                sec.value_row(r, title, v, lambda x, i=i, n=n: self._set_op(i, n, x))
            else:
                pairs = []
                for n, v in vals:
                    leaf = n.split("_")[-1]
                    pairs.append((POST_SHORT.get(leaf, model.post_label(n)), n, v, lambda x, i=i, n=n: self._set_op(i, n, x)))
                sec.line_row(r, title, pairs)
            r += 1
        if not r:
            sec.header(0, "No operator is on")

    def _fill_lightmix(self, sec, key, data):
        a = data.get("arrays", {})
        names = a.get("colormap_lightselect_elementNames", [])
        vals = a.get("colorMap_lightmixIntensities", [])
        cols = a.get("colorMap_lightmixColors", [])
        if not vals:
            sec.header(0, "There are no LightMix channels")
        for i, v in enumerate(vals):
            label = names[i] if i < len(names) else "Channel %d" % (i + 1)
            self._ranges[label] = (0.0, max(10.0, float(v)))
            sec.value_row(i, label, float(v), lambda x, i=i: self._set_lm("colorMap_lightmixIntensities", i, x))
            if i < len(cols):
                # the tint goes at the end of the same line
                tint = sec.small_editor("tint", {"$color": cols[i]}, lambda x, i=i: self._set_lm("colorMap_lightmixColors", i, x["$color"]))
                tint.setToolTip("Tint of %s" % label)
                sec.grid.addWidget(tint, i, 2)

    def _fill_props(self, sec, key, data):
        for r, (n, v) in enumerate(self._ordered(key, data)):
            label = model.post_label(n)
            if isinstance(v, bool) and label in ("Enabled", "Enable", "On"):
                label = "On"
            self._ranges[label] = model.post_range(n, v)
            sec.value_row(r, label, v, lambda x, n=n: self._set_prop(key, n, x))

    def _ordered(self, key, data):
        names = next((x for k, _, x in model.POST_CATS if k == key), [])
        return [(n, data["props"][n]) for n in names if n in data["props"]]

    def _post(self):
        s = self.setup()
        return s["post"].setdefault("cats", {}) if s else None

    def _set_op(self, i, n, v):
        self._post()["tonemap"]["ops"][i]["props"][n] = v
        self.sm.changed(list_too=False)

    def _set_lm(self, name, i, v):
        self._post()["lightmix"]["arrays"][name][i] = v
        self.sm.changed(list_too=False)

    def _set_prop(self, key, n, v):
        self._post()[key]["props"][n] = v
        self.sm.changed(list_too=False)

    def take(self, key):
        s = self.setup()
        if not s:
            return
        data = maxlink.read_post(key)
        if not data:
            self.sm.toast("Corona didn't give %s (is Corona the renderer?)" % model.POST_TITLES[key])
            return
        s["post"].setdefault("cats", {})[key] = data
        s["post"]["conf"] = ""
        self.fill(s)
        self.sm.changed()

    def drop(self, key):
        s = self.setup()
        if s:
            s["post"].setdefault("cats", {}).pop(key, None)
            self.fill(s)
            self.sm.changed()

    def _fetch_all(self):
        s = self.setup()
        if not s:
            return
        cats = {}
        for key in model.POST_ORDER:
            data = maxlink.read_post(key, only_active=key != "tonemap")
            if data:
                cats[key] = data
        s["post"].update(cats=cats, conf="", lightmix={})
        self.fill(s)
        self.sm.changed()

    def _clear(self):
        s = self.setup()
        if s:
            s["post"].update(conf="", lightmix={}, cats={})
            self.fill(s)
            self.sm.changed()


class ScriptFileCard(Card):
    """MAXScript files run before / after each render of this setup."""
    CARD_ID = 17

    def build(self):
        self.rows = {}
        for key, title in (("pre_render", "Pre-Render"), ("post_render", "Post-Render")):
            cb = QtWidgets.QCheckBox(title)
            cb.toggled.connect(lambda v, k=key: self._toggle(k, v))
            path = QtWidgets.QLineEdit()
            path.setPlaceholderText("MAXScript file (.ms, .mse, .py)")
            path.editingFinished.connect(lambda k=key, e=path: self._path(k, e.text()))
            browse = tool("folder", "Choose a script", slot=lambda _=False, k=key: self._browse(k))
            self.body_layout.addWidget(cb)
            self.body_layout.addWidget(hrow(path, browse, stretch_index=0))
            self.rows[key] = (cb, path)
        self.body_layout.addStretch(1)

    def fill(self, s):
        for key, (cb, path) in self.rows.items():
            d = s["scripts"][key]
            with Blocker(cb, path):
                cb.setChecked(bool(d.get("enabled")))
                path.setText(d.get("path", ""))

    def _toggle(self, k, v):
        s = self.setup()
        if s:
            s["scripts"][k]["enabled"] = bool(v)
            self.sm.changed()

    def _path(self, k, t):
        s = self.setup()
        if s and s["scripts"][k].get("path") != t:
            s["scripts"][k]["path"] = t
            if t.strip():
                self.sm.trust_scripts([("file", t)])  # a file you typed or chose is yours
            self.sm.changed()

    def _browse(self, k):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Script", self.sm.scene.folder, "Scripts (*.ms *.mse *.py);;All (*.*)")
        if f:
            s = self.setup()
            if s:
                s["scripts"][k].update(path=f.replace("\\", "/"), enabled=True)
                self.sm.trust_scripts([("file", s["scripts"][k]["path"])])
                self.fill(s)
                self.sm.changed()


class ScriptEditorCard(Card):
    """MAXScript typed here, run before / after the setup is applied and before / after each render."""
    CARD_ID = 22
    TABS = (("pre_setup", "Pre-Setup"), ("post_setup", "Post-Setup"), ("pre_render", "Pre-Render"), ("post_render", "Post-Render"))

    def build(self):
        self.tabs = TabBar()
        for _, t in self.TABS:
            self.tabs.addTab(t)
        self.tabs.currentChanged.connect(lambda i: self.fill(self.setup()) if self.setup() else None)
        test = QtWidgets.QToolButton()
        test.setText(" Test")
        test.setIcon(icon("play", 14))
        test.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        test.setAutoRaise(True)
        test.setToolTip("Run this script now")
        test.clicked.connect(self._test)
        self.body_layout.addWidget(hrow(self.tabs, None, test))
        self.edit = QtWidgets.QPlainTextEdit()
        f = QtGui.QFont("Consolas")
        f.setStyleHint(QtGui.QFont.Monospace)
        self.edit.setFont(f)
        self.edit.setPlaceholderText('print "Hello World"')
        self.edit.textChanged.connect(self._changed)
        self.body_layout.addWidget(self.edit, 1)

    def key(self):
        return self.TABS[max(0, self.tabs.currentIndex())][0]

    def fill(self, s):
        t = s["snippet"].get(self.key(), "")
        if self.edit.toPlainText() != t:
            with Blocker(self.edit):
                self.edit.setPlainText(t)

    def _changed(self):
        s = self.setup()
        if s:
            s["snippet"][self.key()] = self.edit.toPlainText()
            self.sm.typed_code(s["id"], self.key(), s["snippet"][self.key()])
            self.sm.changed(apply=False, list_too=False)

    def _test(self):
        maxlink.run_code(self.edit.toPlainText())
        self.sm.toast("Script run (see the MAXScript Listener for its output)")


class ThumbnailCard(Card):
    """A picture of the setup: from the viewport or from the last render."""
    CARD_ID = 31

    def build(self):
        fv = QtWidgets.QPushButton(icon("photo", 14), " Fetch Viewport")
        fv.clicked.connect(lambda: self.sm.fetch_thumbnail(self.setup(), "viewport"))
        fr = QtWidgets.QPushButton(icon("image", 14), " Fetch VFB")
        fr.clicked.connect(lambda: self.sm.fetch_thumbnail(self.setup(), "vfb"))
        self.body_layout.addWidget(hrow(fv, fr))
        self.pic = QtWidgets.QLabel()
        self.pic.setAlignment(QtCore.Qt.AlignCenter)
        self.pic.setMinimumHeight(80)
        self.pic.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.pic.grows = True
        self.body_layout.addWidget(self.pic, 1)

    def fill(self, s):
        p = s.get("thumbnail", "")
        if p and os.path.isfile(p):
            pm = QtGui.QPixmap(p)
            w = max(80, self.pic.width() or 300)
            self.pic.setPixmap(pm.scaled(w, max(60, self.pic.height() or 160), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        else:
            self.pic.setPixmap(QtGui.QPixmap())
            self.pic.setText("No thumbnail yet")

    def resizeEvent(self, e):
        super(ThumbnailCard, self).resizeEvent(e)
        if self.setup():
            QtCore.QTimer.singleShot(0, lambda: self.setup() and self.fill(self.setup()))


CARD_CLASSES = [BackgroundCard, AtmosphereCard, VariantsCard, ElementsCard, RenderPresetCard, RenderOverrideCard,
                PostCard, ScriptFileCard, ScriptEditorCard, ThumbnailCard]
