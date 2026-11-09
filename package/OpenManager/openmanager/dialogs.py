"""Dialogs: Batch Render progress, Property Selector, Settings (the gear) and Bake Setups."""
from PySide6 import QtCore, QtGui, QtWidgets

from . import model
from .widgets import Combo

WM_CLOSE, WM_SYSCOMMAND, SC_CLOSE = 0x0010, 0x0112, 0xF060


class Dialog(QtWidgets.QDialog):
    """A window of its own with a title bar whose X works. 3ds Max can swallow the close that Qt would make from
    it, so the message from Windows is taken directly: the X does what Cancel does."""

    def __init__(self, parent=None):
        super(Dialog, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.WindowTitleHint | QtCore.Qt.WindowSystemMenuHint | QtCore.Qt.WindowCloseButtonHint)

    def nativeEvent(self, event_type, message):
        try:
            if event_type == b"windows_generic_MSG" or bytes(event_type) == b"windows_generic_MSG":
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_CLOSE or (msg.message == WM_SYSCOMMAND and (msg.wParam & 0xFFF0) == SC_CLOSE):
                    QtCore.QTimer.singleShot(0, self.close_from_title_bar)
                    return True, 0
        except Exception:
            pass
        return super(Dialog, self).nativeEvent(event_type, message)

    def close_from_title_bar(self):
        self.reject()

DEFAULT_SETTINGS_MAX = {
    "viewport_update_type": 0, "viewport_refresh": True, "ipr_corona_restart": False, "ipr_vray_resolution": True,
    "update_time_output_type": False, "animate_camera": False, "restore_base": True,
    "scripts": "ask",
}
SCRIPT_POLICIES = [("ask", "Show them and ask before they run"), ("always", "Always run them"),
                   ("never", "Never run them")]


def hrow_label(text, w):
    row = QtWidgets.QWidget()
    h = QtWidgets.QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(QtWidgets.QLabel(text))
    h.addWidget(w, 1)
    return row


DEFAULT_THEME = {"main": "auto", "header": "colored"}
COLUMNS = [("name", "Scene Name"), ("camera", "Camera"), ("resolution", "Resolution"), ("sun", "Sun"),
           ("dome", "Dome"), ("environment", "Environment"), ("frame", "Frame"), ("id", "Id")]
DEFAULT_COLUMNS = {"name": True, "camera": True, "resolution": True, "sun": True, "dome": False,
                   "environment": True, "frame": False, "id": False}


class BatchDialog(Dialog):
    def __init__(self, parent, total, title="Batch Render", task="Rendering"):
        super(BatchDialog, self).__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        v = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Current Task: %s" % task))
        row.addStretch(1)
        self.job = QtWidgets.QLabel("")
        row.addWidget(self.job)
        v.addLayout(row)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setRange(0, total)
        self.bar.setValue(0)
        v.addWidget(self.bar)
        b = QtWidgets.QHBoxLayout()
        b.addStretch(1)
        self.cancel = QtWidgets.QPushButton("Cancel")
        b.addWidget(self.cancel)
        v.addLayout(b)

    def close_from_title_bar(self):
        self.cancel.click()  # the X of a running batch cancels it

    def set_job(self, label, done, total):
        self.job.setText("%s[%d / %d]" % (label, done, total))
        self.bar.setValue(done)


STATUS_COLORS = {"Ready": "#23d160", "Saved": "#23d160", "Warning": "#ffb020", "Skipped": "#ff3860",
                 "Failed": "#ff3860", "Not rendered": "#9a9a9a"}


def _job_table(rows):
    """rows: (label, status, details); details is a list of lines."""
    t = QtWidgets.QTreeWidget()
    t.setColumnCount(3)
    t.setHeaderLabels(["Setup", "Status", "Details"])
    t.setRootIsDecorated(False)
    t.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
    t.setWordWrap(True)
    for label, status, details in rows:
        it = QtWidgets.QTreeWidgetItem([label, status, "\n".join(details)])
        it.setForeground(1, QtGui.QBrush(QtGui.QColor(STATUS_COLORS.get(status, "#9a9a9a"))))
        it.setToolTip(2, "\n".join(details))
        t.addTopLevelItem(it)
    h = t.header()
    h.setStretchLastSection(True)
    t.resizeColumnToContents(0)
    t.resizeColumnToContents(1)
    t.setColumnWidth(0, min(260, t.columnWidth(0) + 12))
    t.setColumnWidth(1, t.columnWidth(1) + 16)
    return t


