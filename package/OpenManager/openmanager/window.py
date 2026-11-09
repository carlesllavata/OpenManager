"""The OpenManager window: a dock that lives inside 3ds Max (floating or docked)."""
import copy
import json
import os
import time
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

from . import cards, cards2, dialogs, icons, maxlink, model, widgets
from .widgets import Blocker, Card, GridBoard, PRIMARY, TINTS, blend, icon, menu_tool, pal, text_color, tool

VERSION = "0.2.0"
TITLE = "OpenManager"
OBJECT_NAME = "OpenManager"
TOP_ICON = 22

# setup list columns: (key, title); the first three are fixed
COL_GRIP, COL_RENDER, COL_NUM = 0, 1, 2
OPTIONAL_COLUMNS = [("id", "Id"), ("name", "Scene Name"), ("camera", "Camera"), ("resolution", "Resolution"),
                    ("sun", "Sun"), ("dome", "Dome"), ("environment", "Environment"), ("frame", "Frame")]


def cfg_dir():
    try:
        from pymxs import runtime as rt
        return str(rt.getDir(rt.Name("plugcfg")))
    except Exception:
        return os.path.expanduser("~")


def settings_path():
    return os.path.join(cfg_dir(), "OpenManager.json")


def default_settings_path():
    return os.path.join(cfg_dir(), "OpenManager_default.json")


def notify_flag_path():
    return os.path.join(cfg_dir(), "OpenManager_notify.txt")


class SetupTree(QtWidgets.QTreeWidget):
    reordered = QtCore.Signal()

    def __init__(self, parent=None):
        super(SetupTree, self).__init__(parent)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAllColumnsShowFocus(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setIconSize(QtCore.QSize(18, 18))
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.invisibleRootItem().setFlags(self.invisibleRootItem().flags() | QtCore.Qt.ItemIsDropEnabled)

    def dropEvent(self, e):
        super(SetupTree, self).dropEvent(e)
        self.reordered.emit()


class SetupListCard(Card):
    CARD_ID = 0
    NEEDS_SETUP = False

    def build(self):
        sm = self.sm
        hl = self.header_layout
        at = self.header_tools_at
        self.btn_check = tool("checklist", "Tick setups with a box, without activating them, to duplicate, delete or color several",
                              size=widgets.HEADER_ICON, checkable=True, slot=sm.set_check_mode)
        buttons = [
            self.btn_check,
            tool("color", "Setup color", size=widgets.HEADER_ICON, slot=sm.pick_color),
            tool("delete", "Remove selected setups", size=widgets.HEADER_ICON, slot=sm.remove_selected),
            tool("dup", "Duplicate selected setups", size=widgets.HEADER_ICON, slot=sm.duplicate),
        ]
        io, m = menu_tool("transfer", "Import/Export", size=widgets.HEADER_ICON)
        m.addAction(icon("import"), "Import setups (.smp)...", sm.import_setups)
        m.addAction(icon("export"), "Export setups (.smp)...", sm.export_setups)
        buttons.append(io)
        buttons += [
            tool("camera", "Fetch current scene", size=widgets.HEADER_ICON, slot=sm.fetch_scene),
            tool("list", "Create setup for every camera", size=widgets.HEADER_ICON, slot=sm.per_camera),
            tool("wand", "Create new camera (from the current view) and a setup for it", size=widgets.HEADER_ICON, slot=sm.new_camera),
            tool("add", "Create empty setup", size=widgets.HEADER_ICON, slot=sm.add_empty),
        ]
        for i, b in enumerate(buttons):
            hl.insertWidget(at + i, b)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.tree = SetupTree()
        self.body_layout.addWidget(self.tree)
        self.empty_label = QtWidgets.QLabel("There are no setups", self.tree.viewport())
        self.empty_label.setEnabled(False)
        self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, e):
        super(SetupListCard, self).resizeEvent(e)
        self.empty_label.setGeometry(self.tree.viewport().rect())

    def refresh(self):
        self.stack.setCurrentWidget(self.body)
        self.empty_label.setVisible(not self.sm.setups)
        self.empty_label.setGeometry(self.tree.viewport().rect())


class SideBar(QtWidgets.QWidget):
    """One button per card, grouped by colour like the original's left bar: click to show / hide it."""

    def __init__(self, sm, parent=None):
        super(SideBar, self).__init__(parent)
        self.sm = sm
        self.buttons = {}
        self.lines = []
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(4, 6, 2, 6)
        v.setSpacing(1)
        last = None
        for cid in model.CARD_ORDER:
            tint = model.CARDS[cid][1]
            if last is not None and tint != last:
                line = QtWidgets.QFrame()
                line.setFrameShape(QtWidgets.QFrame.HLine)
                self.lines.append(line)
                v.addSpacing(3)
                v.addWidget(line)
                v.addSpacing(3)
            last = tint
            b = QtWidgets.QToolButton()
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setIcon(icon(widgets.CARD_GLYPH.get(cid, "list"), 18))
            b.setIconSize(QtCore.QSize(18, 18))
            b.setFixedSize(30, 28)
            b.setToolTip(model.CARDS[cid][0])
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            b.toggled.connect(lambda on, cid=cid: self.sm.set_card_visible(cid, on))
            b.setProperty("tint", TINTS.get(tint or "", "#808080"))
            v.addWidget(b)
            self.buttons[cid] = b
        v.addStretch(1)
        self.setFixedWidth(38)
        self.restyle()

    def restyle(self):
        c = blend(pal().color(QtGui.QPalette.Window), text_color(), 0.25).name()
        for line in self.lines:
            line.setStyleSheet("color:%s" % c)

    def sync(self):
        vis = set(self.sm.visible_cards())
        for cid, b in self.buttons.items():
            with Blocker(b):
                b.setChecked(cid in vis)
            ok = self.sm.compatible(cid)
            b.setEnabled(ok)
            b.setToolTip(model.CARDS[cid][0] + ("" if ok else "  (not for this renderer)"))
        self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        for cid, b in self.buttons.items():
            g = b.geometry()
            c = QtGui.QColor(b.property("tint"))
            if not b.isChecked():
                c.setAlpha(70)
            p.fillRect(QtCore.QRect(0, g.top() + 3, 3, g.height() - 6), c)


class Toast(QtWidgets.QLabel):
    def __init__(self, parent):
        super(Toast, self).__init__(parent)
        self.setStyleSheet("background:rgba(30,30,30,225);color:#f0f0f0;padding:6px 12px;border-radius:4px")
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_text(self, text, ms=3500):
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move(max(8, (p.width() - self.width()) // 2), p.height() - self.height() - 14)
        self.raise_()
        self.show()
        self.timer.start(ms)


def light_palette():
    p = QtGui.QPalette()
    for role, c in ((QtGui.QPalette.Window, "#f0f0f0"), (QtGui.QPalette.WindowText, "#2e2e2e"), (QtGui.QPalette.Base, "#ffffff"),
                    (QtGui.QPalette.AlternateBase, "#f4f4f4"), (QtGui.QPalette.Text, "#2e2e2e"), (QtGui.QPalette.Button, "#e6e6e6"),
                    (QtGui.QPalette.ButtonText, "#2e2e2e"), (QtGui.QPalette.Highlight, PRIMARY), (QtGui.QPalette.HighlightedText, "#ffffff"),
                    (QtGui.QPalette.ToolTipBase, "#ffffdc"), (QtGui.QPalette.ToolTipText, "#000000")):
        p.setColor(role, QtGui.QColor(c))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor("#9a9a9a"))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor("#9a9a9a"))
    return p


def dark_palette():
    p = QtGui.QPalette()
    for role, c in ((QtGui.QPalette.Window, "#2b2b2b"), (QtGui.QPalette.WindowText, "#e0e0e0"), (QtGui.QPalette.Base, "#3a3a3a"),
                    (QtGui.QPalette.AlternateBase, "#333333"), (QtGui.QPalette.Text, "#e0e0e0"), (QtGui.QPalette.Button, "#444444"),
                    (QtGui.QPalette.ButtonText, "#e0e0e0"), (QtGui.QPalette.Highlight, PRIMARY), (QtGui.QPalette.HighlightedText, "#ffffff"),
                    (QtGui.QPalette.ToolTipBase, "#2b2b2b"), (QtGui.QPalette.ToolTipText, "#e0e0e0")):
        p.setColor(role, QtGui.QColor(c))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor("#7a7a7a"))
    p.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor("#7a7a7a"))
    return p


THEMES = {
    "light": {"bg": "#f0f0f0", "base": "#ffffff", "text": "#2e2e2e", "dis": "#a0a0a0", "border": "#c9c9c9",
              "button": "#e4e4e4", "sel": "#cfe6f3", "head": "#e9e9e9"},
    "dark": {"bg": "#2b2b2b", "base": "#383838", "text": "#e0e0e0", "dis": "#808080", "border": "#4d4d4d",
             "button": "#454545", "sel": "#2f5a73", "head": "#404040"},
}


