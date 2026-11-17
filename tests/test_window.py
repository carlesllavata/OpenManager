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
from openmanager import maxlink, model  # noqa: E402

try:
    from openmanager import window
except ImportError as ex:  # PySide6 comes with the Python of 3ds Max
    raise unittest.SkipTest("the window needs PySide6 (%s)" % ex)

SCENE = {"file": "scene.max", "folder": "", "engine": "Corona", "cameras": [{"handle": 7, "name": "Cam", "class": "CoronaCam", "locked": False}]}
CLASS_TOAST = "%d class name(s) of this file were not used: they are not operator or map classes (see the MAXScript Listener)"
SETTING_TOAST = "%d setting(s) of this file were not applied: OpenManager's cards don't set them (see the MAXScript Listener)"
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
    REAL = ("reload_all", "encoded", "object_handles", "opts", "active", "index_of", "enabled_keys", "enabled_rows", "build_path",
            "final_path", "setup_label", "toast", "actions_for", "script_allowed", "trust_scripts", "typed_code", "review_scripts",
            "tell_refused", "tell_rejected", "run_actions", "_apply", "_apply_edit", "base_restore", "restore_scene", "activate",
            "begin_undo", "undo_capture", "end_undo", "clear_undo", "update_undo_buttons", "undo", "redo",
            "_run_over_setups", "viewport_preview", "bake_setups", "thumb_path", "start_render", "check_render", "_check_row",
            "_begin_render", "_job_label", "_next_job", "_cancel_render", "_end_render")

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
    with mock.patch.object(window, "QtCore", timers), mock.patch.object(window.dialogs, "BatchDialog", Dialog), \
            mock.patch.object(window.dialogs, "BatchCheckDialog", Dialog), mock.patch.object(window.dialogs, "BatchReportDialog", Dialog):
        quiet(w.start_render, chosen)
        while later:
            quiet(later.pop(0))
    return w.last_report


def bake(w, method, ids, code=""):
    with mock.patch.object(window.dialogs, "BakeDialog", bake_dialog(method, ids, code)), \
            mock.patch.object(window.dialogs, "BatchDialog", Dialog), mock.patch.object(window, "cfg_dir", tempfile.gettempdir):
        quiet(w.bake_setups)


def viewport_preview(w):
    with mock.patch.object(window.dialogs, "BatchDialog", Dialog), mock.patch.object(window, "cfg_dir", tempfile.gettempdir):
        quiet(w.viewport_preview)