class ScriptReviewDialog(Dialog):
    """Scripts that came with the file, shown before they run for the first time."""

    def __init__(self, parent, rows):
        """rows: (setup label, slot, kind, text)."""
        super(ScriptReviewDialog, self).__init__(parent)
        self.setWindowTitle("Scripts in this file")
        self.resize(720, 520)
        v = QtWidgets.QVBoxLayout(self)
        msg = QtWidgets.QLabel(
            "These setups run MAXScript that came with the file. A script can do anything 3ds Max can, like "
            "deleting files, so only run scripts you trust. OpenManager remembers your answer for these scripts; "
            "if one changes, it asks again.")
        msg.setWordWrap(True)
        v.addWidget(msg)
        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        f = QtGui.QFont("Consolas")
        f.setStyleHint(QtGui.QFont.Monospace)
        text.setFont(f)
        blocks = []
        for label, slot, kind, body in rows:
            head = "-- %s · %s" % (label, slot)
            blocks.append("%s\n%s" % (head, ("fileIn @\"%s\"" % body) if kind == "file" else body.rstrip()))
        text.setPlainText("\n\n".join(blocks))
        v.addWidget(text, 1)
        bb = QtWidgets.QDialogButtonBox()
        run = bb.addButton("Run these scripts", QtWidgets.QDialogButtonBox.AcceptRole)
        skip = bb.addButton("Don't run them", QtWidgets.QDialogButtonBox.RejectRole)
        skip.setDefault(True)
        run.clicked.connect(self.accept)
        skip.clicked.connect(self.reject)
        v.addWidget(bb)


class BatchCheckDialog(Dialog):
    """Shown before a batch when some setup can't be rendered as asked: what is skipped and why."""

    def __init__(self, parent, rows, runnable):
        super(BatchCheckDialog, self).__init__(parent)
        self.setWindowTitle("Batch Render: check")
        self.resize(760, 360)
        v = QtWidgets.QVBoxLayout(self)
        skipped = sum(1 for r in rows if r[1] == "Skipped")
        msg = QtWidgets.QLabel(("%d setup(s) can't be rendered and will be skipped. " % skipped if skipped else "")
                               + "Fix them in their cards, or render the others now.")
        msg.setWordWrap(True)
        v.addWidget(msg)
        v.addWidget(_job_table(rows), 1)
        bb = QtWidgets.QDialogButtonBox()
        self.go = bb.addButton("Render %d setup(s)" % runnable, QtWidgets.QDialogButtonBox.AcceptRole)
        self.go.setEnabled(runnable > 0)
        self.go.setDefault(runnable > 0)
        bb.addButton(QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)


class BatchReportDialog(Dialog):
    """Shown when a batch ends: what every setup did, where it saved, what went wrong."""

    def __init__(self, parent, rows, summary):
        super(BatchReportDialog, self).__init__(parent)
        self.setWindowTitle("Batch Render: report")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.resize(820, 380)
        v = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QLabel(summary)
        head.setWordWrap(True)
        v.addWidget(head)
        v.addWidget(_job_table(rows), 1)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.close)
        v.addWidget(bb)

    def close_from_title_bar(self):
        self.close()