def theme_qss(name):
    """A full style for the window when the theme is forced: 3ds Max's own style sheet would otherwise
    keep its colours on inputs and labels."""
    t = dict(THEMES[name], primary=PRIMARY)
    return """
QWidget { color: %(text)s; }
QDockWidget { color: %(text)s; }
QDockWidget::title { background: %(head)s; padding: 4px; }
QWidget#omRoot, QWidget#omBoard, QDialog, QMessageBox, QColorDialog, QInputDialog { background: %(bg)s; }
QDialog QWidget { background: %(bg)s; }
QDialog QLineEdit, QDialog QComboBox, QDialog QSpinBox, QDialog QPlainTextEdit, QDialog QListWidget { background: %(base)s; }
QDialog QAbstractButton { background: transparent; }
QDialog QPushButton { background: %(button)s; }
QDialog QPushButton:hover { background: %(sel)s; }
QDialog QProgressBar { background: %(base)s; }
QDialog QProgressBar::chunk { background: %(primary)s; }
QLabel, QCheckBox, QRadioButton { background: transparent; color: %(text)s; }
QCalendarWidget QWidget { background: %(base)s; color: %(text)s; alternate-background-color: %(head)s; }
QCalendarWidget QAbstractItemView { selection-background-color: %(primary)s; selection-color: #ffffff; }
QCalendarWidget QToolButton { color: %(text)s; background: %(head)s; }
QDateEdit { background: %(base)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 2px; }
QLabel:disabled, QCheckBox:disabled, QRadioButton:disabled { color: %(dis)s; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QListWidget, QTreeWidget, QTableWidget {
    background: %(base)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 2px;
    selection-background-color: %(primary)s; selection-color: #ffffff; }
QComboBox QAbstractItemView { background: %(base)s; color: %(text)s; selection-background-color: %(primary)s; }
QHeaderView::section { background: %(head)s; color: %(text)s; border: none; border-right: 1px solid %(border)s; padding: 2px 5px; }
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected { background: %(sel)s; color: %(text)s; }
QPushButton { background: %(button)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 3px; padding: 3px 10px; }
QPushButton:hover, QToolButton:hover { background: %(sel)s; }
QToolButton { color: %(text)s; background: transparent; border: none; }
QTabBar::tab { background: %(button)s; color: %(text)s; padding: 4px 12px; border: 1px solid %(border)s; }
QTabBar::tab:selected { background: %(base)s; }
QTabWidget::pane { border: 1px solid %(border)s; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: %(bg)s; width: 10px; } QScrollBar::handle:vertical { background: %(border)s; min-height: 20px; border-radius: 4px; }
QScrollBar:horizontal { background: %(bg)s; height: 10px; } QScrollBar::handle:horizontal { background: %(border)s; min-width: 20px; border-radius: 4px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QMenu { background: %(base)s; color: %(text)s; border: 1px solid %(border)s; } QMenu::item:selected { background: %(sel)s; }
QProgressBar { background: %(base)s; border: 1px solid %(border)s; text-align: center; color: %(text)s; }
QProgressBar::chunk { background: %(primary)s; }
QToolTip { color: %(text)s; background: %(base)s; border: 1px solid %(border)s; }
QCheckBox::indicator, QRadioButton::indicator, QTableWidget::indicator, QListWidget::indicator {
    width: 13px; height: 13px; border: 1px solid %(dis)s; background: %(base)s; }
QRadioButton::indicator { border-radius: 7px; }
QCheckBox::indicator:checked, QTableWidget::indicator:checked, QListWidget::indicator:checked { background: %(primary)s; border-color: %(primary)s; }
QRadioButton::indicator:checked { background: %(primary)s; border: 3px solid %(base)s; outline: 1px solid %(primary)s; }
""" % t


