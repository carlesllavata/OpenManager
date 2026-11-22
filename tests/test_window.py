# SPDX-License-Identifier: GPL-3.0-or-later
"""What the window lets through and tells when the setups of a file are applied (window.py on a fake 3ds Max).

The methods under test are the real ones of window.SceneManager, used by an object that has none of its widgets
(Window below): opening a file, clicking a setup, Batch Render, Bake Setups."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "package", "OpenManager"))
import fake_max  # noqa: E402

rt = fake_max.install()
from openmanager import folders, maxlink, model, open3d_settings  # noqa: E402

try:
    from openmanager import cards, window
except ImportError as ex:  # PySide6 comes with the Python of 3ds Max
    raise unittest.SkipTest("the window needs PySide6 (%s)" % ex) from ex

SCENE = {
    "file": "scene.max",
    "folder": "",
    "engine": "Corona",
    "cameras": [{"handle": 7, "name": "Cam", "class": "CoronaCam", "locked": False}],
}
CLASS_TOAST = (
    "%d class name(s) of this file were not used: they are not operator or map classes (see the MAXScript Listener)"
)
SETTING_TOAST = (
    "%d setting(s) of this file were not applied: OpenManager's cards don't set them (see the MAXScript Listener)"
)
SCRIPT_TOAST = "%d script(s) of this setup were not run: they came with the file and aren't trusted"
PRESET_TOAST = "The render preset of this setup was not loaded: it came with the file and isn't trusted"


class Holder(object):
    def __init__(self, **values):
        self.__dict__.update(values)


class Timer(object):
    def start(self, *args):
        pass

    def stop(self):
        pass

    def isActive(self):
        return False


class Window(object):
    """window.SceneManager without widgets: the methods listed in REAL are its own; what they need from the widgets
    is below (toasts and questions are kept instead of shown)."""

    REAL = (
        "reload_all",
        "encoded",
        "object_handles",
        "opts",
        "active",
        "index_of",
        "enabled_keys",
        "enabled_rows",
        "build_path",
        "final_path",
        "setup_label",
        "toast",
        "actions_for",
        "script_allowed",
        "trust_scripts",
        "typed_code",
        "review_scripts",
        "tell_refused",
        "tell_rejected",
        "run_actions",
        "_apply",
        "_apply_edit",
        "base_restore",
        "restore_scene",
        "activate",
        "begin_undo",
        "undo_capture",
        "end_undo",
        "clear_undo",
        "update_undo_buttons",
        "undo",
        "redo",
        "_run_over_setups",
        "viewport_preview",
        "bake_setups",
        "thumb_path",
        "start_render",
        "check_render",
        "_check_row",
        "_begin_render",
        "_job_label",
        "_next_job",
        "_cancel_render",
        "_end_render",
        "targets",
        "_start_dir",
    )
    column_keys = ()  # the columns of the setup list (it has none)

    def __init__(self, stored="", settings=None, answer=False, pulze=""):
        """stored: the text of rootNode.OpenManager_Dat (pulze: of Pulze's SceneManager_Dat); answer: what the person
        says when asked about scripts."""
        self.settings = settings or {}
        self.answer = answer
        self.toasts, self.asked = [], []
        self.toast_label = Holder(show_text=lambda text, ms=3500: self.toasts.append(text))
        self.save_timer = self.apply_timer = self.list_timer = Timer()
        self.scene, self.setups, self.todo, self.rs_default, self.base = maxlink.Scene(), [], [], {}, {}
        self.undo_stack, self.redo_stack, self._undo_rec = [], [], None
        self._typed, self._denied, self._refused, self._refused_presets = {}, set(), [], []
        self.active_id, self.next_id, self.last_sent, self.last_saved = None, 1, [], None
        self.rendering, self.loading, self.applying = False, False, 0
        self.pc_name, self.user_name = "PC", "me"
        rt.returns["omgr_readKey"] = lambda key: {maxlink.DATA_KEY: stored, maxlink.PULZE_KEY: pulze}.get(key, "")
        rt.returns["omgr_scene"] = lambda **kw: json.dumps(SCENE)
        self.reload_all()

    def ask_scripts(self, rows):
        self.asked.append(rows)
        return self.answer

    def nothing(self, *args, **kwargs):
        pass

    save_settings = save_setups = reload_scene = resolve_scene_refs = query_values = nothing
    layout_cards = rebuild_rows = refresh_rows = refresh_cards = update_status = changed = set_card_visible = nothing

    def resolve_all(self, setups=None, strict=False):
        return False

    def selected_setups(self):
        return []

    def widget(self):
        return Holder(setEnabled=self.nothing)

    def isFloating(self):
        return True

    def geometry(self):
        return Holder(x=lambda: 10, y=lambda: 20, width=lambda: 900, height=lambda: 1000)

    def parent(self):
        return None


for _name in Window.REAL:
    setattr(Window, _name, getattr(window.SceneManager, _name))


def stored(setups, **extra):
    """The text a file keeps in rootNode.OpenManager_Dat."""
    return model.encode(setups, [], extra or None)


def setup(sid=1, ops=None, **scripts):
    """A setup that only sets what is asked: tone-mapping operators (Post-Production card), scripts (pre_setup,
    post_setup, pre_render, post_render: Script Editor card; pre_file, post_file: Script File card) and a render
    preset (preset: Render Settings - Preset card)."""
    s = model.empty_setup(sid)
    s["resolution"]["enabled"] = False
    s["camera"].update(handle=7, name="Cam")
    if ops is not None:
        s["post"].update(enabled=True, cats={"tonemap": {"ops": ops}})
    if scripts.get("preset"):
        s["render_preset"].update(enabled=True, path=scripts.pop("preset"))
    code = {k: v for k, v in scripts.items() if not k.endswith("_file")}
    if code:
        s["snippet"].update(enabled=True, **code)
    for key in ("pre", "post"):
        if scripts.get(key + "_file"):
            s["scripts"]["enabled"] = True
            s["scripts"][key + "_render"] = {"enabled": True, "path": scripts[key + "_file"]}
    return s


def quiet(fn, *args, **kwargs):
    """Runs fn; returns what it wrote to the MAXScript Listener."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        fn(*args, **kwargs)
    return out.getvalue()


def called(name):
    return [c[1:] for c in rt.calls if c[0] == name]


def opened(text, **kwargs):
    """The window after a file with this stored text was opened (what that wrote to the Listener is dropped)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return Window(text, **kwargs)


class Dialog(object):
    """Stands for the dialogs of a batch (progress, check, report): nothing is shown, every question is accepted."""

    def __init__(self, *args, **kwargs):
        self.cancel = Holder(clicked=Holder(connect=lambda fn: None))

    def exec(self):
        return window.QtWidgets.QDialog.Accepted

    def nothing(self, *args, **kwargs):
        pass

    show = close = deleteLater = set_job = nothing


def bake_dialog(method, ids, code=""):
    """Stands for the Bake Setups dialog with these choices made (method: its place in dialogs.BakeDialog.METHODS)."""

    class BakeDialog(Dialog):
        def __init__(self, parent, setups, folder):
            self.method = Holder(currentIndex=lambda: method)
            self.folder = Holder(text=lambda: folder)
            self.code = Holder(toPlainText=lambda: code)

        def chosen(self):
            return ids

    return BakeDialog


def batch_render(w, chosen=None):
    """Batch Render from the button to the report; the timers of the window are run here, one after the other.
    Returns the rows of the report: (setup, status, details)."""
    later = []
    timers = Holder(QTimer=Holder(singleShot=lambda ms, fn: later.append(fn)))
    with (
        mock.patch.object(window, "QtCore", timers),
        mock.patch.object(window.dialogs, "BatchDialog", Dialog),
        mock.patch.object(window.dialogs, "BatchCheckDialog", Dialog),
        mock.patch.object(window.dialogs, "BatchReportDialog", Dialog),
    ):
        quiet(w.start_render, chosen)
        while later:
            quiet(later.pop(0))
    return w.last_report


def bake(w, method, ids, code=""):
    with (
        mock.patch.object(window.dialogs, "BakeDialog", bake_dialog(method, ids, code)),
        mock.patch.object(window.dialogs, "BatchDialog", Dialog),
        mock.patch.object(window, "data_dir", tempfile.gettempdir),
    ):
        quiet(w.bake_setups)


def viewport_preview(w):
    with (
        mock.patch.object(window.dialogs, "BatchDialog", Dialog),
        mock.patch.object(window, "data_dir", tempfile.gettempdir),
    ):
        quiet(w.viewport_preview)


class Base(unittest.TestCase):
    def setUp(self):
        rt.reset()
        rt.add_node(7, "CoronaCam", "Cam")
        rt.returns["omgr_render"] = "done"
        # the scene saves its renders, so a batch has nothing to stop for
        rt._globals.update(
            rendSaveFile=True, rendOutputFilename=os.path.join(tempfile.gettempdir(), "omgr_no_such_folder", "a.png")
        )
        maxlink.take_rejected()


class ClassNamesLeftOut(Base):
    BAD = [{"class": 'Box(); messageBox "x"', "props": {}}, {"class": "Box", "props": {}}]
    GOOD = [{"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_highlightCompression": 2.0}}]

    def test_clicking_a_setup_tells(self):
        w = Window(stored([setup(1, self.BAD + self.GOOD)]))
        listener = quiet(w.activate, 1)
        self.assertEqual(rt.executed, [])
        self.assertEqual([str(o.cls) for o in rt.chain()], ["FilmicOperatorPlugin"])
        self.assertEqual(w.toasts, [CLASS_TOAST % 2])
        self.assertIn(
            'OpenManager: left out "Box(); messageBox "x"": it is not a tone-mapping operator class', listener
        )
        self.assertIn('OpenManager: left out "Box": it is not a tone-mapping operator class', listener)

    def test_a_setup_with_real_classes_tells_nothing(self):
        w = Window(stored([setup(1, self.GOOD)]))
        listener = quiet(w.activate, 1)
        self.assertEqual(w.toasts, [])
        self.assertNotIn("left out", listener)
        self.assertEqual([str(o.cls) for o in rt.chain()], ["FilmicOperatorPlugin"])

    def test_scripts_and_class_names_in_one_message(self):
        w = Window(stored([setup(1, self.BAD, pre_setup="print 1")]))
        quiet(w.activate, 1)
        self.assertEqual(w.toasts, [SCRIPT_TOAST % 1 + "\n" + CLASS_TOAST % 2])
        self.assertEqual(called("omgr_runCode"), [])

    def test_scripts_alone_are_told_as_before(self):
        w = Window(stored([setup(1, self.GOOD, pre_setup="print 1")]))
        quiet(w.activate, 1)
        self.assertEqual(w.toasts, [SCRIPT_TOAST % 1])

    def test_map_classes_left_out_by_omgr_core_are_told(self):
        w = Window(stored([setup(1)]))
        rt.bad_classes = ['Box(); messageBox "x"']  # what omgr_mapClass keeps for a name that is not a map class
        quiet(w.activate, 1)
        self.assertEqual(w.toasts, [CLASS_TOAST % 1])

    def test_an_edit_of_the_active_setup_tells(self):
        w = Window(stored([setup(1, self.GOOD)]))
        quiet(w.activate, 1)
        w.active()["post"]["cats"]["tonemap"]["ops"].append({"class": "a;b", "props": {}})
        quiet(w._apply_edit)
        self.assertEqual(rt.executed, [])
        self.assertEqual(w.toasts, [CLASS_TOAST % 1])

    def test_told_once(self):
        w = Window(stored([setup(1, self.BAD), setup(2, self.GOOD)]))
        quiet(w.activate, 1)
        quiet(w.activate, 2)
        self.assertEqual(w.toasts, [CLASS_TOAST % 2])

    def test_undo_and_putting_the_scene_back_tell_too(self):
        w = Window(stored([setup(1, self.GOOD)]))
        quiet(w.activate, 1)
        rt.bad_classes = ["a;b"]
        quiet(w.undo)
        self.assertEqual(w.toasts[-1], CLASS_TOAST % 1)
        quiet(w.activate, 1)
        rt.bad_classes = ["a;b"]
        quiet(w.restore_scene)
        self.assertEqual(w.toasts[-1], CLASS_TOAST % 1)


class StoredBaseState(Base):
    """The base state (what the setup applied before changed) is stored in the file and put back without being
    shown, so nothing in it may run a script."""

    HIDDEN = [
        [["x"], ["code", 'messageBox "x"']],
        [["y"], ["renderscripts", "D:/s/pre.ms", "", "print 3", ""]],
        [["z"], ["preset", "D:/s/a.rps"]],
    ]
    BASE_TOAST = "3 stored change(s) of this file were ignored: they could run a script without asking"

    def assert_no_script(self):
        self.assertEqual(rt.executed, [])
        self.assertEqual(called("omgr_runCode"), [])
        self.assertEqual(called("omgr_loadPreset"), [])
        self.assertEqual(set(called("omgr_setRenderScripts")) - {("", "", "", "")}, set())

    def test_opening_the_file_leaves_them_out_and_tells(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            w = Window(stored([setup(1)], base=self.HIDDEN + [[["res"], ["res", 800, 600]]]))
        self.assertEqual(w.base, {("res",): ("res", 800, 600)})
        self.assertEqual(w.toasts, [self.BASE_TOAST])
        self.assertIn("OpenManager: ignored 3 stored change(s) of this file", out.getvalue())

    def test_clicking_a_setup_runs_none_of_them(self):
        w = opened(stored([setup(1)], base=self.HIDDEN))
        quiet(w.activate, 1)
        self.assert_no_script()
        self.assertEqual(w.asked, [])

    def test_putting_the_scene_back_runs_none_of_them(self):
        w = opened(stored([setup(1)], base=self.HIDDEN + [[["res"], ["res", 800, 600]]]))
        quiet(w.restore_scene)
        self.assert_no_script()
        self.assertEqual(called("omgr_setRes"), [(800, 600)])

    def test_always_run_scripts_does_not_cover_them(self):
        # the setting is about the scripts the cards show; these are in no card
        w = opened(stored([setup(1)], base=self.HIDDEN), settings={"max": {"scripts": "always"}})
        quiet(w.activate, 1)
        self.assert_no_script()

    def test_a_base_of_openmanager_is_put_back_as_before(self):
        base = model.base_to_json({("res",): ("res", 800, 600), ("rs", "gi"): ("rs", "gi", 1)})
        w = Window(stored([setup(1)], base=base))
        self.assertEqual(w.toasts, [])
        quiet(w.activate, 1)
        self.assertEqual(called("omgr_setRes"), [(800, 600)])
        self.assertEqual(called("omgr_setRS"), [("gi", 1)])


class SettingsOfAFile(Base):
    """A change names the property it sets; the setups and the base state of a file only set what the cards set."""

    CODE = "OM_PAYLOAD_RAN = true"
    READS = ("omgr_getRawNode", "omgr_getRawRS", "omgr_getRawLayer", "omgr_getRawMap")

    def test_a_base_state_can_not_write_the_script_of_a_script_controller(self):
        w = opened(
            stored([setup(1)], base=[[["node", 7, "controller.script"], ["node", 7, "controller.script", self.CODE]]])
        )
        listener = quiet(w.activate, 1)
        self.assertEqual(rt.executed, [])
        self.assertEqual(called("omgr_setNode"), [])
        self.assertEqual([c for c in rt.calls if c[0] in self.READS], [])
        self.assertEqual(w.toasts, [SETTING_TOAST % 1])
        self.assertIn('OpenManager: left out the object setting "controller.script": it holds code', listener)
        self.assertEqual(w.base, {})

    def test_nor_when_the_scene_is_put_back(self):
        w = opened(
            stored(
                [setup(1)],
                base=[
                    [["node", 7, "Proceed_Script"], ["node", 7, "Proceed_Script", self.CODE]],
                    [["rs", "a.b.script"], ["rs", "a.b.script", self.CODE]],
                    [["map", "Checker", "m", "coords.x"], ["map", "Checker", "m", "coords.x", 1]],
                    [["layer", "0", "x.y"], ["layer", "0", "x.y", True]],
                    [["res"], ["res", 800, 600]],
                ],
            )
        )
        quiet(w.restore_scene)
        self.assertEqual([c[0] for c in rt.calls if c[0].startswith("omgr_set")], ["omgr_setRes"])
        self.assertEqual(w.toasts[-1], SETTING_TOAST % 4)

    def test_a_setup_can_not_reach_other_objects_through_the_renderer(self):
        s = setup(1)
        s["rs_override"].update(enabled=True, set={"bg_texmap.coords.script": self.CODE, "a.b": 1, "gi_on": True})
        s["post"].update(
            enabled=True, cats={"bloom": {"props": {"x.controller.script": self.CODE, "bloomGlare_enabled": True}}}
        )
        w = opened(stored([s], rs_default={"other.path": 1, "progressive_passLimit": 5}))
        quiet(w.activate, 1)
        self.assertEqual(
            sorted(called("omgr_setRS")), [("bloomGlare_enabled", True), ("gi_on", True), ("progressive_passLimit", 5)]
        )
        self.assertEqual(
            sorted(set(c[1] for c in rt.calls if c[0] == "omgr_getRawRS")),
            ["bloomGlare_enabled", "gi_on", "progressive_passLimit"],
        )
        self.assertEqual(w.toasts, [SETTING_TOAST % 4])

    def test_everything_left_out_is_told_in_one_message(self):
        s = setup(
            1,
            [{"class": "a;b", "props": {}}, {"class": "FilmicOperatorPlugin", "props": {"x.y": 1}}],
            pre_setup="print 1",
        )
        w = opened(stored([s], base=[[["node", 7, "controller.script"], ["node", 7, "controller.script", self.CODE]]]))
        quiet(w.activate, 1)
        self.assertEqual(w.toasts, ["\n".join([SCRIPT_TOAST % 1, CLASS_TOAST % 1, SETTING_TOAST % 2])])

    def test_what_omgr_core_refused_is_told(self):
        w = opened(stored([setup(1)]))
        rt.bad_props = ["controller.script"]  # what omgr_propOk keeps
        quiet(w.activate, 1)
        self.assertEqual(w.toasts, [SETTING_TOAST % 1])

    def test_batch_render_says_it_in_its_report(self):
        w = opened(
            stored([setup(1)], base=[[["node", 7, "controller.script"], ["node", 7, "controller.script", self.CODE]]])
        )
        report = batch_render(w)
        self.assertEqual(called("omgr_setNode"), [])
        self.assertIn("1 setting(s) not applied: OpenManager's cards don't set them", report[0][2])

    # ---- what the cards make keeps working
    def test_render_settings_override_as_the_card_stores_it(self):
        s = setup(1)
        s["rs_override"].update(
            enabled=True, set={"gi_on": True, "lut_path": "D:/luts/a.cube", "progressive_passLimit": 20}
        )
        w = opened(stored([s], rs_default={"gi_on": False, "progressive_passLimit": 5, "image_filter_width": 1.5}))
        listener = quiet(w.activate, 1)
        self.assertEqual(
            called("omgr_setRS"),
            [
                ("image_filter_width", 1.5),
                ("gi_on", True),
                ("lut_path", "D:/luts/a.cube"),
                ("progressive_passLimit", 20),
            ],
        )
        self.assertEqual(w.toasts, [])
        self.assertNotIn("left out", listener)

    def test_post_production_as_the_card_stores_it(self):
        s = setup(
            1,
            [
                {
                    "class": "FilmicOperatorPlugin",
                    "props": {"colorMappingOperator_highlightCompression": 2.0, "colorMappingOperator_enabled": True},
                }
            ],
        )
        s["post"]["cats"].update({key: {"props": {n: True for n in names}} for key, _, names in model.POST_CATS})
        w = opened(stored([s]))
        quiet(w.activate, 1)
        self.assertEqual(
            sorted(c[0] for c in called("omgr_setRS")), sorted(n for _, _, names in model.POST_CATS for n in names)
        )
        self.assertEqual(rt.chain()[0].props["colorMappingOperator_highlightCompression"], 2.0)
        self.assertEqual(w.toasts, [])

    def test_ticked_settings_of_a_camera(self):
        tab = next(t for t in model.tabs_for(1, "corona") if t["v_class"] == "CoronaCam")
        names = [p["name"] for p in tab["props"] if p["class"] in ("Float", "BooleanClass", "Integer")][:5]
        s = setup(1)
        for n in names:
            s["props"]["1|CoronaCam|%s" % n] = 1
        w = opened(stored([s]), settings={"enabled_props": {"1": ["CoronaCam|%s" % n for n in names]}})
        quiet(w.activate, 1)
        self.assertEqual(sorted(c[1] for c in called("omgr_setNode")), sorted(names))
        self.assertEqual(w.toasts, [])

    def test_a_setup_converted_from_pulze(self):
        import base64

        cam = next(
            p["name"]
            for t in model.tabs_for(1, "corona")
            if t["v_class"] == "CoronaCam"
            for p in t["props"]
            if p["class"] == "Float"
        )
        rs = next(p["name"] for t in model.tabs_for(25, "corona") for p in t["props"] if p["class"] == "BooleanClass")
        pulze = [
            {
                "camera": {
                    "enabled": True,
                    "handle": 7,
                    "props": [{"name": cam, "v_class": "CoronaCam", "value": "35.5"}],
                },
                "renderCustom": {
                    "enabled": "true",
                    "props": [
                        {"name": rs, "v_class": "CoronaRenderer", "value": "true"},
                        {"name": "a.b.script", "v_class": "CoronaRenderer", "value": self.CODE},
                    ],
                },
                "objects": {
                    "enabled": True,
                    "set": [
                        {
                            "handle": 7,
                            "name": "Cam",
                            "props": [
                                {"name": "isNodeHidden", "value": "true"},
                                {"name": "renderable", "value": False},
                                {"name": "script", "value": True},
                            ],
                        }
                    ],
                },
                "layers": {
                    "enabled": True,
                    "set": [
                        {"name": "0", "props": [{"name": "on", "value": False}, {"name": "script", "value": True}]}
                    ],
                },
            }
        ]
        text = base64.b64encode(json.dumps(pulze).encode("utf-8")).decode("ascii")
        w = opened(
            "", pulze=text, settings={"enabled_props": {"1": ["CoronaCam|" + cam], "25": ["CoronaRenderer|" + rs]}}
        )
        self.assertEqual(w.toasts, ["Read 1 setup(s) saved by Pulze Scene Manager in this file"])
        listener = quiet(w.activate, 1)
        self.assertIn((7, cam, 35.5), called("omgr_setNode"))
        self.assertIn((7, "isHidden", True), called("omgr_setNode"))
        self.assertIn((7, "renderable", False), called("omgr_setNode"))
        self.assertIn(("0", "on", False), called("omgr_setLayer"))
        self.assertEqual(called("omgr_setRS"), [(rs, True)])
        # names Pulze stored that are not in the table never become a change: nothing to leave out
        self.assertEqual(len(w.toasts), 1)
        self.assertNotIn("left out", listener)


class ScriptsOfAFile(Base):
    """Batch Render and Bake Setups apply setups too: the scripts that came with the file go through the same
    question and the same check as when a setup is clicked."""

    FILE = "D:/s/pre.ms"

    def setups(self):
        return [
            setup(
                1,
                pre_setup="print 1",
                post_setup="print 2",
                pre_render="print 3",
                post_render="print 4",
                pre_file=self.FILE,
            ),
            setup(2, pre_setup="print 5"),
        ]

    def all_scripts(self):
        return [
            ("#1 Cam", "Pre-Setup script", "code", "print 1"),
            ("#1 Cam", "Post-Setup script", "code", "print 2"),
            ("#1 Cam", "Pre-Render script", "code", "print 3"),
            ("#1 Cam", "Post-Render script", "code", "print 4"),
            ("#1 Cam", "Pre-Render file", "file", self.FILE),
            ("#2 Cam", "Pre-Setup script", "code", "print 5"),
        ]

    def assert_no_script_ran(self):
        self.assertEqual(rt.executed, [])
        self.assertEqual(called("omgr_runCode"), [])
        self.assertTrue(called("omgr_setRenderScripts"))
        self.assertEqual(set(called("omgr_setRenderScripts")), {("", "", "", "")})

    def assert_scripts_ran(self):
        self.assertEqual(called("omgr_runCode"), [("print 1",), ("print 2",), ("print 5",)])
        self.assertEqual(called("omgr_setRenderScripts"), [(self.FILE, "", "print 3", "print 4"), ("", "", "", "")])

    # ---- Batch Render
    def test_batch_render_asks_first_and_runs_nothing_when_refused(self):
        w = Window(stored(self.setups()), answer=False)
        report = batch_render(w)
        self.assertEqual(w.asked, [self.all_scripts()])
        self.assert_no_script_ran()
        self.assertEqual(len(called("omgr_render")), 2)
        self.assertIn("5 script(s) not run: they came with the file and aren't trusted", report[0][2])
        self.assertIn("1 script(s) not run: they came with the file and aren't trusted", report[1][2])

    def test_batch_render_runs_them_once_the_person_agrees(self):
        w = Window(stored(self.setups()), answer=True)
        report = batch_render(w)
        self.assertEqual(w.asked, [self.all_scripts()])
        self.assert_scripts_ran()
        self.assertFalse([line for row in report for line in row[2] if "script(s) not run" in line])
        self.assertEqual(len(w.settings["trusted_scripts"]), 6)

    def test_batch_render_of_selected_setups(self):
        w = Window(stored(self.setups()), answer=False)
        batch_render(w, [w.setups[1]])
        self.assertEqual(w.asked, [self.all_scripts()[5:]])
        self.assert_no_script_ran()

    def test_batch_render_never_run_them(self):
        w = Window(stored(self.setups()), settings={"max": {"scripts": "never"}}, answer=True)
        batch_render(w)
        self.assertEqual(w.asked, [])
        self.assert_no_script_ran()

    def test_batch_render_always_run_them(self):
        w = Window(stored(self.setups()), settings={"max": {"scripts": "always"}})
        batch_render(w)
        self.assertEqual(w.asked, [])
        self.assert_scripts_ran()

    def test_a_refusal_holds_for_the_next_batch_without_asking_again(self):
        w = Window(stored(self.setups()), answer=False)
        batch_render(w)
        w.answer = True
        batch_render(w)
        self.assertEqual(len(w.asked), 1)
        self.assert_no_script_ran()

    def test_a_script_changed_after_it_was_trusted_is_asked_about_again(self):
        w = Window(stored(self.setups()), answer=True)
        batch_render(w)
        w.setups[1]["snippet"]["pre_setup"] = 'messageBox "changed"'
        w.answer = False
        del rt.calls[:]
        batch_render(w)
        self.assertEqual(w.asked[1], [("#2 Cam", "Pre-Setup script", "code", 'messageBox "changed"')])
        self.assertEqual(called("omgr_runCode"), [("print 1",), ("print 2",)])

    def test_batch_render_does_not_run_a_class_name_either(self):
        w = Window(stored([setup(1, [{"class": 'Box(); messageBox "x"', "props": {}}])]))
        report = batch_render(w)
        self.assertEqual(rt.executed, [])
        self.assertIn("1 class name(s) not used: they are not operator or map classes", report[0][2])

    # ---- Bake Setups
    def test_bake_asks_first_and_runs_nothing_when_refused(self):
        for method in (0, 3):  # Batch Render views; a script of your own on every setup
            self.setUp()
            w = Window(stored(self.setups()), answer=False)
            bake(w, method, [1, 2], "print mine")
            self.assertEqual(w.asked, [self.all_scripts()], method)
            self.assertEqual(rt.executed, [])
            # the only script that runs is the one typed in the Bake Setups dialog, once per setup
            self.assertEqual(called("omgr_runCode"), [("print mine",)] * 2 if method == 3 else [])
            self.assertEqual(set(called("omgr_setRenderScripts")), {("", "", "", "")})
            self.assertEqual(len(called("omgr_batchView")), 2 if method == 0 else 0)

    def test_bake_runs_them_once_the_person_agrees(self):
        w = Window(stored(self.setups()), answer=True)
        bake(w, 0, [1, 2])
        self.assertEqual(w.asked, [self.all_scripts()])
        self.assert_scripts_ran()

    def test_bake_of_some_setups_asks_about_theirs_only(self):
        w = Window(stored(self.setups()), answer=False)
        bake(w, 0, [2])
        self.assertEqual(w.asked, [self.all_scripts()[5:]])
        self.assert_no_script_ran()

    def test_bake_never_run_them(self):
        w = Window(stored(self.setups()), settings={"max": {"scripts": "never"}}, answer=True)
        bake(w, 3, [1, 2], "print mine")
        self.assertEqual(w.asked, [])
        self.assertEqual(called("omgr_runCode"), [("print mine",)] * 2)
        self.assertEqual(set(called("omgr_setRenderScripts")), {("", "", "", "")})

    def test_viewport_preview_goes_the_same_way(self):
        w = Window(stored(self.setups()), answer=False)
        viewport_preview(w)
        self.assertEqual(w.asked, [self.all_scripts()])
        self.assert_no_script_ran()
        self.assertEqual(len(called("omgr_snapshotViewport")), 2)

    # ---- the same answer everywhere
    def test_an_answer_given_for_a_bake_holds_for_a_click(self):
        w = Window(stored(self.setups()), answer=True)
        bake(w, 0, [1, 2])
        del rt.calls[:]
        quiet(w.activate, 2)
        self.assertEqual(len(w.asked), 1)
        self.assertEqual(called("omgr_runCode"), [("print 5",)])

    def test_a_base_state_of_the_file_runs_no_script_in_a_batch_or_a_bake(self):
        hidden = [[["x"], ["code", 'messageBox "x"']], [["y"], ["renderscripts", self.FILE, "", "print 3", ""]]]
        for go in (batch_render, lambda w: bake(w, 0, [1])):
            self.setUp()
            w = opened(stored([setup(1)], base=hidden))
            go(w)
            self.assert_no_script_ran()
            self.assertEqual(w.asked, [])


class RenderPresetOfAFile(Base):
    """The render preset of a setup (Render Settings - Preset card) is a file that replaces the render settings; its
    path comes with the setup. It is asked about and trusted like a script file."""

    PRESET = "D:/project/presets/final.rps"
    ROW = ("#1 Cam", "Render preset", "preset", PRESET)

    def file(self, **more):
        return stored([setup(1, preset=self.PRESET, **more)])

    # ---- a click on the setup
    def test_it_is_shown_and_not_loaded_when_refused(self):
        w = Window(self.file(), answer=False)
        quiet(w.activate, 1)
        self.assertEqual(w.asked, [[self.ROW]])
        self.assertEqual(called("omgr_loadPreset"), [])
        self.assertEqual(w.toasts, [PRESET_TOAST])

    def test_it_is_loaded_once_the_person_agrees_and_not_asked_about_again(self):
        w = Window(self.file(), answer=True)
        quiet(w.activate, 1)
        self.assertEqual(w.asked, [[self.ROW]])
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])
        self.assertEqual(w.toasts, [])
        self.assertEqual(w.settings["trusted_scripts"], [model.script_key("preset", self.PRESET)])
        w.answer = False
        quiet(w.activate, 1)  # clicked again
        self.assertEqual(len(w.asked), 1)

    def test_a_refusal_holds_for_the_session(self):
        w = Window(self.file(), answer=False)
        quiet(w.activate, 1)
        w.answer = True
        quiet(w.activate, 1)
        self.assertEqual(len(w.asked), 1)
        self.assertEqual(called("omgr_loadPreset"), [])

    def test_never(self):
        w = Window(self.file(), settings={"max": {"scripts": "never"}}, answer=True)
        quiet(w.activate, 1)
        self.assertEqual(w.asked, [])
        self.assertEqual(called("omgr_loadPreset"), [])
        self.assertEqual(w.toasts, [PRESET_TOAST])

    def test_always(self):
        w = Window(self.file(), settings={"max": {"scripts": "always"}})
        quiet(w.activate, 1)
        self.assertEqual(w.asked, [])
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])

    def test_scripts_and_the_preset_are_asked_about_together(self):
        w = Window(self.file(pre_setup="print 1"), answer=False)
        quiet(w.activate, 1)
        self.assertEqual(w.asked, [[("#1 Cam", "Pre-Setup script", "code", "print 1"), self.ROW]])
        self.assertEqual(called("omgr_loadPreset") + called("omgr_runCode"), [])
        self.assertEqual(w.toasts, [SCRIPT_TOAST % 1 + "\n" + PRESET_TOAST])

    def test_another_path_is_another_preset(self):
        w = Window(self.file(), answer=True)
        quiet(w.activate, 1)
        w.setups[0]["render_preset"]["path"] = "//server/share/other.rps"
        w.answer = False
        quiet(w.activate, 1)
        self.assertEqual(w.asked[1], [("#1 Cam", "Render preset", "preset", "//server/share/other.rps")])
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])

    def test_a_card_that_is_off_loads_nothing_and_asks_nothing(self):
        s = setup(1, preset=self.PRESET)
        s["render_preset"]["enabled"] = False
        w = Window(stored([s]))
        quiet(w.activate, 1)
        self.assertEqual((w.asked, called("omgr_loadPreset"), w.toasts), ([], [], []))

    def test_a_path_that_is_not_text_is_not_loaded(self):
        for path in (5, ["a.rps"], {"a": 1}, "   "):
            self.setUp()
            s = setup(1)
            s["render_preset"].update(enabled=True, path=path)
            w = Window(stored([s]), answer=True)
            quiet(w.activate, 1)
            self.assertEqual(called("omgr_loadPreset"), [], repr(path))

    # ---- a preset of your own
    def test_a_preset_chosen_in_the_card_is_yours(self):
        w = Window(stored([setup(1)]))
        s = w.setups[0]
        s["render_preset"]["enabled"] = True
        card = Holder(setup=lambda: s, fill=lambda s: None, sm=w)
        window.cards2.RenderPresetCard._set(card, "D:\\project\\presets\\final.rps")  # typed, browsed or saved
        self.assertEqual(s["render_preset"]["path"], self.PRESET)
        quiet(w.activate, 1)
        self.assertEqual(w.asked, [])
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])

    def test_clearing_the_card_trusts_nothing(self):
        w = Window(self.file())
        card = Holder(setup=lambda: w.setups[0], fill=lambda s: None, sm=w)
        window.cards2.RenderPresetCard._set(card, "")
        self.assertEqual(w.settings.get("trusted_scripts", []), [])

    def test_a_preset_trusted_here_is_not_asked_about_in_another_file(self):
        mine = model.script_key("preset", "d:\\PROJECT\\presets\\final.rps")  # the same file, written another way
        w = Window(self.file(), settings={"trusted_scripts": [mine]})
        quiet(w.activate, 1)
        self.assertEqual(w.asked, [])
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])

    # ---- Batch Render, Bake Setups, Viewport Preview
    def test_batch_render(self):
        w = Window(self.file(), answer=False)
        report = batch_render(w)
        self.assertEqual(w.asked, [[self.ROW]])
        self.assertEqual(called("omgr_loadPreset"), [])
        self.assertIn("Render preset not loaded: it came with the file and isn't trusted", report[0][2])
        self.setUp()
        w = Window(self.file(), answer=True)
        report = batch_render(w)
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])
        self.assertFalse([line for line in report[0][2] if "preset" in line.lower()])

    def test_bake_setups_and_viewport_preview(self):
        for go in (lambda w: bake(w, 0, [1]), lambda w: bake(w, 3, [1], "print mine"), viewport_preview):
            for answer in (False, True):
                self.setUp()
                w = Window(self.file(), answer=answer)
                go(w)
                self.assertEqual(w.asked, [[self.ROW]])
                self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)] if answer else [])

    def test_never_and_always_hold_for_a_batch_too(self):
        for policy, loaded in (("never", []), ("always", [(self.PRESET,)])):
            for go in (batch_render, lambda w: bake(w, 0, [1])):
                self.setUp()
                w = Window(self.file(), settings={"max": {"scripts": policy}}, answer=True)
                go(w)
                self.assertEqual(w.asked, [])
                self.assertEqual(called("omgr_loadPreset"), loaded)

    # ---- what the dialog says
    def test_the_dialog_for_scripts_alone_reads_as_before(self):
        title, message, listed, yes, no = window.dialogs.review_text(
            [("#1 Cam", "Pre-Setup script", "code", "print 1\n"), ("#1 Cam", "Pre-Render file", "file", "D:/s/pre.ms")]
        )
        self.assertEqual(title, "Scripts in this file")
        self.assertEqual(
            message,
            "These setups run MAXScript that came with the file. A script can do anything 3ds Max can, like "
            "deleting files, so only run scripts you trust. OpenManager remembers your answer for these scripts; "
            "if one changes, it asks again.",
        )
        self.assertEqual(
            listed, '-- #1 Cam · Pre-Setup script\nprint 1\n\n-- #1 Cam · Pre-Render file\nfileIn @"D:/s/pre.ms"'
        )
        self.assertEqual((yes, no), ("Run these scripts", "Don't run them"))

    def test_the_dialog_for_a_preset(self):
        title, message, listed, yes, no = window.dialogs.review_text([self.ROW])
        self.assertEqual(title, "Render presets in this file")
        self.assertEqual(
            message,
            "These setups load a render preset that came with the file. A preset replaces the render settings "
            "of the scene with the ones in its file, so only load presets you trust. OpenManager leaves the "
            "scripts of Render Setup as they are. OpenManager remembers your answer for these render presets; "
            "if one changes, it asks again.",
        )
        self.assertEqual(listed, '-- #1 Cam · Render preset\nrenderPresets.LoadAll 0 @"D:/project/presets/final.rps"')
        self.assertEqual((yes, no), ("Load these presets", "Don't load them"))

    def test_the_dialog_for_both(self):
        title, message, listed, yes, no = window.dialogs.review_text(
            [("#1 Cam", "Pre-Setup script", "code", "print 1"), self.ROW]
        )
        self.assertEqual(title, "Scripts and render presets in this file")
        self.assertIn("so only run scripts you trust. They also load a render preset that came with the file.", message)
        self.assertIn(
            "so only load presets you trust. OpenManager leaves the scripts of Render Setup as they are. "
            "OpenManager remembers",
            message,
        )
        self.assertTrue(
            message.endswith(
                "OpenManager remembers your answer for these scripts and render presets; if one changes, it asks again."
            )
        )
        self.assertEqual(
            listed,
            "-- #1 Cam · Pre-Setup script\nprint 1\n\n-- #1 Cam · Render preset\n"
            'renderPresets.LoadAll 0 @"D:/project/presets/final.rps"',
        )
        self.assertEqual((yes, no), ("Run and load them", "Don't run or load them"))


class RenderSetupScriptsOfAPreset(Base):
    """A render preset also keeps the scripts of Render Setup (Scripts rollout: a script file run before each render,
    one run after it, and their switches), so a preset the person agreed to could still set a script that runs at
    the next render. Loading a preset leaves them as they were (maxlink.load_preset)."""

    PRESET = "D:/project/presets/final.rps"
    BROUGHT = [True, "//server/share/before.ms", True, "//server/share/after.ms"]
    FILE = "D:/s/pre.ms"

    def preset_brings_scripts(self, fails=False):
        """What 3ds Max does with this preset: the four script settings of Render Setup become the ones it keeps."""

        def load(path):
            rt.render_setup_scripts = list(self.BROUGHT)
            if fails:
                raise RuntimeError("the preset could not be read")
            return True

        rt.returns["omgr_loadPreset"] = load

    def file(self, **more):
        """A window on a file whose setup loads the preset, already trusted on this computer."""
        trusted = [model.script_key("preset", self.PRESET)] + [model.script_key(k, t) for k, t in more.pop("trust", [])]
        return Window(stored([setup(1, preset=self.PRESET, **more)]), settings={"trusted_scripts": trusted})

    # ---- the one place where a preset is loaded
    def test_they_are_read_before_the_load_and_put_back_after_it(self):
        self.preset_brings_scripts()
        self.assertTrue(maxlink.load_preset(self.PRESET))
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])
        self.assertEqual(
            rt.calls,
            [
                ("omgr_renderSetupScripts",),
                ("omgr_loadPreset", self.PRESET),
                ("omgr_setRenderSetupScripts", False, "", False, ""),
                ("omgr_renderSetupScripts",),
            ],
        )

    def test_scripts_the_person_has_in_render_setup_stay(self):
        mine = [True, "D:/mine/before.ms", False, "D:/mine/after.ms"]
        rt.render_setup_scripts = list(mine)
        self.preset_brings_scripts()
        maxlink.load_preset(self.PRESET)
        self.assertEqual(rt.render_setup_scripts, mine)

    def test_a_load_that_fails_puts_them_back_too(self):
        self.preset_brings_scripts(fails=True)
        with self.assertRaises(RuntimeError):
            maxlink.load_preset(self.PRESET)
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])

    def test_a_preset_that_is_not_loaded_changes_nothing(self):
        rt.render_setup_scripts = [True, "D:/mine/before.ms", False, ""]
        self.assertFalse(
            maxlink.load_preset("D:/no/such.rps")
        )  # omgr_loadPreset gives false for a file that is not there
        self.assertEqual(rt.render_setup_scripts, [True, "D:/mine/before.ms", False, ""])

    def test_no_preset_is_loaded_when_they_can_not_be_read(self):
        self.preset_brings_scripts()

        def broken(self):
            raise RuntimeError("no such global")

        with mock.patch.object(type(rt), "omgr_renderSetupScripts", broken), self.assertRaises(RuntimeError):
            maxlink.load_preset(self.PRESET)
        self.assertEqual(called("omgr_loadPreset"), [])
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])

    def test_it_says_so_when_3ds_max_does_not_take_them_back(self):
        self.preset_brings_scripts()
        with mock.patch.object(type(rt), "omgr_setRenderSetupScripts", lambda self, values: True):
            listener = quiet(maxlink.load_preset, self.PRESET)
        self.assertIn(
            "OpenManager: the scripts of Render Setup could not be put back after loading %s" % self.PRESET, listener
        )
        self.assertNotIn("could not be put back", quiet(maxlink.load_preset, self.PRESET))

    def test_the_same_path_written_another_way_is_no_change(self):
        rt.render_setup_scripts = [True, "d:\\MINE\\before.ms", False, ""]

        def load(path):
            rt.render_setup_scripts = [
                True,
                "D:/mine/before.ms",
                False,
                "",
            ]  # the same file, as 3ds Max may give it back
            return True

        rt.returns["omgr_loadPreset"] = load
        with mock.patch.object(type(rt), "omgr_setRenderSetupScripts", lambda self, values: True):
            self.assertNotIn("could not be put back", quiet(maxlink.load_preset, self.PRESET))

    # ---- every way a setup is applied
    def test_a_click_on_a_setup(self):
        self.preset_brings_scripts()
        w = self.file()
        quiet(w.activate, 1)
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])
        self.assertEqual(w.toasts, [])

    def test_a_click_when_the_load_fails(self):
        self.preset_brings_scripts(fails=True)
        w = self.file()
        listener = quiet(w.activate, 1)
        self.assertIn("-> the preset could not be read", listener)
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])

    def test_batch_render_bake_setups_and_viewport_preview(self):
        for go in (batch_render, lambda w: bake(w, 0, [1]), lambda w: bake(w, 3, [1], "print mine"), viewport_preview):
            self.setUp()
            rt.render_setup_scripts = [False, "D:/mine/before.ms", True, "D:/mine/after.ms"]
            self.preset_brings_scripts()
            go(self.file())
            self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])
            self.assertEqual(rt.render_setup_scripts, [False, "D:/mine/before.ms", True, "D:/mine/after.ms"])

    def test_a_preset_chosen_in_the_card(self):
        self.preset_brings_scripts()
        w = Window(stored([setup(1)]))
        s = w.setups[0]
        s["render_preset"]["enabled"] = True
        window.cards2.RenderPresetCard._set(Holder(setup=lambda: s, fill=lambda s: None, sm=w), self.PRESET)
        quiet(w.activate, 1)
        self.assertEqual(called("omgr_loadPreset"), [(self.PRESET,)])
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])

    # ---- the scripts of the setup itself are another thing, and still apply
    def test_the_scripts_of_the_setup_still_apply(self):
        self.preset_brings_scripts()
        w = self.file(
            pre_setup="print 1",
            pre_render="print 3",
            post_render="print 4",
            pre_file=self.FILE,
            trust=[("code", "print 1"), ("code", "print 3"), ("code", "print 4"), ("file", self.FILE)],
        )
        quiet(w.activate, 1)
        order = [
            c
            for c in rt.calls
            if c[0] in ("omgr_runCode", "omgr_loadPreset", "omgr_setRenderSetupScripts", "omgr_setRenderScripts")
        ]
        self.assertEqual(
            order,
            [
                ("omgr_runCode", "print 1"),
                ("omgr_loadPreset", self.PRESET),
                ("omgr_setRenderSetupScripts", False, "", False, ""),
                ("omgr_setRenderScripts", self.FILE, "", "print 3", "print 4"),
            ],
        )
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])
        self.assertEqual(w.toasts, [])

    def test_and_in_a_batch(self):
        self.preset_brings_scripts()
        w = self.file(pre_render="print 3", trust=[("code", "print 3")])
        batch_render(w)
        self.assertEqual(called("omgr_setRenderScripts"), [("", "", "print 3", "")])
        self.assertEqual(rt.render_setup_scripts, [False, "", False, ""])


class OpenFolders(Base):
    """The settings, the HDRI previews and what a scene not saved yet makes are in the Open3D folders (folders.py),
    one set for every 3ds Max, not in its plugcfg folder."""

    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.settings = os.path.join(folder.name, "Roaming", "Open3D", "OpenManager")
        self.data = os.path.join(folder.name, "Local", "Open3D", "OpenManager")
        environ = {
            "OPEN3D_SETTINGS_DIR": os.path.dirname(self.settings),
            "OPEN3D_DATA_DIR": os.path.dirname(self.data),
            folders.TEST_OLD_FOLDERS: os.path.join(folder.name, "3dsMax"),
        }
        patcher = mock.patch.dict(os.environ, environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        folders._session = None
        self.addCleanup(setattr, folders, "_session", None)

    def test_where_each_file_goes(self):
        self.assertEqual(window.settings_path(), os.path.join(self.settings, "OpenManager.json"))
        self.assertEqual(window.default_settings_path(), os.path.join(self.settings, "OpenManager_default.json"))
        self.assertEqual(window.notify_flag_path(), os.path.join(self.settings, "OpenManager_notify.txt"))
        self.assertEqual(cards.HdriCard.cache_dir(), os.path.join(self.data, "OpenManager_hdri"))
        w = opened(stored([setup(1)]))
        thumbs = os.path.join(self.data, "OpenManager_thumbs").replace("\\", "/")
        self.assertEqual(w.thumb_path(w.setups[0]), thumbs + "/scene_001.png")
        w.scene.folder = "D:/work"
        self.assertEqual(w.thumb_path(w.setups[0]), "D:/work/OpenManager_thumbs/scene_001.png")

    def test_saving_makes_the_settings_folder(self):
        w = opened("", settings={"notify": False, "theme": {"main": "dark"}})
        quiet(window.SceneManager.save_settings, w)
        with open(window.settings_path(), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["theme"], {"main": "dark"})
        with open(window.notify_flag_path(), encoding="utf-8") as f:
            self.assertEqual(f.read(), "0")

    def test_a_copy_that_failed_is_told(self):
        w = opened("")
        w.folders = folders.Folders(
            "old", "data", "hdri", (("old", "new", open3d_settings.CarryOver(open3d_settings.FAILED, reason="no")),)
        )
        window.SceneManager.tell_folders(w)
        self.assertEqual(w.toasts, [folders.trouble(w.folders)])
        w.toasts, w.folders = [], folders.Folders("new", "data", "hdri")
        window.SceneManager.tell_folders(w)
        self.assertEqual(w.toasts, [])


# ---------------------------------------------------------------- what the window catches and what it lets through


class Unexpected(Exception):
    """An error nobody expects: it must reach the caller, not be swallowed."""


def fails(ex):
    def fn(*args, **kwargs):
        raise ex

    return fn


MAX_ERROR = 'MAXScript exception raised.\n-- Unknown property: "x" in undefined'  # what pymxs gives
DELETED = "Internal C++ object (SceneManager) already deleted."  # what Qt gives for a part it deleted


class SettingsFiles(Base):
    """load_settings, save_settings, export_setups and import_output_preset: files, and JSON in them."""

    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = folder.name
        self.paths = {
            "settings_path": os.path.join(folder.name, "OpenManager.json"),
            "default_settings_path": os.path.join(folder.name, "OpenManager_default.json"),
            "notify_flag_path": os.path.join(folder.name, "OpenManager_notify.txt"),
        }
        for name, path in self.paths.items():
            patcher = mock.patch.object(window, name, lambda path=path: path)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(window, "cfg_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, text):
        with open(self.paths[name], "w", encoding="utf-8") as f:
            f.write(text)

    def test_settings_that_can_not_be_read(self):
        w = opened("")
        self.assertEqual(window.SceneManager.load_settings(w), {})  # neither file is there
        self.write("default_settings_path", '{"notify": false}')
        self.assertEqual(window.SceneManager.load_settings(w), {"notify": False})
        self.write("settings_path", "{not json")
        self.assertEqual(window.SceneManager.load_settings(w), {"notify": False})
        with open(self.paths["default_settings_path"], "wb") as f:
            f.write(b"\xff\xfe")  # not UTF-8 either
        self.assertEqual(window.SceneManager.load_settings(w), {})

    def test_an_unexpected_error_while_reading_the_settings(self):
        self.write("settings_path", "{}")
        w = opened("")
        with mock.patch.object(window.json, "load", fails(Unexpected())), self.assertRaises(Unexpected):
            window.SceneManager.load_settings(w)

    def test_settings_are_saved_when_qt_has_deleted_part_of_the_window(self):
        w = opened("", settings={"notify": False})
        w.isFloating = fails(RuntimeError(DELETED))
        quiet(window.SceneManager.save_settings, w)
        with open(self.paths["settings_path"], encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"notify": False})

    def test_where_the_window_is_goes_into_the_settings(self):
        w = opened("")
        quiet(window.SceneManager.save_settings, w)
        with open(self.paths["settings_path"], encoding="utf-8") as f:
            self.assertEqual(json.load(f)["geometry"], [10, 20, 900, 1000])

    def test_settings_that_can_not_be_written_are_told(self):
        w = opened("")
        os.makedirs(self.paths["settings_path"])  # a folder where the file goes
        listener = quiet(window.SceneManager.save_settings, w)
        self.assertIn("OpenManager: could not save settings: ", listener)

    def test_an_unexpected_error_while_saving_the_settings(self):
        w = opened("")
        w.isFloating = fails(Unexpected())
        with self.assertRaises(Unexpected):
            quiet(window.SceneManager.save_settings, w)
        w = opened("")
        with mock.patch.object(window.json, "dump", fails(Unexpected())), self.assertRaises(Unexpected):
            quiet(window.SceneManager.save_settings, w)

    def save_dialog(self, path):
        return mock.patch.object(window.QtWidgets.QFileDialog, "getSaveFileName", lambda *a, **k: (path, ""))

    def open_dialog(self, path):
        return mock.patch.object(window.QtWidgets.QFileDialog, "getOpenFileName", lambda *a, **k: (path, ""))

    def test_a_preset_that_can_not_be_written_is_told(self):
        w = opened(stored([setup(1)]))
        with self.save_dialog(self.folder):  # a folder: it can't be written as a file
            window.SceneManager.export_setups(w)
        self.assertEqual(len(w.toasts), 1)
        self.assertTrue(w.toasts[0].startswith("Could not save the preset: "), w.toasts)
        path = os.path.join(self.folder, "setups.smp")
        with self.save_dialog(path):
            window.SceneManager.export_setups(w)
        self.assertEqual(w.toasts[-1], "Exported 1 setup(s)")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["setups"]), 1)

    def test_an_unexpected_error_while_writing_a_preset(self):
        w = opened(stored([setup(1)]))
        with self.save_dialog(os.path.join(self.folder, "setups.smp")):
            with mock.patch.object(window.json, "dump", fails(Unexpected())), self.assertRaises(Unexpected):
                window.SceneManager.export_setups(w)

    def output_preset(self, text):
        path = os.path.join(self.folder, "output.smp")
        if text is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        w = opened(stored([setup(1)]))
        w.active_id = 1
        before = json.dumps(w.setups[0]["output"], sort_keys=True)
        with self.open_dialog(path):
            window.SceneManager.import_output_preset(w)
        return w, before

    def test_an_output_preset_that_is_not_one(self):
        for text in (
            None,
            "{not json",
            "[]",
            '{"output": 5}',
            '{"output": {"preset": 5}}',
            '{"output": {"preset": [1]}}',
        ):
            w, before = self.output_preset(text)
            self.assertEqual(w.toasts, ["Invalid preset"], text)
            self.assertEqual(json.dumps(w.setups[0]["output"], sort_keys=True), before, text)

    def test_an_output_preset(self):
        token = {"kind": "text", "value": "day"}
        w, _ = self.output_preset(json.dumps({"output": {"enabled": True, "preset": [token]}}))
        self.assertEqual(w.toasts, [])
        self.assertEqual(w.setups[0]["output"], {"enabled": True, "preset": [token]})

    def test_an_unexpected_error_while_reading_an_output_preset(self):
        with mock.patch.object(window.json, "load", fails(Unexpected())), self.assertRaises(Unexpected):
            self.output_preset('{"output": {}}')


class SceneReads(Base):
    """reload_all, reload_scene and sync_scene: the scene as omgr_scene gives it, in JSON."""

    def test_a_scene_that_can_not_be_read_leaves_the_one_read_before(self):
        w = opened(stored([setup(1)]))
        scene = w.scene
        for value in (fails(RuntimeError(MAX_ERROR)), lambda **kw: "{not json"):
            rt.returns["omgr_scene"] = value
            for read in (w.reload_all, lambda: window.SceneManager.reload_scene(w)):
                listener = quiet(read)
                self.assertIs(w.scene, scene)
                self.assertIn("Traceback", listener)
        w.scene_timer = Timer()
        rt.returns["omgr_scene"] = fails(RuntimeError(MAX_ERROR))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(window.SceneManager.sync_scene(w, True))
        self.assertIs(w.scene, scene)

    def test_an_unexpected_error_while_reading_the_scene(self):
        w = opened(stored([setup(1)]))
        w.scene_timer = Timer()
        rt.returns["omgr_scene"] = fails(Unexpected())
        for read in (w.reload_all, lambda: window.SceneManager.reload_scene(w)):
            with self.assertRaises(Unexpected):
                quiet(read)
        with self.assertRaises(Unexpected):
            window.SceneManager.sync_scene(w, True)


class SavingSetups(Base):
    """save_setups: what the autosave and the save before the file run."""

    def setUp(self):
        super().setUp()
        rt.returns["omgr_stampNodes"] = lambda hs: ["uid-%d" % h for h in hs]
        rt.returns["omgr_stampLayers"] = lambda names: ["" for _ in names]

    def save(self, w):
        return quiet(window.SceneManager.save_setups, w)

    def test_a_save_maxscript_refuses_is_told_and_tried_again(self):
        w = opened(stored([setup(1)]))
        w.stamp_uids = lambda: window.SceneManager.stamp_uids(w)
        w.setups[0]["notes"] = "changed"
        rt.returns["omgr_saveSetups"] = fails(RuntimeError(MAX_ERROR))
        self.assertIn("Traceback", self.save(w))
        rt.returns["omgr_saveSetups"] = None
        self.save(w)
        self.assertEqual(w.last_saved, w.encoded())
        self.assertIn('"notes":"changed"', called("omgr_saveSetups")[-1][0])

    def test_the_setups_are_saved_even_when_their_nodes_can_not_get_an_id(self):
        # the boundary of the autosave: whatever giving IDs raises, the setups are saved
        w = opened(stored([setup(1)]))
        w.stamp_uids = fails(Unexpected("no IDs"))
        w.setups[0]["notes"] = "changed"
        listener = self.save(w)
        self.assertIn("no IDs", listener)
        self.assertEqual(w.last_saved, w.encoded())

    def test_an_unexpected_error_while_saving(self):
        w = opened(stored([setup(1)]))
        w.stamp_uids = lambda: None
        w.setups[0]["notes"] = "changed"
        rt.returns["omgr_saveSetups"] = fails(Unexpected())
        with self.assertRaises(Unexpected):
            self.save(w)


class EndOfABatch(Base):
    """_cancel_render and _end_render: stopping a batch and closing its progress window."""

    def batch(self, close):
        w = opened("")
        w.batch = Holder(close=close, deleteLater=lambda: None)
        w.render_results, w.render_order, w.render_cancel = {}, [], False
        return w

    def test_a_stop_maxscript_refuses(self):
        w = opened("")
        rt.returns["omgr_stop"] = fails(RuntimeError(MAX_ERROR))
        window.SceneManager._cancel_render(w)
        self.assertTrue(w.render_cancel)
        rt.returns["omgr_stop"] = fails(Unexpected())
        with self.assertRaises(Unexpected):
            window.SceneManager._cancel_render(w)

    def test_a_progress_window_qt_has_deleted(self):
        w = self.batch(fails(RuntimeError(DELETED)))
        quiet(window.SceneManager._end_render, w)
        self.assertFalse(w.rendering)
        self.assertEqual(w.toasts, ["Batch Render finished: 0 saved, 0 failed, 0 skipped"])
        w = self.batch(fails(Unexpected()))
        with self.assertRaises(Unexpected):
            quiet(window.SceneManager._end_render, w)


class HdriPreviews(Base):
    """HdriCard._make_next: a preview of an HDRI made by 3ds Max."""

    def card(self):
        made = []
        card = Holder(
            sm=Holder(rendering=False),
            _missing=[("item", "c:/hdri/sky.hdr")],
            _auto=False,
            AUTO_MB=cards.HdriCard.AUTO_MB,
            _size_mb=lambda raw: 1.0,
            cache_file=lambda raw: ("c:/cache/sky.jpg", 1),
            _set_picture=lambda it, path: made.append(path),
            _update_make=lambda: None,
            _stop_making=lambda: None,
        )
        return card, made

    def test_a_preview_that_can_not_be_made_is_told(self):
        for ex in (RuntimeError(MAX_ERROR), OSError("no folder")):
            card, made = self.card()
            with mock.patch.object(maxlink, "hdri_preview", fails(ex)):
                listener = quiet(cards.HdriCard._make_next, card)
            self.assertIn("OpenManager: preview of c:/hdri/sky.hdr -> ", listener)
            self.assertEqual((made, card._missing), ([], []))
        card, made = self.card()
        with mock.patch.object(maxlink, "hdri_preview", lambda raw, dst: True):
            cards.HdriCard._make_next(card)
        self.assertEqual(made, ["c:/cache/sky.jpg"])

    def test_an_unexpected_error_while_making_one(self):
        card, _ = self.card()
        with mock.patch.object(maxlink, "hdri_preview", fails(Unexpected())), self.assertRaises(Unexpected):
            cards.HdriCard._make_next(card)


if __name__ == "__main__":
    unittest.main()