class PropertySelector(Dialog):
    def __init__(self, parent, title, tabs, checked, start_tab):
        super(PropertySelector, self).__init__(parent)
        self.setWindowTitle("%s | Property Selector" % title)
        self.resize(700, 480)
        self.result_keys = None
        v = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        self.boxes = []
        on = set(checked)
        for t in tabs:
            page = QtWidgets.QWidget()
            grid = QtWidgets.QGridLayout(page)
            grid.setAlignment(QtCore.Qt.AlignTop)
            for i, p in enumerate(t["props"]):
                key = model.prop_key(t, p)
                cb = QtWidgets.QCheckBox(p.get("long") or p["name"])
                cb.setToolTip("%s  (%s)" % (p["name"], p["class"]))
                cb.setChecked(key in on)
                cb.setProperty("key", key)
                if p["name"] == "name":
                    cb.setChecked(True)
                    cb.setEnabled(False)
                grid.addWidget(cb, i // 3, i % 3)
                self.boxes.append(cb)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, t["name"])
        if not tabs:
            self.tabs.addTab(QtWidgets.QLabel("  Sorry, no props for this type."), "-")
        self.tabs.setCurrentIndex(start_tab)
        v.addWidget(self.tabs)
        row = QtWidgets.QHBoxLayout()
        reset = QtWidgets.QPushButton("Reset")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        allb = QtWidgets.QPushButton("Tick this tab")
        allb.clicked.connect(lambda: self._tick_tab(True))
        noneb = QtWidgets.QPushButton("Untick this tab")
        noneb.clicked.connect(lambda: self._tick_tab(False))
        row.addWidget(allb)
        row.addWidget(noneb)
        row.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QtWidgets.QPushButton("Ok")
        ok.setDefault(True)
        ok.clicked.connect(self._ok)
        row.addWidget(cancel)
        row.addWidget(ok)
        v.addLayout(row)

    def _tick_tab(self, on):
        page = self.tabs.currentWidget()
        for cb in page.findChildren(QtWidgets.QCheckBox):
            if cb.isEnabled():
                cb.setChecked(on)

    def _reset(self):
        self.result_keys = []
        self.accept()

    def _ok(self):
        self.result_keys = [b.property("key") for b in self.boxes if b.isChecked()]
        self.accept()