class Base(unittest.TestCase):
    def setUp(self):
        rt.reset()
        rt.add_node(7, "CoronaCam", "Cam")
        rt.returns["omgr_render"] = "done"
        # the scene saves its renders, so a batch has nothing to stop for
        rt._globals.update(rendSaveFile=True, rendOutputFilename=os.path.join(tempfile.gettempdir(), "omgr_no_such_folder", "a.png"))
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
        self.assertIn('OpenManager: left out "Box(); messageBox "x"": it is not a tone-mapping operator class', listener)
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
    HIDDEN = [[["x"], ["code", 'messageBox "x"']],
              [["y"], ["renderscripts", "D:/s/pre.ms", "", "print 3", ""]],
              [["z"], ["preset", "D:/s/a.rps"]]]
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
        w = opened(stored([setup(1)], base=[[["node", 7, "controller.script"], ["node", 7, "controller.script", self.CODE]]]))
        listener = quiet(w.activate, 1)
        self.assertEqual(rt.executed, [])
        self.assertEqual(called("omgr_setNode"), [])
        self.assertEqual([c for c in rt.calls if c[0] in self.READS], [])
        self.assertEqual(w.toasts, [SETTING_TOAST % 1])
        self.assertIn('OpenManager: left out the object setting "controller.script": it holds code', listener)
        self.assertEqual(w.base, {})

    def test_nor_when_the_scene_is_put_back(self):
        w = opened(stored([setup(1)], base=[[["node", 7, "Proceed_Script"], ["node", 7, "Proceed_Script", self.CODE]],
                                            [["rs", "a.b.script"], ["rs", "a.b.script", self.CODE]],
                                            [["map", "Checker", "m", "coords.x"], ["map", "Checker", "m", "coords.x", 1]],
                                            [["layer", "0", "x.y"], ["layer", "0", "x.y", True]],
                                            [["res"], ["res", 800, 600]]]))
        quiet(w.restore_scene)
        self.assertEqual([c[0] for c in rt.calls if c[0].startswith("omgr_set")], ["omgr_setRes"])
        self.assertEqual(w.toasts[-1], SETTING_TOAST % 4)

    def test_a_setup_can_not_reach_other_objects_through_the_renderer(self):
        s = setup(1)
        s["rs_override"].update(enabled=True, set={"bg_texmap.coords.script": self.CODE, "a.b": 1, "gi_on": True})
        s["post"].update(enabled=True, cats={"bloom": {"props": {"x.controller.script": self.CODE, "bloomGlare_enabled": True}}})
        w = opened(stored([s], rs_default={"other.path": 1, "progressive_passLimit": 5}))
        quiet(w.activate, 1)
        self.assertEqual(sorted(called("omgr_setRS")), [("bloomGlare_enabled", True), ("gi_on", True), ("progressive_passLimit", 5)])
        self.assertEqual(sorted(set(c[1] for c in rt.calls if c[0] == "omgr_getRawRS")), ["bloomGlare_enabled", "gi_on", "progressive_passLimit"])
        self.assertEqual(w.toasts, [SETTING_TOAST % 4])

    def test_everything_left_out_is_told_in_one_message(self):
        s = setup(1, [{"class": "a;b", "props": {}}, {"class": "FilmicOperatorPlugin", "props": {"x.y": 1}}], pre_setup="print 1")
        w = opened(stored([s], base=[[["node", 7, "controller.script"], ["node", 7, "controller.script", self.CODE]]]))
        quiet(w.activate, 1)
        self.assertEqual(w.toasts, ["\n".join([SCRIPT_TOAST % 1, CLASS_TOAST % 1, SETTING_TOAST % 2])])

    def test_what_omgr_core_refused_is_told(self):
        w = opened(stored([setup(1)]))
        rt.bad_props = ["controller.script"]  # what omgr_propOk keeps
        quiet(w.activate, 1)
        self.assertEqual(w.toasts, [SETTING_TOAST % 1])

    def test_batch_render_says_it_in_its_report(self):
        w = opened(stored([setup(1)], base=[[["node", 7, "controller.script"], ["node", 7, "controller.script", self.CODE]]]))
        report = batch_render(w)
        self.assertEqual(called("omgr_setNode"), [])
        self.assertIn("1 setting(s) not applied: OpenManager's cards don't set them", report[0][2])

    # ---- what the cards make keeps working
    def test_render_settings_override_as_the_card_stores_it(self):
        s = setup(1)
        s["rs_override"].update(enabled=True, set={"gi_on": True, "lut_path": "D:/luts/a.cube", "progressive_passLimit": 20})
        w = opened(stored([s], rs_default={"gi_on": False, "progressive_passLimit": 5, "image_filter_width": 1.5}))
        listener = quiet(w.activate, 1)
        self.assertEqual(called("omgr_setRS"), [("image_filter_width", 1.5), ("gi_on", True), ("lut_path", "D:/luts/a.cube"),
                                                ("progressive_passLimit", 20)])
        self.assertEqual(w.toasts, [])
        self.assertNotIn("left out", listener)

    def test_post_production_as_the_card_stores_it(self):
        s = setup(1, [{"class": "FilmicOperatorPlugin", "props": {"colorMappingOperator_highlightCompression": 2.0,
                                                                   "colorMappingOperator_enabled": True}}])
        s["post"]["cats"].update({key: {"props": {n: True for n in names}} for key, _, names in model.POST_CATS})
        w = opened(stored([s]))
        quiet(w.activate, 1)
        self.assertEqual(sorted(c[0] for c in called("omgr_setRS")), sorted(n for _, _, names in model.POST_CATS for n in names))
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
        cam = next(p["name"] for t in model.tabs_for(1, "corona") if t["v_class"] == "CoronaCam" for p in t["props"] if p["class"] == "Float")
        rs = next(p["name"] for t in model.tabs_for(25, "corona") for p in t["props"] if p["class"] == "BooleanClass")
        pulze = [{"camera": {"enabled": True, "handle": 7, "props": [{"name": cam, "v_class": "CoronaCam", "value": "35.5"}]},
                  "renderCustom": {"enabled": "true", "props": [{"name": rs, "v_class": "CoronaRenderer", "value": "true"},
                                                                {"name": "a.b.script", "v_class": "CoronaRenderer", "value": self.CODE}]},
                  "objects": {"enabled": True, "set": [{"handle": 7, "name": "Cam", "props": [
                      {"name": "isNodeHidden", "value": "true"}, {"name": "renderable", "value": False}, {"name": "script", "value": True}]}]},
                  "layers": {"enabled": True, "set": [{"name": "0", "props": [{"name": "on", "value": False}, {"name": "script", "value": True}]}]}}]
        text = base64.b64encode(json.dumps(pulze).encode("utf-8")).decode("ascii")
        w = opened("", pulze=text, settings={"enabled_props": {"1": ["CoronaCam|" + cam], "25": ["CoronaRenderer|" + rs]}})
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
        return [setup(1, pre_setup="print 1", post_setup="print 2", pre_render="print 3", post_render="print 4", pre_file=self.FILE),
                setup(2, pre_setup="print 5")]

    def all_scripts(self):
        return [("#1 Cam", "Pre-Setup script", "code", "print 1"), ("#1 Cam", "Post-Setup script", "code", "print 2"),
                ("#1 Cam", "Pre-Render script", "code", "print 3"), ("#1 Cam", "Post-Render script", "code", "print 4"),
                ("#1 Cam", "Pre-Render file", "file", self.FILE), ("#2 Cam", "Pre-Setup script", "code", "print 5")]

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
        title, message, listed, yes, no = window.dialogs.review_text([("#1 Cam", "Pre-Setup script", "code", "print 1\n"),
                                                                      ("#1 Cam", "Pre-Render file", "file", "D:/s/pre.ms")])
        self.assertEqual(title, "Scripts in this file")
        self.assertEqual(message, "These setups run MAXScript that came with the file. A script can do anything 3ds Max can, like "
                                  "deleting files, so only run scripts you trust. OpenManager remembers your answer for these scripts; "
                                  "if one changes, it asks again.")
        self.assertEqual(listed, '-- #1 Cam · Pre-Setup script\nprint 1\n\n-- #1 Cam · Pre-Render file\nfileIn @"D:/s/pre.ms"')
        self.assertEqual((yes, no), ("Run these scripts", "Don't run them"))

    def test_the_dialog_for_a_preset(self):
        title, message, listed, yes, no = window.dialogs.review_text([self.ROW])
        self.assertEqual(title, "Render presets in this file")
        self.assertEqual(message, "These setups load a render preset that came with the file. A preset replaces the render settings "
                                  "of the scene with the ones in its file, so only load presets you trust. OpenManager remembers "
                                  "your answer for these render presets; if one changes, it asks again.")
        self.assertEqual(listed, '-- #1 Cam · Render preset\nrenderPresets.LoadAll 0 @"D:/project/presets/final.rps"')
        self.assertEqual((yes, no), ("Load these presets", "Don't load them"))

    def test_the_dialog_for_both(self):
        title, message, listed, yes, no = window.dialogs.review_text([("#1 Cam", "Pre-Setup script", "code", "print 1"), self.ROW])
        self.assertEqual(title, "Scripts and render presets in this file")
        self.assertIn("so only run scripts you trust. They also load a render preset that came with the file.", message)
        self.assertTrue(message.endswith("OpenManager remembers your answer for these scripts and render presets; if one changes, it asks again."))
        self.assertEqual(listed, '-- #1 Cam · Pre-Setup script\nprint 1\n\n-- #1 Cam · Render preset\nrenderPresets.LoadAll 0 @"D:/project/presets/final.rps"')
        self.assertEqual((yes, no), ("Run and load them", "Don't run or load them"))


if __name__ == "__main__":
    unittest.main()