class SceneManager(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super(SceneManager, self).__init__(TITLE, parent)
        self.setObjectName(OBJECT_NAME)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable
                         | QtWidgets.QDockWidget.DockWidgetClosable)
        self.settings = self.load_settings()
        self.apply_theme_palette()
        self._icon_color = text_color()
        self.scene = maxlink.Scene()
        self.setups = []
        self.todo = []
        self.rs_default = {}
        self.base = {}  # what the applied setup changed, to put it back (model.base_step)
        self.undo_stack = []  # records of applied setups (see begin_undo), newest last
        self.redo_stack = []
        self._undo_rec = None
        self._typed = {}  # (setup id, slot) -> code typed in the Script Editor this session: yours, so it runs
        self._denied = set()  # scripts you chose not to run this session (not asked about again)
        self._refused = []  # scripts left out of the last changes built (not trusted)
        self.active_id = None
        self.next_id = 1
        self.last_sent = []
        self.last_saved = None
        self.clipboard = {}
        self.rendering = False
        self.loading = False
        self.applying = 0
        self.preview_mode = False
        self.camera_sync = False
        self.check_mode = False
        self.checked = set()
        self.pc_name = os.environ.get("COMPUTERNAME", "")
        self.user_name = os.environ.get("USERNAME", "")
        self._texmaps = None
        self._scene_raw = None
        self._synced = 0.0

        self.apply_timer = self._timer(120, self._apply)
        self.save_timer = self._timer(700, self.save_setups)
        self.list_timer = self._timer(0, self.refresh_rows)
        self.scene_timer = self._timer(350, self.reload_scene)
        self.sync_timer = QtCore.QTimer(self)
        self.sync_timer.setInterval(400)
        self.sync_timer.timeout.connect(self._camera_sync_tick)

        self._build()
        maxlink.load_core()
        self.reload_all()
        maxlink.watch(self._on_max_event)

    def _timer(self, ms, slot):
        t = QtCore.QTimer(self)
        t.setSingleShot(True)
        t.setInterval(ms)
        t.timeout.connect(slot)
        return t

    # ------------------------------------------------------------ building
    def _top_tool(self, glyph, tip, slot=None, checkable=False):
        b = tool(glyph, tip, size=TOP_ICON, checkable=checkable, slot=slot)
        b.setFixedSize(TOP_ICON + 14, TOP_ICON + 12)
        return b

    def _build(self):
        root = QtWidgets.QWidget()
        root.setObjectName("omRoot")
        root.setAutoFillBackground(True)
        v = QtWidgets.QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        top = QtWidgets.QWidget()
        tl = QtWidgets.QHBoxLayout(top)
        tl.setContentsMargins(6, 4, 8, 4)
        tl.setSpacing(2)
        self.btn_preview = self._top_tool("view", "Switch to Preview Mode: clicking a setup only shows it, the cards can't be edited", checkable=True)
        self.btn_preview.toggled.connect(self.set_preview_mode)
        self.btn_sync = self._top_tool("sync", "Enable Camera Sync: changing the camera of the viewport changes the active setup's camera", checkable=True)
        self.btn_sync.toggled.connect(self.set_camera_sync)
        self.btn_render = QtWidgets.QToolButton()
        self.btn_render.setIcon(icons.teapot(PRIMARY, True, TOP_ICON))
        self.btn_render.setIconSize(QtCore.QSize(TOP_ICON + 4, TOP_ICON + 4))
        self.btn_render.setAutoRaise(True)
        self.btn_render.setFixedSize(TOP_ICON + 14, TOP_ICON + 12)
        self.btn_render.setToolTip("Batch Render: every setup with its teapot on, one after the other")
        self.btn_render.clicked.connect(lambda: self.start_render(None))
        self.btn_render_sel = self._top_tool("photo", "Render only the selected setups", slot=lambda: self.start_render(self.selected_setups()))
        self.btn_bake = self._top_tool("bake", "Bake Setups: 3ds Max Batch Render, .max / .scn per setup, or a script on every setup", slot=self.bake_setups)
        self.btn_vpreview = self._top_tool("globe", "Viewport Preview: a viewport picture of every setup (as its thumbnail)", slot=self.viewport_preview)
        for b in (self.btn_preview, self.btn_sync, self.btn_render, self.btn_render_sel, self.btn_bake, self.btn_vpreview):
            tl.addWidget(b)
        tl.addSpacing(6)
        tl.addWidget(self._top_tool("refresh", "Read the scene again", slot=self.reload_scene))
        tl.addSpacing(6)
        self.btn_undo = self._top_tool("undo", "Undo the last setup applied", slot=self.undo)
        self.btn_redo = self._top_tool("redo", "Redo", slot=self.redo)
        tl.addWidget(self.btn_undo)
        tl.addWidget(self.btn_redo)
        tl.addStretch(1)
        self.status = QtWidgets.QLabel("")
        self.status.setEnabled(False)
        tl.addWidget(self.status)
        tl.addSpacing(8)
        tl.addWidget(self._top_tool("gear", "Settings", slot=self.open_settings))
        self.logo = QtWidgets.QLabel()
        self.logo.setToolTip("OpenManager %s" % VERSION)
        tl.addSpacing(4)
        tl.addWidget(self.logo)
        v.addWidget(top)

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = SideBar(self)
        body.addWidget(self.sidebar)
        self.board = GridBoard(self)
        self.board.setObjectName("omBoard")
        self.board.layout_changed.connect(self.save_settings)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.board)
        body.addWidget(self.scroll, 1)
        v.addLayout(body, 1)

        self.cards = {}
        for cls in [SetupListCard] + cards.CARD_CLASSES + cards2.CARD_CLASSES:
            c = cls(self, self.board)
            c.hide()
            self.cards[cls.CARD_ID] = c
        self.tree = self.cards[0].tree
        self.tree.itemClicked.connect(self._row_clicked)
        self.tree.itemDoubleClicked.connect(self._row_double)
        self.tree.itemChanged.connect(self._row_edited)
        self.tree.reordered.connect(self._reordered)
        self.tree.customContextMenuRequested.connect(self._row_menu)
        QtGui.QShortcut(QtGui.QKeySequence.Delete, self.tree, self.remove_selected, context=QtCore.Qt.WidgetShortcut)
        # Ctrl+Z / Ctrl+Y while the window has the focus (a text box keeps its own undo)
        QtGui.QShortcut(QtGui.QKeySequence.Undo, root, self.undo, context=QtCore.Qt.WidgetWithChildrenShortcut)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Y"), root, self.redo, context=QtCore.Qt.WidgetWithChildrenShortcut)
        self.setup_columns()
        self.toast_label = Toast(root)
        self.setWidget(root)
        self.layout_cards()
        self._draw_logo()

    # ------------------------------------------------------------ settings
    def load_settings(self):
        for path in (settings_path(), default_settings_path()):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if isinstance(d, dict):
                        if "layouts" in d and not isinstance(d["layouts"], dict):
                            d["layouts"] = {}
                        return d
            except Exception:
                pass
        return {}

    def save_settings(self):
        st = self.settings
        try:
            st["floating"] = self.isFloating()
            if self.isFloating():
                g = self.geometry()
                st["geometry"] = [g.x(), g.y(), g.width(), g.height()]
            par = self.parent()
            if isinstance(par, QtWidgets.QMainWindow) and not self.isFloating():
                area = par.dockWidgetArea(self)
                st["area"] = int(area.value) if hasattr(area, "value") else int(area)
            st["column_widths"] = {k: self.tree.header().sectionSize(i) for i, k in enumerate(self.column_keys)}
        except Exception:
            pass
        try:
            with open(settings_path(), "w", encoding="utf-8") as f:
                json.dump(st, f, indent=1)
            with open(notify_flag_path(), "w") as f:
                f.write("1" if st.get("notify", True) else "0")
        except Exception as ex:
            print("OpenManager: could not save settings: %s" % ex)

    def opts(self):
        return dict(dialogs.DEFAULT_SETTINGS_MAX, **self.settings.get("max", {}))

    def apply_theme_palette(self):
        main = self.settings.get("theme", {}).get("main", "auto")
        self._theme_main = main
        widgets_pal = None
        if main == "light":
            widgets_pal = light_palette()
        elif main == "dark":
            widgets_pal = dark_palette()
        self._palette = widgets_pal
        widgets.PALETTE_OVERRIDE = widgets_pal
        if widgets_pal is not None:
            self.setPalette(widgets_pal)
            self.setStyleSheet(theme_qss(main))
        else:
            self.setPalette(QtWidgets.QApplication.palette())
            self.setStyleSheet("")

    def open_settings(self):
        dlg = dialogs.SettingsDialog(self, self.settings)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        if dlg.action == "factory":
            if QtWidgets.QMessageBox.question(self, TITLE, "Reset every setting, the card layout and the Property Selector ticks?") != QtWidgets.QMessageBox.Yes:
                return
            geo = self.settings.get("geometry")
            self.settings = {"geometry": geo} if geo else {}
            try:
                os.remove(default_settings_path())
            except OSError:
                pass
        elif dlg.action == "reset":
            try:
                with open(default_settings_path(), "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            except Exception:
                self.toast("You have no default settings saved yet")
                return
        else:
            self.settings.update(dlg.values())
            if dlg.action == "save_default":
                with open(default_settings_path(), "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=1)
                self.toast("Saved as your default settings")
        self.save_settings()
        self.restyle_all()

    def set_theme(self, main):
        """Changes the look at once, with the window open."""
        self.settings.setdefault("theme", {})["main"] = main
        self.restyle_all()

    def _draw_logo(self):
        pm = icons.app_icon(widgets.is_dark())
        self.setWindowIcon(pm)
        self.logo.setPixmap(pm.pixmap(TOP_ICON, TOP_ICON))

    def _redraw_icons(self):
        """Icons are pictures in the colour of the theme: each one that exists is redrawn in the new colour."""
        new = text_color()
        old = self._icon_color
        if QtGui.QColor(old).rgba() == QtGui.QColor(new).rgba():
            return
        for w in self.findChildren(QtWidgets.QAbstractButton) + self.findChildren(QtGui.QAction):
            ic = icons.recolor(w.icon(), old, new)
            if ic is not None:
                w.setIcon(ic)
        self._icon_color = new

    def restyle_all(self):
        self.apply_theme_palette()
        self._redraw_icons()
        self._draw_logo()
        self.sidebar.restyle()
        for c in self.cards.values():
            c.restyle()
        self.setup_columns()
        self.layout_cards()
        self.rebuild_rows()
        self.refresh_cards()

    def visible_cards(self):
        vis = self.settings.get("visible")
        if vis is None:
            vis = list(model.DEFAULT_VISIBLE)
        if 0 not in vis:
            vis = [0] + list(vis)
        return vis

    def compatible(self, cid):
        eng = model.CARD_ENGINES.get(cid)
        return not eng or self.scene.engine_id in eng

    def layout_cards(self):
        shown = {cid: self.cards[cid] for cid in self.visible_cards() if cid in self.cards and self.compatible(cid)}
        self.board.set_cards(shown)
        self.sidebar.sync()

    def set_card_visible(self, cid, on):
        vis = [c for c in self.visible_cards() if c != cid]
        if on:
            vis.append(cid)
        self.settings["visible"] = vis
        self.layout_cards()
        self.save_settings()
        if on:
            self.cards[cid].refresh()

    # ------------------------------------------------------------ reading the scene and its setups
    def reload_all(self):
        """A file was opened (or the window just opened): read the scene and the setups stored in it."""
        data, source = maxlink.read_setups(1)
        try:
            raw = maxlink.read_scene_raw(self.object_handles(data["setups"]))
            self.scene = maxlink.Scene(maxlink.parse_scene(raw))
            self._scene_raw = raw
        except Exception:
            traceback.print_exc()
        self.setups = data["setups"]
        self.todo = data["todo"]
        self.rs_default = data.get("rs_default") or {}
        self.base = data.get("base") or {}
        self.clear_undo()
        self.next_id = max([s["id"] for s in self.setups] + [0]) + 1
        self.last_saved = self.encoded()
        if source == "pulze":
            self.toast("Read %d setup(s) saved by Pulze Scene Manager in this file" % len(self.setups))
            # written with the file next time it is saved: from then on these are the setups (Pulze's are not asked about again)
            self.last_saved = None
        elif source == "legacy":
            self.last_saved = None  # saved again under the new name with the file
        self.resolve_scene_refs()
        self.active_id = None
        self.last_sent = []
        self.loading = False
        self._texmaps = None
        self.layout_cards()
        self.rebuild_rows()
        self.refresh_cards()
        self.update_status()

    # ------------------------------------------------------------ lasting references to nodes and layers
    def resolve_all(self, setups=None, strict=False):
        """Finds again the nodes and layers the setups use after a merge, a rename or a file change (by lasting ID,
        then handle, then name; see model.apply_resolved). Returns True when a reference changed."""
        setups = self.setups if setups is None else setups
        changed = False
        try:
            results = maxlink.resolve_nodes(model.resolve_query(setups))
            changed = model.apply_resolved(setups, results, strict=strict)
            names = maxlink.layer_uids()
            for s in setups:
                for ref in model.layer_refs(s):
                    name, uid = model.layer_ref_get(ref)
                    if uid and uid in names and names[uid] != name:
                        model.layer_ref_set(ref, name=names[uid])
                        changed = True
        except Exception:
            traceback.print_exc()
        if changed:
            self.save_timer.start()
        return changed

    def resolve_scene_refs(self):
        """resolve_all after a scene read; when a node moved (a merge), the scene is read again so it lists the
        objects at their new handles."""
        if self.resolve_all():
            try:
                raw = maxlink.read_scene_raw(self.object_handles())
                self.scene = maxlink.Scene(maxlink.parse_scene(raw))
                self._scene_raw = raw
            except Exception:
                traceback.print_exc()

    def stamp_uids(self):
        """Gives a lasting ID to every node and layer a setup started to use (stored in their app data)."""
        refs = [r for s in self.setups for r in model.node_refs(s) if r.get("handle") is not None and not r.get("uid")]
        lights = [(s, h) for s in self.setups for h in s["lights"]["set"] if not model.light_uids(s).get(str(h))]
        uids = maxlink.stamp_nodes([r["handle"] for r in refs] + [h for _, h in lights])
        for r, u in zip(refs, uids):
            if u:
                r["uid"] = u
        for (s, h), u in zip(lights, uids[len(refs):]):
            if u:
                model.light_uids(s)[str(h)] = u
        lrefs = [ref for s in self.setups for ref in model.layer_refs(s) if not model.layer_ref_get(ref)[1]]
        for ref, u in zip(lrefs, maxlink.stamp_layers([model.layer_ref_get(ref)[0] for ref in lrefs])):
            if u:
                model.layer_ref_set(ref, uid=u)

    def object_handles(self, setups=None):
        """Objects the setups use: the only ones the scene read lists (a big scene has far too many to list)."""
        hs = set()
        for s in (self.setups if setups is None else setups):
            for o in s.get("objects", {}).get("set", []):
                if o.get("handle") is not None:
                    hs.add(int(o["handle"]))
        return sorted(hs)

    def reload_scene(self, raw=None):
        try:
            if raw is None:
                raw = maxlink.read_scene_raw(self.object_handles())
            self.scene = maxlink.Scene(maxlink.parse_scene(raw))
            self._scene_raw = raw
        except Exception:
            traceback.print_exc()
            return
        self._texmaps = None
        self.resolve_scene_refs()
        self.layout_cards()
        self.refresh_rows()
        self.refresh_cards()
        self.update_status()

    def sync_scene(self, force=False):
        """Reads the scene again when it changed in 3ds Max in a way no event tells (a map made in the Material Editor,
        the sun type of a Daylight...). Cheap: one call, and nothing is redrawn when the scene is the same."""
        if self.rendering or self.loading or self.applying:
            return False
        now = time.time()
        if not force and now - self._synced < 0.8:
            return False
        self._synced = now
        try:
            raw = maxlink.read_scene_raw(self.object_handles())
        except Exception:
            traceback.print_exc()
            return False
        if raw == self._scene_raw:
            return False
        self.scene_timer.stop()
        self.reload_scene(raw)
        return True

    def enterEvent(self, e):
        # back from working in 3ds Max: what the lists offer must be what the scene has now
        QtCore.QTimer.singleShot(0, self.sync_scene)
        super(SceneManager, self).enterEvent(e)

    def set_check_mode(self, on):
        """Boxes in the setup list: a click ticks a setup instead of activating it."""
        self.check_mode = bool(on)
        self.checked = set()
        self.refresh_rows()
        self.toast("Tick the setups, then duplicate, delete or color them" if on else "Setup boxes off")

    def _on_max_event(self, what):
        try:
            w = str(what)
            if self.applying and w in ("preopen", "file", "presave"):
                return
            if w == "preopen":
                if self.save_timer.isActive():
                    self.save_timer.stop()
                    self.save_setups()
                self.apply_timer.stop()
                self.loading = True
            elif w == "file":
                QtCore.QTimer.singleShot(50, self.reload_all)
            elif w == "presave":
                self.save_timer.stop()
                self.save_setups()
            elif w == "shutdown":
                self.close()
            elif w == "view":
                if self.camera_sync:
                    self._camera_sync_tick()
            elif not self.rendering:
                self.scene_timer.start()
        except Exception:
            traceback.print_exc()

    def update_status(self):
        f = self.scene.file or "Untitled"
        self.status.setText("%s  ·  %s  ·  %d setup%s" % (self.scene.engine or "?", f, len(self.setups),
                                                                     "" if len(self.setups) == 1 else "s"))

    # ------------------------------------------------------------ helpers the cards use
    def active(self):
        if self.active_id is None:
            return None
        for s in self.setups:
            if s["id"] == self.active_id:
                return s
        return None

    def locked(self):
        return self.preview_mode or self.rendering

    def index_of(self, s):
        for i, x in enumerate(self.setups):
            if x is s:
                return i
        return 0

    def selected_setups(self):
        if self.check_mode:
            return [s for s in self.setups if s["id"] in self.checked]
        ids = set(it.data(0, QtCore.Qt.UserRole) for it in self.tree.selectedItems())
        return [s for s in self.setups if s["id"] in ids]

    def targets(self):
        """The active setup plus every selected one."""
        out = self.selected_setups()
        a = self.active()
        if a is not None and a not in out:
            out.insert(0, a)
        return out

    def enabled_keys(self, card):
        st = self.settings.setdefault("enabled_props", {})
        keys = st.get(str(card))
        return keys if keys is not None else model.default_enabled(card)

    def enabled_rows(self, card):
        return model.enabled_rows(card, self.scene.engine_id, self.enabled_keys(card))

    def resolution_presets(self):
        return [tuple(x) for x in self.settings.get("resolution_presets") or model.RESOLUTION_PRESETS]

    def build_path(self, s):
        """(path, problem) of the setup's Render Output card; problem is None when the path is complete."""
        cam = self.scene.camera(s["camera"]["handle"])
        return model.build_path(s["output"], self.scene.file, cam["name"] if cam else None, s["scenename"],
                                self.index_of(s), self.pc_name, self.user_name)

    def final_path(self, s):
        path, problem = self.build_path(s)
        return path, problem is None

    def toast(self, text):
        self.toast_label.show_text(text)

    def changed(self, apply=True, list_too=True):
        self.save_timer.start()
        if apply:
            self.apply_timer.start()
        if list_too:
            self.list_timer.start()
        out = self.cards.get(9)
        s = self.active()
        if out is not None and s is not None and out.isVisible():
            out.update_final(s)

    def selected_handles(self):
        return maxlink.selected_handles()

    def selected_objects(self):
        """The selected geometry and shapes, read now (and added to what the scene knows)."""
        items = maxlink.objects_info(maxlink.selected_handles())
        self.scene.add_objects(items)
        return items

    def select_handles(self, hs):
        maxlink.select_handles(hs)

    def scene_texmaps(self):
        if self._texmaps is None:
            self._texmaps = maxlink.texmaps()
        return self._texmaps

    def fetch_prop(self, card, tab, prop, link=None, key=None, store=None, entry=0):
        """The pencil of a setting row: take its value from the scene into the active setup."""
        s = self.active()
        if s is None:
            return False
        v = self._scene_value(s, card, tab, prop, link, entry)
        if v is None:
            self.toast("Couldn't read %s from the scene" % (prop.get("short") or prop["name"]))
            return False
        target = s["props"] if store is None else store
        target[key or "%d|%s|%s" % (card, tab["v_class"], prop["name"])] = v
        self.changed(apply=False)
        return True

    def _scene_value(self, s, card, tab, prop, link=None, entry=0):
        cls = prop["class"]
        special = cls in ("Color", "Texturemap", "Pipeline")
        if card == 25:
            v = maxlink.read_special("rs", None, prop["name"], cls) if special else maxlink.read_value("rs", prop["name"], None)
        elif card in (1, 3, 4):
            block = s[{1: "camera", 3: "sun", 4: "dome"}[card]]
            h = model.entries(block)[entry].get("handle") if card != 1 else block.get("handle")
            if h is None:
                return None
            name = prop["name"]
            if card == 3:
                name = model.light_prop(self.scene.light(h), tab, prop)
            v = maxlink.read_special("node", h, name, cls) if special else maxlink.read_value("node", h, name)
        elif card == 6:
            if link is None:
                return None
            v = maxlink.read_value("map", link["class"], link["name"], prop["name"])
        else:
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = model.from_max(prop["name"], float(v))
        return v

    # ------------------------------------------------------------ applying to the scene
    def actions_for(self, s, rendering):
        out_path = None
        if s["output"]["enabled"]:
            path, valid = self.final_path(s)
            # an incomplete path leaves the scene's render output as it is (it used to switch saving off, so a
            # batch rendered without saving); the batch checks every setup before it starts
            out_path = path if valid else None
        acts = maxlink.actions(s, self.scene, self.enabled_rows, out_path, rendering, self.opts(), self.rs_default)
        acts, self._refused = model.filter_scripts(acts, self.script_allowed)
        return acts

    # ------------------------------------------------------------ scripts that came with a file
    def script_allowed(self, kind, text):
        """May this script of a setup run? Yes when trusted (approved, written or chosen by you) or when Settings
        say to always run them."""
        policy = self.opts().get("scripts", "ask")
        if policy == "always":
            return True
        if model.script_key(kind, text) in set(self.settings.get("trusted_scripts") or []):
            return True
        if kind == "code" and text in self._typed.values():
            self.trust_scripts([(kind, text)])
            return True
        return False

    def trust_scripts(self, pieces):
        """Remembers (kind, text) pieces as trusted, in this computer's settings (never in the .max)."""
        lst = self.settings.setdefault("trusted_scripts", [])
        added = False
        for kind, text in pieces:
            k = model.script_key(kind, text)
            if k not in lst:
                lst.append(k)
                added = True
        if added:
            del lst[:-1000]
            self.save_settings()

    def typed_code(self, sid, slot, text):
        self._typed[(sid, slot)] = text

    def review_scripts(self, setups):
        """Before setups are applied: shows the scripts they would run that aren't trusted yet, once, and asks."""
        if self.opts().get("scripts", "ask") != "ask":
            return
        rows, keys = [], []
        for s in setups:
            for p in model.code_pieces(s):
                k = model.script_key(p["kind"], p["text"])
                if k in keys or k in self._denied or self.script_allowed(p["kind"], p["text"]):
                    continue
                keys.append(k)
                rows.append((self.setup_label(s), p["slot"], p["kind"], p["text"]))
        if not rows:
            return
        if self.ask_scripts(rows):
            self.trust_scripts([(kind, text) for _, _, kind, text in rows])
        else:
            self._denied.update(keys)

    def ask_scripts(self, rows):
        return dialogs.ScriptReviewDialog(self, rows).exec() == QtWidgets.QDialog.Accepted

    def tell_refused(self):
        if self._refused:
            self.toast("%d script(s) of this setup were not run: they came with the file and aren't trusted" % len(self._refused))

    def run_actions(self, acts, redraw=True):
        """Applies changes; events 3ds Max fires because of them (a render preset load looks like a file
        being opened) are not taken for the person opening another scene."""
        self.applying += 1
        try:
            maxlink.run(acts, redraw=redraw)
        finally:
            QtWidgets.QApplication.processEvents()
            self.applying -= 1

    def _apply(self):
        s = self.active()
        if s is None or self.rendering:
            return
        acts = self.actions_for(s, False)
        restore = self.base_restore(acts)
        sent = set(self.last_sent)
        fresh = restore + [a for a in acts if a not in sent]
        self.last_sent = acts
        if not fresh:
            return
        self.undo_capture(fresh)
        o = self.opts()
        restart = False
        if o.get("ipr_corona_restart") and self.scene.engine_id == "corona" and maxlink.interactive_running():
            maxlink.interactive_stop()
            restart = True
        self.run_actions(fresh, redraw=bool(o.get("viewport_refresh", True)))
        if restart:
            maxlink.interactive_start()

    def base_restore(self, acts):
        """Before applying `acts`: the changes that put back what the setup applied before changed and this one
        doesn't control, and the values this one is about to replace are kept (model.base_step)."""
        if not self.opts().get("restore_base", True):
            self.base = {}
            return []
        before = self.base
        restore, self.base = model.base_step(self.base, acts, maxlink.capture)
        if self.base != before:
            self.save_timer.start()
        return restore

    def restore_scene(self, keep_redo=False):
        """Puts back everything the setups changed, as the scene was before them, and leaves no setup active."""
        if not self.base:
            self.toast("Nothing to put back: no setup has changed the scene")
            return
        self.begin_undo("Put back the scene", "restore", keep_redo)
        restore, self.base = model.base_step(self.base, [], maxlink.capture)
        self.undo_capture(restore)
        self.run_actions(restore)
        self.active_id = None
        self.last_sent = []
        self.end_undo()
        self.save_timer.start()
        self.refresh_rows()
        self.refresh_cards()
        self.toast("The scene is back as it was before the setups (%d setting(s))" % len(restore))

    def activate(self, sid, keep_redo=False):
        s = next((x for x in self.setups if x["id"] == sid), None)
        if s is None:
            return
        self.review_scripts([s])
        self.begin_undo("Apply %s" % self.setup_label(s), "activate", keep_redo)
        self.active_id = sid
        self.resolve_all([s])
        self.last_sent = []
        self.query_values()
        self.apply_timer.stop()
        try:
            self._apply()
        finally:
            self.end_undo()
        self.tell_refused()
        self.refresh_rows()
        self.refresh_cards()

    # ------------------------------------------------------------ undo / redo of applied setups
    # 3ds Max's own undo can't take back render settings such as the resolution or the output file, so applying a
    # setup keeps its own record: the value of everything it changes, taken just before (model.undo_capture).
    # Card edits on the active setup add what they change to the same record, so Undo brings back the scene as it
    # was before that setup was clicked. The setups' own data is never undone.

    def begin_undo(self, label, kind, keep_redo=False):
        self._undo_rec = {"label": label, "kind": kind, "restore": {}, "base_before": dict(self.base),
                          "active_before": self.active_id}
        if not keep_redo:
            self.redo_stack = []

    def undo_capture(self, acts):
        """Before acts run: their current values go into the open record, or into the last one when the change is
        an edit of the setup it applied."""
        rec = self._undo_rec
        if rec is None and self.active_id is not None and self.undo_stack \
                and self.undo_stack[-1].get("active_after") == self.active_id:
            rec = self.undo_stack[-1]
        if rec is not None:
            model.undo_capture(rec["restore"], acts, maxlink.capture)

    def end_undo(self):
        rec, self._undo_rec = self._undo_rec, None
        if rec is None:
            return
        rec["active_after"] = self.active_id
        if rec["restore"] or rec["base_before"] != self.base:
            self.undo_stack = (self.undo_stack + [rec])[-30:]
        self.update_undo_buttons()

    def clear_undo(self):
        self.undo_stack, self.redo_stack, self._undo_rec = [], [], None
        self.update_undo_buttons()

    def update_undo_buttons(self):
        if not hasattr(self, "btn_undo"):
            return
        u = self.undo_stack[-1]["label"] if self.undo_stack else None
        r = self.redo_stack[-1]["label"] if self.redo_stack else None
        self.btn_undo.setEnabled(u is not None)
        self.btn_redo.setEnabled(r is not None)
        self.btn_undo.setToolTip("Undo: %s (Ctrl+Z)" % u if u else "Nothing to undo")
        self.btn_redo.setToolTip("Redo: %s (Ctrl+Y)" % r if r else "Nothing to redo")

    def undo(self):
        if self.rendering or not self.undo_stack:
            return
        self.apply_timer.stop()
        rec = self.undo_stack.pop()
        self.run_actions(list(rec["restore"].values()))
        self.base = dict(rec["base_before"])
        self.active_id = rec["active_before"]
        self.last_sent = []
        self.redo_stack.append(rec)
        self.save_timer.start()
        self.update_undo_buttons()
        self.refresh_rows()
        self.refresh_cards()
        self.toast("Undone: %s" % rec["label"])

    def redo(self):
        if self.rendering or not self.redo_stack:
            return
        rec = self.redo_stack.pop()
        if rec["kind"] == "restore":
            self.restore_scene(keep_redo=True)
        elif any(s["id"] == rec["active_after"] for s in self.setups):
            self.activate(rec["active_after"], keep_redo=True)
        else:
            self.toast("Can't redo: that setup was removed")
        self.update_undo_buttons()

    def query_values(self):
        """Ticked settings with no value yet are read from the scene first, so sliders start at the real value."""
        s = self.active()
        if s is None:
            return
        props = s["props"]
        got = False
        for card in (25, 1, 4):
            if card == 1:
                n = self.scene.camera(s["camera"].get("handle"))
            elif card == 4:
                n = self.scene.light(s["dome"].get("handle"))
            else:
                n = {"class": None}
            if n is None:
                continue
            for t, p in self.enabled_rows(card):
                if card in (1, 4) and not model.tab_matches(t, n["class"]):
                    continue
                key = "%d|%s|%s" % (card, t["v_class"], p["name"])
                if key in props or p["class"] in ("Matrix3", "Material"):
                    continue
                if p["class"] == "Pipeline":
                    continue  # taken only when asked (pencil), it can be long
                v = self._scene_value(s, card, t, p)
                if v is not None:
                    props[key] = v
                    got = True
        for i, en in enumerate(model.entries(s["sun"])):
            l = self.scene.light(en.get("handle"))
            store = model.entry_store(s, s["sun"], i)
            classes = model.light_tabs_classes(l)
            for t, p in self.enabled_rows(3):
                key = "3|%s|%s" % (t["v_class"], p["name"])
                if key not in store and any(model.tab_matches(t, c) for c in classes):
                    v = self._scene_value(s, 3, t, p, entry=i)
                    if v is not None:
                        store[key] = v
                        got = True
        for i, en in enumerate(model.entries(s["environment"])):
            m = self.scene.map(en.get("cls"), en.get("name")) if en.get("cls") else None
            if not m:
                continue
            store = model.entry_store(s, s["environment"], i)
            for t, p, link, key_cls in model.env_rows(m, self.enabled_rows(6)):
                key = "6|%s|%s" % (key_cls, p["name"])
                if key not in store and p["class"] not in ("Matrix3", "Material", "Pipeline"):
                    v = self._scene_value(s, 6, t, p, link)
                    if v is not None:
                        store[key] = v
                        got = True
        for h in s["lights"]["set"]:
            self.query_light(s, h)
        if got:
            self.save_timer.start()

    def query_light(self, s, h):
        for _, p in self.enabled_rows(26):
            if p["class"] in ("String", "Matrix3", "Material"):
                continue
            key = "26|%s|%s" % (h, p["name"])
            if key not in s["props"]:
                v = maxlink.read_value("node", h, p["name"])
                if v is not None:
                    s["props"][key] = v

    def apply_hdri(self, path):
        """Double click in the HDRI browser: this file becomes the environment of the tab shown in the Environment card
        (of the scene too) and that map is what its list shows. A colour correction on top of the old HDRI is kept."""
        path = os.path.normpath(path)
        s = self.active()
        card = self.cards[6]
        e = card._entry(s) if s else {}
        m = maxlink.use_hdri(path, e.get("cls"), e.get("name"))
        if s is not None:
            # a file typed earlier in a Filename row would override the new one
            store = model.entry_store(s, s["environment"], card.tab)
            for k in [k for k in store if k.startswith("6|") and k.endswith("|filename")]:
                del store[k]
            card.use(m["class"], m["name"])  # the setup puts it in the scene (alone, or in the mix of the tabs)
        else:
            self.applying += 1
            try:
                maxlink.set_environment(m["class"], m["name"])
            finally:
                self.applying -= 1
            self.reload_scene()
        self.toast("Environment: %s" % os.path.basename(path))

    # ------------------------------------------------------------ top bar modes
    def set_preview_mode(self, on):
        self.preview_mode = bool(on)
        self.refresh_cards()
        self.toast("Preview Mode on: click a setup to see it, editing is off" if on else "Preview Mode off")

    def set_camera_sync(self, on):
        self.camera_sync = bool(on)
        if on:
            self.sync_timer.start()
        else:
            self.sync_timer.stop()
        self.toast("Camera Sync on: the viewport camera goes into the active setup" if on else "Camera Sync off")

    def _camera_sync_tick(self):
        s = self.active()
        if s is None or self.rendering or not self.camera_sync:
            return
        h = maxlink.viewport_camera()
        if h is None or h == s["camera"].get("handle"):
            return
        cam = self.scene.camera(h)
        if cam is None:
            self.reload_scene()
            cam = self.scene.camera(h)
        s["camera"].update(handle=h, name=cam["name"] if cam else "")
        self.last_sent = [a for a in self.last_sent if a[0] != "camera"] + [("camera", h, bool(s["camera"]["locked"]), int(self.opts().get("viewport_update_type", 0)))]
        self.changed(apply=False)
        self.refresh_cards([1, 9])

    # ------------------------------------------------------------ setup list
    def setup_columns(self):
        vis = dict(dialogs.DEFAULT_COLUMNS, **self.settings.get("columns_visible", {}))
        self.column_keys = ["grip", "render", "num"] + [k for k, _ in OPTIONAL_COLUMNS if vis.get(k)]
        titles = {"grip": "", "render": "", "num": "#"}
        titles.update(dict(OPTIONAL_COLUMNS))
        self.tree.setColumnCount(len(self.column_keys))
        self.tree.setHeaderLabels([titles[k] for k in self.column_keys])
        h = self.tree.header()
        h.setStretchLastSection(False)
        h.setMinimumSectionSize(20)
        widths = self.settings.get("column_widths", {})
        for i, k in enumerate(self.column_keys):
            if k in ("grip", "render", "num"):
                h.setSectionResizeMode(i, QtWidgets.QHeaderView.Fixed)
                h.resizeSection(i, {"grip": 26, "render": 30, "num": 34}[k])
            elif k == "name":
                h.setSectionResizeMode(i, QtWidgets.QHeaderView.Stretch)
            else:
                h.setSectionResizeMode(i, QtWidgets.QHeaderView.Interactive)
                h.resizeSection(i, max(50, int(widths.get(k, 130))))

    def rebuild_rows(self):
        with Blocker(self.tree):
            self.tree.clear()
            for s in self.setups:
                it = QtWidgets.QTreeWidgetItem()
                it.setData(0, QtCore.Qt.UserRole, s["id"])
                it.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsDragEnabled | QtCore.Qt.ItemIsEditable)
                self.tree.addTopLevelItem(it)
        self.refresh_rows()

    def refresh_rows(self):
        if self.tree.topLevelItemCount() != len(self.setups):
            return self.rebuild_rows()
        bold = QtGui.QFont(self.tree.font())
        bold.setBold(True)
        normal = QtGui.QFont(self.tree.font())
        base = self.tree.palette().color(QtGui.QPalette.Base)
        on_icon = icons.teapot(PRIMARY, True, 18)
        off_icon = icons.teapot(blend(base, text_color(self.tree), 0.45), False, 18)
        grip = icon("grip", 14, blend(base, text_color(self.tree), 0.5))
        active_bg = QtGui.QBrush(blend(base, PRIMARY, 0.22))
        keys = self.column_keys
        with Blocker(self.tree):
            for i, s in enumerate(self.setups):
                it = self.tree.topLevelItem(i)
                it.setData(0, QtCore.Qt.UserRole, s["id"])
                cam = self.scene.camera(s["camera"]["handle"])
                sun = self.scene.light(s["sun"]["handle"]) if s["sun"]["enabled"] else None
                dome = self.scene.light(s["dome"]["handle"]) if s["dome"]["enabled"] else None
                env = s["environment"]
                values = {
                    "num": str(i + 1), "id": str(s["id"]), "name": s["scenename"],
                    "camera": (cam["name"] if cam else (s["camera"].get("name") or "")) if s["camera"]["enabled"] else "",
                    "resolution": "%d * %d" % (s["resolution"]["width"], s["resolution"]["height"]) if s["resolution"]["enabled"] else "",
                    "sun": (sun["name"] + (" +%d" % len(s["sun"].get("extra") or []) if s["sun"].get("extra") else "") if sun else ("Off" if s["sun"]["enabled"] else "")),
                    "dome": (dome["name"] if dome else ("Off" if s["dome"]["enabled"] else "")),
                    "environment": (env.get("name") or "Off") if env["enabled"] else "",
                    "frame": self._frames_text(s),
                }
                for c, k in enumerate(keys):
                    if k in values:
                        it.setText(c, values[k])
                it.setIcon(COL_RENDER, on_icon if s["render"] else off_icon)
                it.setToolTip(COL_RENDER, "Render this setup in the batch (click to switch)")
                if self.check_mode:
                    it.setIcon(COL_GRIP, QtGui.QIcon())
                    it.setCheckState(COL_GRIP, QtCore.Qt.Checked if s["id"] in self.checked else QtCore.Qt.Unchecked)
                else:
                    it.setData(COL_GRIP, QtCore.Qt.CheckStateRole, None)
                    it.setIcon(COL_GRIP, grip)
                color = QtGui.QColor(s.get("color") or "#ffffff")
                plain = color.name().lower() == "#ffffff"
                act = s["id"] == self.active_id
                for c in range(len(keys)):
                    it.setFont(c, bold if act else normal)
                    if c in (COL_GRIP, COL_NUM) and not plain:
                        it.setBackground(c, QtGui.QBrush(color))
                    else:
                        it.setBackground(c, active_bg if act else QtGui.QBrush())
        self.cards[0].refresh()
        self.update_status()

    def _frames_text(self, s):
        f = s["frames"]
        if not f["enabled"]:
            return ""
        if f["kind"] == 1:
            return "%d-%d" % (f["start"], f["end"]) + (" /%d" % f["nth"] if f["nth"] > 1 else "")
        if f["kind"] == 2:
            return f["list"]
        return str(f["single"])

    def _row_clicked(self, it, col):
        sid = it.data(0, QtCore.Qt.UserRole)
        s = next((x for x in self.setups if x["id"] == sid), None)
        if s is None:
            return
        if col == COL_RENDER:
            s["render"] = not s["render"]
            self.changed(apply=False)
            return
        if self.check_mode:
            self.checked.symmetric_difference_update({sid})
            self.refresh_rows()
            return
        mods = QtWidgets.QApplication.keyboardModifiers()
        if mods & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            return
        if sid != self.active_id:
            self.activate(sid)
        else:
            self.review_scripts([s])
            self.last_sent = []
            self._apply()
            self.tell_refused()

    def _row_double(self, it, col):
        if col < len(self.column_keys) and self.column_keys[col] == "name" and not self.locked():
            self.tree.editItem(it, col)

    def _row_edited(self, it, col):
        if col >= len(self.column_keys) or self.column_keys[col] != "name":
            return
        sid = it.data(0, QtCore.Qt.UserRole)
        s = next((x for x in self.setups if x["id"] == sid), None)
        if s is not None and s["scenename"] != it.text(col):
            s["scenename"] = it.text(col)
            self.changed(apply=False, list_too=False)
            if s is self.active():
                self.refresh_cards([15, 9])

    def _reordered(self):
        ids = [self.tree.topLevelItem(i).data(0, QtCore.Qt.UserRole) for i in range(self.tree.topLevelItemCount())]
        by = {s["id"]: s for s in self.setups}
        if sorted(ids) == sorted(by):
            self.setups = [by[i] for i in ids]
        self.changed(apply=False)
        self.refresh_rows()
        self.refresh_cards([9])

    def _row_menu(self, pos):
        it = self.tree.itemAt(pos)
        m = QtWidgets.QMenu(self.tree)
        if it is not None:
            sid = it.data(0, QtCore.Qt.UserRole)
            m.addAction("Activate", lambda: self.activate(sid))
            m.addAction(icons.teapot(PRIMARY, True, 16), "Render this setup",
                        lambda: self.start_render([s for s in self.setups if s["id"] == sid]))
            col = self.column_keys.index("name") if "name" in self.column_keys else 0
            m.addAction(icon("edit"), "Rename", lambda: self.tree.editItem(it, col))
            m.addAction(icon("photo"), "Thumbnail from viewport", lambda: self.fetch_thumbnail(next(s for s in self.setups if s["id"] == sid), "viewport"))
            m.addSeparator()
            m.addAction(icon("dup"), "Duplicate", self.duplicate)
            m.addAction(icon("color"), "Setup color...", self.pick_color)
            m.addAction(icon("delete"), "Remove", self.remove_selected)
            m.addSeparator()
        m.addAction(icon("add"), "Create empty setup", self.add_empty)
        m.addAction(icon("camera"), "Fetch current scene", self.fetch_scene)
        m.addAction("Render: all on", lambda: self._set_all_render(True))
        m.addAction("Render: all off", lambda: self._set_all_render(False))
        m.addSeparator()
        m.addAction(icon("refresh"), "Put back the scene as it was before the setups", self.restore_scene)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _set_all_render(self, on):
        for s in self.setups:
            s["render"] = on
        self.changed(apply=False)

    def _new_id(self):
        self.next_id = max([s["id"] for s in self.setups] + [self.next_id - 1]) + 1
        return self.next_id

    def _add(self, s, activate=True):
        self.setups.append(s)
        self.rebuild_rows()
        self.changed(apply=False)
        if activate:
            self.activate(s["id"])
            it = self.tree.topLevelItem(len(self.setups) - 1)
            self.tree.setCurrentItem(it)
            self.tree.scrollToItem(it)

    def add_empty(self):
        s = model.empty_setup(self._new_id())
        s["camera"]["handle"] = self.scene.active_camera
        cam = self.scene.camera(self.scene.active_camera)
        s["camera"]["name"] = cam["name"] if cam else ""
        s["resolution"].update(width=self.scene.width, height=self.scene.height, ratio=model.ratio(self.scene.width, self.scene.height))
        self._add(s)

    def fetch_scene(self):
        self.reload_scene()
        sc = self.scene
        s = model.empty_setup(self._new_id())
        cam = sc.camera(sc.active_camera)
        s["camera"].update(handle=sc.active_camera, name=cam["name"] if cam else "", locked=bool(cam and cam["locked"]))
        s["resolution"].update(width=sc.width, height=sc.height, ratio=model.ratio(sc.width, sc.height))
        s["layers"]["set"] = [model.layer_entry(l["name"], l["visible"], l.get("frozen", False), l.get("render", True)) for l in sc.layers]
        if sc.env_class:
            s["environment"].update(cls=sc.env_class, name=sc.env_name)
        self._add(s)
        self.toast("Fetched the current scene into a new setup")

    def per_camera(self):
        self.reload_scene()
        used = set(s["camera"]["handle"] for s in self.setups)
        cams = [c for c in self.scene.cameras if c["handle"] not in used]
        if not cams:
            self.toast("Every camera already has a setup")
            return
        for c in cams:
            s = model.empty_setup(self._new_id())
            s["camera"].update(handle=c["handle"], name=c["name"])
            s["resolution"].update(width=self.scene.width, height=self.scene.height, ratio=model.ratio(self.scene.width, self.scene.height))
            self.setups.append(s)
        self.rebuild_rows()
        self.changed(apply=False)
        self.toast("Created %d setup(s), one per camera" % len(cams))

    def new_camera(self):
        h = maxlink.new_camera()
        self.reload_scene()
        s = model.empty_setup(self._new_id())
        cam = self.scene.camera(h)
        s["camera"].update(handle=h, name=cam["name"] if cam else "")
        s["resolution"].update(width=self.scene.width, height=self.scene.height, ratio=model.ratio(self.scene.width, self.scene.height))
        self._add(s)
        self.toast("New camera: %s" % (cam["name"] if cam else h))

    def duplicate(self):
        src = self.selected_setups() or ([self.active()] if self.active() else [])
        if not src:
            return
        for s in src:
            i = self.setups.index(s)
            self.setups.insert(i + 1, model.clone(s, self._new_id()))
        self.rebuild_rows()
        self.changed(apply=False)

    def remove_selected(self):
        sel = self.selected_setups() or ([self.active()] if self.active() else [])
        if not sel:
            return
        if QtWidgets.QMessageBox.question(self, TITLE, "Are you sure you want to remove the selected setup(s)?") != QtWidgets.QMessageBox.Yes:
            return
        ids = set(s["id"] for s in sel)
        self.checked -= ids
        self.setups = [s for s in self.setups if s["id"] not in ids]
        if self.active_id in ids:
            self.active_id = None
        self.rebuild_rows()
        self.refresh_cards()
        self.changed(apply=False)

    def pick_color(self):
        sel = self.selected_setups() or ([self.active()] if self.active() else [])
        if not sel:
            return
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(sel[0].get("color") or "#ffffff"), self, "Setup Color")
        if c.isValid():
            for s in sel:
                s["color"] = c.name()
            self.changed(apply=False)

    # ------------------------------------------------------------ cards
    def refresh_cards(self, only=None):
        for cid, c in self.cards.items():
            if only is not None and cid not in only:
                continue
            if cid not in self.board.items:
                continue
            try:
                c.refresh()
            except Exception:
                traceback.print_exc()

    def clipboard_has(self, cid):
        return cid in self.clipboard

    def _card_data(self, s, cid):
        if cid == 15:
            return s["scenename"]
        if cid == 12:
            return s["notes"]
        return s.get(model.CARD_KEY.get(cid))

    def copy_card(self, cid):
        s = self.active()
        if s is None:
            return
        prefix = "%d|" % cid
        self.clipboard[cid] = (copy.deepcopy(self._card_data(s, cid)), {k: v for k, v in s["props"].items() if k.startswith(prefix)})
        self.toast("Copied %s" % model.CARDS[cid][0])

    def paste_card(self, cid):
        if cid not in self.clipboard:
            return
        data, props = self.clipboard[cid]
        tg = self.targets()
        prefix = "%d|" % cid
        for s in tg:
            if cid == 15:
                s["scenename"] = data
            elif cid == 12:
                s["notes"] = data
            else:
                s[model.CARD_KEY[cid]] = copy.deepcopy(data)
            for k in [k for k in s["props"] if k.startswith(prefix)]:
                del s["props"][k]
            s["props"].update(copy.deepcopy(props))
        self.last_sent = []
        self.changed()
        self.refresh_cards()
        self.toast("Pasted into %d setup(s)" % len(tg))

    def open_property_selector(self, cid):
        tabs = model.tabs_for(cid, self.scene.engine_id)
        checked = self.enabled_keys(cid)
        s = self.active()
        cls = None
        if s is not None:
            if cid == 1:
                n = self.scene.camera(s["camera"]["handle"])
                cls = n["class"] if n else None
            elif cid in (3, 4):
                n = self.scene.light(s["sun" if cid == 3 else "dome"]["handle"])
                cls = (n.get("sun_class") or n["class"]) if n else None
            elif cid == 6:
                cls = s["environment"].get("cls")
        idx = next((i for i, t in enumerate(tabs) if cls and (model.tab_matches(t, cls) or t["v_class"] == cls)), None)
        if idx is None:
            idx = next((i for i, t in enumerate(tabs) if t.get("engine") and t.get("engine") == self.scene.engine_id), None)
        if idx is None:
            on = set(checked)
            idx = next((i for i, t in enumerate(tabs) if any(model.prop_key(t, p) in on for p in t["props"])), 0)
        if cid == 23:
            idx = 0
        dlg = dialogs.PropertySelector(self, model.CARDS[cid][0], tabs, checked, idx)
        if dlg.exec() != QtWidgets.QDialog.Accepted or dlg.result_keys is None:
            return
        keys = dlg.result_keys
        self.settings.setdefault("enabled_props", {})[str(cid)] = keys
        self.save_settings()
        names = set(k.split("|", 1)[1] for k in keys)
        for st in self.setups:
            for k in list(st["props"]):
                parts = k.split("|", 2)
                if parts[0] != str(cid) or len(parts) < 3:
                    continue
                if cid == 26:
                    if parts[2] not in names:
                        del st["props"][k]
                elif "%s|%s" % (parts[1], parts[2]) not in keys:
                    del st["props"][k]
        # a card with settings ticked grows so they fit (it can still be stretched by hand)
        if keys and cid in (1, 3, 4, 6, 25):
            self.board.grow(cid, min(60, 10 + 3 * len([k for k in keys if k.split("|", 1)[0]])))
        self.query_values()
        self.last_sent = []
        self.changed()
        self.refresh_cards()

    # ------------------------------------------------------------ files (.smp presets)
    def _start_dir(self):
        return self.scene.folder or ""

    def export_setups(self):
        sel = self.selected_setups()
        chosen = sel if len(sel) > 1 else self.setups
        f, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Preset", os.path.join(self._start_dir(), "setups.smp"),
                                                     "OpenManager Preset Files (*.smp);;All(*.*)")
        if not f:
            return
        try:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump({"format": "openmanager_preset", "setups": chosen}, fh, indent=1)
            self.toast("Exported %d setup(s)" % len(chosen))
        except Exception as ex:
            self.toast("Could not save the preset: %s" % ex)

    def import_setups(self):
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Preset", self._start_dir(), "OpenManager Preset Files (*.smp)")
        if not f:
            return
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            lst = d.get("setups") if isinstance(d, dict) else d
            if not isinstance(lst, list):
                raise ValueError("not a list of setups")
            for s in lst:
                s = model.normalize(dict(s))
                s["id"] = self._new_id()
                self.resolve_all([s], strict=True)
                self.setups.append(s)
            self.reload_scene()  # the scene read lists the objects the imported setups use
            self.rebuild_rows()
            self.changed(apply=False)
            self.toast("Imported %d setup(s)" % len(lst))
        except Exception:
            traceback.print_exc()
            self.toast("There was error while loading the preset...")

    def export_output_preset(self):
        s = self.active()
        if s is None:
            return
        f, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Output Preset", os.path.join(self._start_dir(), "output.smp"),
                                                     "OpenManager Preset Files (*.smp);;All(*.*)")
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump({"output": s["output"]}, fh, indent=1)
            self.toast("Output preset saved")

    def import_output_preset(self):
        s = self.active()
        if s is None:
            return
        f, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Output Preset", self._start_dir(), "OpenManager Preset Files (*.smp)")
        if not f:
            return
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            out = d["output"]
            for t in self.targets():
                t["output"] = dict(out)
                t["output"]["preset"] = [dict(x) for x in out.get("preset", [])]
            self.changed()
            self.refresh_cards([9])
        except Exception:
            self.toast("Invalid preset")

    # ------------------------------------------------------------ thumbnails, previews, bake
    def thumb_path(self, s):
        folder = self.scene.folder or os.path.join(cfg_dir(), "OpenManager_thumbs")
        stem = os.path.splitext(self.scene.file or "untitled")[0]
        return os.path.join(folder, "OpenManager_thumbs", "%s_%03d.png" % (stem, s["id"])).replace("\\", "/")

    def fetch_thumbnail(self, s, kind):
        if s is None:
            return
        p = self.thumb_path(s)
        ok = maxlink.snapshot_viewport(p) if kind == "viewport" else maxlink.snapshot_vfb(p)
        if ok:
            s["thumbnail"] = p
            self.changed(apply=False)
            self.refresh_cards([31])
        else:
            self.toast("There is no rendered image yet" if kind == "vfb" else "Couldn't grab the viewport")

    def _run_over_setups(self, setups, title, task, step):
        """Applies each setup in turn (like a batch) and calls step(setup, index); Cancel stops it."""
        if not setups or self.rendering:
            return 0
        self.review_scripts(setups)
        self.rendering = True
        self.clear_undo()  # a batch applies many setups: what came before it can no longer be undone
        keep = self.active_id
        dlg = dialogs.BatchDialog(self, len(setups), title, task)
        cancel = {"on": False}
        dlg.cancel.clicked.connect(lambda: cancel.update(on=True))
        dlg.show()
        done = 0
        try:
            for i, s in enumerate(setups):
                if cancel["on"]:
                    break
                dlg.set_job("[%s]" % (s["scenename"] or (self.scene.camera(s["camera"]["handle"]) or {}).get("name", "")), i, len(setups))
                QtWidgets.QApplication.processEvents()
                acts = self.actions_for(s, False)
                self.run_actions(self.base_restore(acts) + acts)
                step(s, self.index_of(s))
                done += 1
                dlg.set_job("", done, len(setups))
        except Exception:
            traceback.print_exc()
            self.toast("Stopped by an error (see the MAXScript Listener)")
        finally:
            dlg.close()
            self.rendering = False
            self.active_id = keep
            self.last_sent = []
            if keep is not None:
                self._apply()
            self.refresh_cards()
        return done

    def viewport_preview(self):
        sel = self.selected_setups() or list(self.setups)

        def step(s, i):
            maxlink.snapshot_viewport(self.thumb_path(s))
            s["thumbnail"] = self.thumb_path(s)
        n = self._run_over_setups(sel, "Viewport Preview", "Viewport snapshot", step)
        if n:
            self.changed(apply=False)
            self.set_card_visible(31, True)
            self.toast("Viewport pictures taken for %d setup(s)" % n)

    def bake_setups(self):
        if not self.setups:
            self.toast("There are no setups")
            return
        for i, s in enumerate(self.setups):
            cam = self.scene.camera(s["camera"]["handle"])
            s["_label"] = s["scenename"] or (cam["name"] if cam else "")
        folder = os.path.join(self.scene.folder or cfg_dir(), "OpenManager_export").replace("\\", "/")
        dlg = dialogs.BakeDialog(self, self.setups, folder)
        for s in self.setups:
            s.pop("_label", None)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        ids = dlg.chosen()
        chosen = [s for s in self.setups if s["id"] in ids]
        method = dlg.method.currentIndex()
        folder = dlg.folder.text().strip() or folder
        stem = os.path.splitext(self.scene.file or "untitled")[0]
        if method in (1, 2):
            os.makedirs(folder, exist_ok=True)

        def label(s, i):
            return "%03d_%s" % (i + 1, (s["scenename"] or (self.scene.camera(s["camera"]["handle"]) or {}).get("name", "setup")).replace(" ", "_"))

        if method == 0:
            def step(s, i):
                if s["camera"].get("handle") is None:
                    return
                path, valid = self.final_path(s)
                preset = os.path.join(self.scene.folder or cfg_dir(), "OpenManager_presets", "%s_%s.rps" % (stem, label(s, i))).replace("\\", "/")
                maxlink.save_preset(preset)
                maxlink.batch_view(s["camera"]["handle"], label(s, i), "SM_" + label(s, i), preset,
                                   path if (s["output"]["enabled"] and valid) else "", int(s["resolution"]["width"]), int(s["resolution"]["height"]))
            n = self._run_over_setups(chosen, "Bake Setups", "Batch Render views", step)
            self.toast("%d view(s) added to Rendering > Batch Render" % n)
        elif method == 1:
            n = self._run_over_setups(chosen, "Bake Setups", "Saving .max files",
                                      lambda s, i: maxlink.save_copy(os.path.join(folder, "%s_%s.max" % (stem, label(s, i)))))
            self.toast("%d .max file(s) saved in %s" % (n, folder))
        elif method == 2:
            from pymxs import runtime as rt

            def step(s, i):
                rt.CoronaRenderer.CoronaFp.exportScene(os.path.join(folder, "%s_%s.scn" % (stem, label(s, i))), False, False)
            n = self._run_over_setups(chosen, "Bake Setups", "Exporting Corona scenes", step)
            self.toast("%d .scn file(s) exported to %s" % (n, folder))
        else:
            code = dlg.code.toPlainText()
            n = self._run_over_setups(chosen, "Bake Setups", "Running your script", lambda s, i: maxlink.run_code(code))
            self.toast("Script run on %d setup(s)" % n)

    # ------------------------------------------------------------ batch render
    def start_render(self, chosen):
        if self.rendering:
            return
        jobs = chosen if chosen is not None else [s for s in self.setups if s["render"]]
        if not jobs:
            self.toast("Please enable one or more scene setups to Render..." if chosen is None else "Select one or more setups first")
            return
        self.save_setups()
        self.reload_scene()
        self.review_scripts(jobs)
        checks = self.check_render(jobs)
        runnable = [s for s, c in zip(jobs, checks) if not c["errors"]]
        if any(c["errors"] or c["warnings"] for c in checks):
            rows = [self._check_row(s, c) for s, c in zip(jobs, checks)]
            if dialogs.BatchCheckDialog(self, rows, len(runnable)).exec() != QtWidgets.QDialog.Accepted:
                return
        skipped = [(s, c) for s, c in zip(jobs, checks) if c["errors"]]
        if not runnable:
            return
        try:
            self._begin_render(runnable, skipped)
        except Exception:
            traceback.print_exc()
            self.rendering = False
            self.widget().setEnabled(True)
            self.toast("The batch could not start (see the MAXScript Listener)")

    def setup_label(self, s):
        cam = self.scene.camera(s["camera"].get("handle"))
        name = s["scenename"] or (cam["name"] if cam else s["camera"].get("name") or "")
        return "#%d %s" % (self.index_of(s) + 1, name)

    def check_render(self, jobs):
        """What each setup of a batch would save, and why one can't be rendered (model.check_jobs)."""
        scene_out = maxlink.render_output()
        info = []
        for s in jobs:
            c = s["camera"]
            missing = ""
            if c["enabled"] and c.get("handle") is not None and self.scene.camera(c["handle"]) is None:
                missing = c.get("name") or "#%s" % c["handle"]
            path, problem = self.build_path(s) if s["output"]["enabled"] else ("", None)
            info.append({"label": self.setup_label(s), "output": bool(s["output"]["enabled"]), "path": path,
                         "problem": problem, "scene_output": scene_out, "camera_missing": missing})
        return model.check_jobs(info)

    def _check_row(self, s, c):
        if c["errors"]:
            return (self.setup_label(s), "Skipped", c["errors"] + c["warnings"])
        if c["warnings"]:
            return (self.setup_label(s), "Warning", c["warnings"] + [c["path"]])
        return (self.setup_label(s), "Ready", [c["path"]])

    def _begin_render(self, jobs, skipped=()):
        self.rendering = True
        self.clear_undo()  # a batch applies many setups: what came before it can no longer be undone
        self.render_jobs = list(jobs)
        self.render_done = 0
        self.render_cancel = False
        # one row per setup for the report: skipped ones first get their reason, the others are filled as they render
        self.render_results = {id(s): (self.setup_label(s), "Skipped", c["errors"]) for s, c in skipped}
        self.render_order = [s for s in self.setups if any(s is x for x in jobs) or any(s is x for x, _ in skipped)]
        self.active_id = None
        self.last_sent = []
        self.refresh_rows()
        self.refresh_cards()
        self.widget().setEnabled(False)
        self.batch = dialogs.BatchDialog(self, len(jobs))
        self.batch.cancel.clicked.connect(self._cancel_render)
        self.batch.show()
        QtCore.QTimer.singleShot(60, self._next_job)

    def _job_label(self, s):
        cam = self.scene.camera(s["camera"]["handle"])
        return "[%s]" % cam["name"] if cam else ""

    def _next_job(self):
        total = len(self.render_jobs)
        if self.render_cancel or self.render_done >= total:
            return self._end_render()
        s = self.render_jobs[self.render_done]
        label = self.setup_label(s)
        self.batch.set_job(self._job_label(s), self.render_done, total)
        QtWidgets.QApplication.processEvents()
        status, details = "Failed", []
        try:
            acts = self.actions_for(s, True)
            refused = len(self._refused)
            self.run_actions(self.base_restore(acts) + acts)
            target = maxlink.render_output()
            if not target:
                # never render a frame that isn't saved
                result = "no output file is set after applying the setup"
            else:
                started = time.time()
                result = maxlink.render()
            if result == "done":
                files = model.find_written(target, started)
                if files:
                    status = "Saved"
                    details = [files[0]] if len(files) == 1 else ["%d files: %s ..." % (len(files), files[0])]
                else:
                    details = ["The render finished but no file was written to %s" % target]
            elif result == "canceled" or maxlink.canceled():
                self.render_cancel = True
                status, details = "Not rendered", ["Canceled"]
            else:
                details = [str(result)]
            if refused:
                details.append("%d script(s) not run: they came with the file and aren't trusted" % refused)
        except Exception as ex:
            traceback.print_exc()
            details = [str(ex)]
        self.render_results[id(s)] = (label, status, details)
        print("OpenManager batch: %s -> %s %s" % (label, status, "; ".join(details)))
        self.render_done += 1  # a failed setup does not stop the batch: the next one renders
        self.batch.set_job(self._job_label(s), self.render_done, total)
        QtCore.QTimer.singleShot(30, self._next_job)

    def _cancel_render(self):
        self.render_cancel = True
        try:
            maxlink.stop_render()
        except Exception:
            pass

    def _end_render(self):
        self.rendering = False
        try:
            self.batch.close()
            self.batch.deleteLater()
        except Exception:
            pass
        self.widget().setEnabled(True)
        self.refresh_cards()
        rows = [self.render_results.get(id(s), (self.setup_label(s), "Not rendered", ["Canceled before it started"]))
                for s in self.render_order]
        count = lambda st: sum(1 for r in rows if r[1] == st)
        summary = "%d saved, %d failed, %d skipped" % (count("Saved"), count("Failed"), count("Skipped"))
        if self.render_cancel:
            summary = "Batch Render canceled: " + summary + ", %d not rendered" % count("Not rendered")
        else:
            summary = "Batch Render finished: " + summary
        print("OpenManager: " + summary)
        self.last_report = rows
        self.toast(summary)
        if any(r[1] != "Saved" for r in rows) or len(rows) > 1:
            self.report = dialogs.BatchReportDialog(self, rows, summary)
            self.report.show()

    # ------------------------------------------------------------ storing setups in the .max file
    def encoded(self):
        extra = {}
        if self.rs_default:
            extra["rs_default"] = self.rs_default
        if self.base:
            extra["base"] = model.base_to_json(self.base)
        return model.encode(self.setups, self.todo, extra or None)

    def save_setups(self):
        if self.loading:
            return  # another file is being opened; its own setups will be read
        try:
            self.stamp_uids()
        except Exception:
            traceback.print_exc()
        text = self.encoded()
        if text == self.last_saved:
            return
        try:
            maxlink.save_setups(text)
            self.last_saved = text
        except Exception:
            traceback.print_exc()

    # ------------------------------------------------------------ closing
    def closeEvent(self, e):
        try:
            if self.save_timer.isActive():
                self.save_timer.stop()
                self.save_setups()
            self.sync_timer.stop()
            self.save_settings()
            maxlink.watch(None)
        except Exception:
            traceback.print_exc()
        widgets.PALETTE_OVERRIDE = None
        from . import _closed
        _closed(self)
        super(SceneManager, self).closeEvent(e)