class SettingsDialog(Dialog):
    """The gear: theme, viewport behaviour, interactive rendering, list columns, resolution presets."""

    def __init__(self, parent, settings):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(900, 720)
        self.settings = settings
        mx = dict(DEFAULT_SETTINGS_MAX, **settings.get("max", {}))
        th = dict(DEFAULT_THEME, **settings.get("theme", {}))
        cols = dict(DEFAULT_COLUMNS, **settings.get("columns_visible", {}))
        outer = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        page = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page)
        form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignTop)
        form.setVerticalSpacing(10)
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)

        def section(text):
            l = QtWidgets.QLabel(text)
            f = l.font()
            f.setBold(True)
            l.setFont(f)
            return l

        # Notification
        self.notify = QtWidgets.QCheckBox("Ask to open the window when a file with setups is opened")
        self.notify.setChecked(bool(settings.get("notify", True)))
        form.addRow(section("Notification"), self.notify)
        # Theme
        self.main = Combo()
        self.main.addItems(["Follow 3ds Max", "Light", "Dark"])
        self.main.setCurrentIndex({"auto": 0, "light": 1, "dark": 2}.get(th["main"], 0))
        self.start_theme = th["main"]
        # the theme changes as soon as it is chosen; closing with the X puts the old one back
        self.main.currentIndexChanged.connect(lambda i: parent.set_theme(["auto", "light", "dark"][i]))
        self.header = Combo()
        self.header.addItems(["Colored", "Default"])
        self.header.setCurrentIndex(0 if th["header"] != "default" else 1)
        tw = QtWidgets.QWidget()
        tl = QtWidgets.QFormLayout(tw)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addRow("Main", self.main)
        tl.addRow("Module Headers", self.header)
        form.addRow(section("Theme"), tw)
        # Setups
        self.restore_base = QtWidgets.QCheckBox("Put back what the previous setup changed and the new one doesn't control")
        self.restore_base.setToolTip("On: every setup starts from the scene as it was before any setup.\n"
                                     "Off: a setup only changes its own cards; the rest stays as the previous setup left it.\n"
                                     "Viewport camera and background, scripts and render presets are never put back.")
        self.restore_base.setChecked(bool(mx["restore_base"]))
        sw = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.restore_base)
        self.scripts = Combo()
        self.scripts.addItems([t for _, t in SCRIPT_POLICIES])
        self.scripts.setCurrentIndex(next((i for i, (k, _) in enumerate(SCRIPT_POLICIES) if k == mx["scripts"]), 0))
        self.scripts.setToolTip("Scripts of the Script Editor and Script File cards. The ones you write or choose\n"
                                "yourself always run; this is about the ones that came with a file.")
        sl.addWidget(hrow_label("Scripts that came with a file", self.scripts))
        form.addRow(section("Setups"), sw)
        # Time output
        self.time_type = QtWidgets.QCheckBox("Update Time Output Type (Single/Range/List) on setup change")
        self.time_type.setChecked(bool(mx["update_time_output_type"]))
        form.addRow(section("Time Output"), self.time_type)
        # Viewport
        vw = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(vw)
        vl.setContentsMargins(0, 0, 0, 0)
        self.vp_group = QtWidgets.QButtonGroup(self)
        for i, t in enumerate(["Switch the currently Active Viewport",
                               "Only switch if the Active Viewport is Perspective, Camera or Orthographic",
                               "Switch to the locked View to Render, based on the Render Settings Dialog"]):
            r = QtWidgets.QRadioButton(t)
            self.vp_group.addButton(r, i)
            vl.addWidget(r)
        self.vp_group.button(int(mx["viewport_update_type"])).setChecked(True)
        self.redraw = QtWidgets.QCheckBox("Redraw viewport after switching setup")
        self.redraw.setChecked(bool(mx["viewport_refresh"]))
        vl.addWidget(self.redraw)
        form.addRow(section("Viewport"), vw)
        # Interactive rendering
        iw = QtWidgets.QWidget()
        il = QtWidgets.QVBoxLayout(iw)
        il.setContentsMargins(0, 0, 0, 0)
        self.ipr_corona = QtWidgets.QCheckBox("Corona Interactive: stop and restart it after the setup is applied")
        self.ipr_corona.setChecked(bool(mx["ipr_corona_restart"]))
        self.ipr_vray = QtWidgets.QCheckBox("V-Ray IPR: update resolution while switching setups")
        self.ipr_vray.setChecked(bool(mx["ipr_vray_resolution"]))
        il.addWidget(self.ipr_corona)
        il.addWidget(self.ipr_vray)
        form.addRow(section("Interactive Rendering"), iw)
        # Columns
        cw = QtWidgets.QWidget()
        cl = QtWidgets.QGridLayout(cw)
        cl.setContentsMargins(0, 0, 0, 0)
        self.col_boxes = {}
        for i, (k, t) in enumerate(COLUMNS):
            cb = QtWidgets.QCheckBox(t)
            cb.setChecked(bool(cols.get(k)))
            cl.addWidget(cb, i // 3, i % 3)
            self.col_boxes[k] = cb
        form.addRow(section("Columns"), cw)
        # Resolution presets
        self.presets = QtWidgets.QPlainTextEdit()
        self.presets.setFixedHeight(130)
        pres = settings.get("resolution_presets") or [list(x) for x in model.RESOLUTION_PRESETS]
        self.presets.setPlainText("\n".join("%d x %d" % (w, h) for w, h in pres))
        self.presets.setToolTip("One preset per line: width x height")
        form.addRow(section("Resolution Presets"), self.presets)

        row = QtWidgets.QHBoxLayout()
        self.factory = QtWidgets.QPushButton("Factory Reset")
        self.factory.setToolTip("Every setting, the card layout and the Property Selector ticks back to how they come")
        self.reset_def = QtWidgets.QPushButton("Reset to Default")
        self.reset_def.setToolTip("Back to the settings you saved as default")
        self.save_def = QtWidgets.QPushButton("Save as Default")
        self.save_def.setToolTip("Remember these settings, the card layout and the ticks as your default")
        row.addWidget(self.factory)
        row.addWidget(self.reset_def)
        row.addWidget(self.save_def)
        row.addStretch(1)
        ok = QtWidgets.QPushButton("Ok")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        outer.addLayout(row)
        self.action = None
        self.factory.clicked.connect(lambda: self._done("factory"))
        self.reset_def.clicked.connect(lambda: self._done("reset"))
        self.save_def.clicked.connect(lambda: self._done("save_default"))

    def _done(self, what):
        self.action = what
        self.accept()

    def reject(self):
        self.parent().set_theme(self.start_theme)
        super(SettingsDialog, self).reject()

    def values(self):
        pres = []
        for line in self.presets.toPlainText().splitlines():
            parts = [x for x in line.lower().replace("*", "x").replace(" ", "").split("x") if x]
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                pres.append([int(parts[0]), int(parts[1])])
        return {
            "notify": self.notify.isChecked(),
            "theme": {"main": ["auto", "light", "dark"][self.main.currentIndex()],
                      "header": "colored" if self.header.currentIndex() == 0 else "default"},
            "max": {"viewport_update_type": self.vp_group.checkedId(), "viewport_refresh": self.redraw.isChecked(),
                    "ipr_corona_restart": self.ipr_corona.isChecked(), "ipr_vray_resolution": self.ipr_vray.isChecked(),
                    "update_time_output_type": self.time_type.isChecked(), "animate_camera": False,
                    "restore_base": self.restore_base.isChecked(),
                    "scripts": SCRIPT_POLICIES[self.scripts.currentIndex()][0]},
            "columns_visible": {k: cb.isChecked() for k, cb in self.col_boxes.items()},
            "resolution_presets": pres or [list(x) for x in model.RESOLUTION_PRESETS],
        }


class BakeDialog(Dialog):
    """Bake Setups: turn the setups into something that renders without the window."""
    METHODS = ["Convert to 3ds Max Batch Render (scene state + view per setup)",
               "Export 3ds Max (.max), one file per setup",
               "Export Corona Scene (.scn), one file per setup",
               "Run Custom MAXScript on every setup"]

    def __init__(self, parent, setups, folder):
        super(BakeDialog, self).__init__(parent)
        self.setWindowTitle("Bake Setups")
        self.resize(560, 520)
        v = QtWidgets.QVBoxLayout(self)
        v.addWidget(QtWidgets.QLabel("Setups"))
        self.list = QtWidgets.QListWidget()
        for i, s in enumerate(setups):
            it = QtWidgets.QListWidgetItem("%d  %s" % (i + 1, s.get("_label", "")))
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if s.get("render", True) else QtCore.Qt.Unchecked)
            it.setData(QtCore.Qt.UserRole, s["id"])
            self.list.addItem(it)
        v.addWidget(self.list, 1)
        v.addWidget(QtWidgets.QLabel("Method"))
        self.method = Combo()
        self.method.addItems(self.METHODS)
        v.addWidget(self.method)
        self.folder = QtWidgets.QLineEdit(folder)
        self.folder.setPlaceholderText("Folder for exported files")
        b = QtWidgets.QToolButton()
        b.setText("...")
        b.clicked.connect(self._browse)
        fr = QtWidgets.QHBoxLayout()
        fr.addWidget(QtWidgets.QLabel("Folder"))
        fr.addWidget(self.folder, 1)
        fr.addWidget(b)
        v.addLayout(fr)
        self.code = QtWidgets.QPlainTextEdit()
        self.code.setPlaceholderText("MAXScript run after each setup is applied (Run Custom MAXScript)")
        self.code.setFixedHeight(90)
        v.addWidget(self.code)
        self.note = QtWidgets.QLabel()
        self.note.setWordWrap(True)
        self.note.setEnabled(False)
        v.addWidget(self.note)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.method.currentIndexChanged.connect(self._method)
        self._method(0)

    def _method(self, i):
        self.code.setVisible(i == 3)
        self.folder.setEnabled(i in (1, 2))
        self.note.setText([
            "A scene state and a render preset are made for each setup and added to Rendering > Batch Render, "
            "so the setups can go to Backburner or any render farm. Atmosphere, Background, Scripts, Xref, "
            "object transforms and Corona LightMix can't be carried over this way.",
            "Each setup is applied and the scene is saved as a copy. This can take a while on big files.",
            "Each setup is applied and exported with Corona's own scene export.",
            "Each setup is applied, then your script runs.",
        ][i])

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Folder", self.folder.text())
        if d:
            self.folder.setText(d.replace("\\", "/"))

    def chosen(self):
        return [self.list.item(i).data(QtCore.Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == QtCore.Qt.Checked]
