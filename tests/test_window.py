# SPDX-License-Identifier: GPL-3.0-or-later
"""What the window lets through and tells when the setups of a file are applied (window.py on a fake 3ds Max).

The methods under test are the real ones of window.SceneManager, used by an object that has none of its widgets
(Window below): opening a file, clicking a setup, Batch Render, Bake Setups."""
import contextlib
import io
import json
import os
import sys
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
SCRIPT_TOAST = "%d script(s) of this setup were not run: they came with the file and aren't trusted"


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
            "begin_undo", "undo_capture", "end_undo", "clear_undo", "update_undo_buttons", "undo", "redo")

    def __init__(self, stored="", settings=None, answer=False):
        """stored: the text of rootNode.OpenManager_Dat; answer: what the person says when asked about scripts."""
        self.settings = settings or {}
        self.answer = answer
        self.toasts, self.asked = [], []
        self.toast_label = Holder(show_text=lambda text, ms=3500: self.toasts.append(text))
        self.save_timer = self.apply_timer = self.list_timer = Timer()
        self.scene, self.setups, self.todo, self.rs_default, self.base = maxlink.Scene(), [], [], {}, {}
        self.undo_stack, self.redo_stack, self._undo_rec = [], [], None
        self._typed, self._denied, self._refused = {}, set(), []
        self.active_id, self.next_id, self.last_sent, self.last_saved = None, 1, [], None
        self.rendering, self.loading, self.applying = False, False, 0
        rt.returns["omgr_readKey"] = lambda key: stored if key == maxlink.DATA_KEY else ""
        rt.returns["omgr_scene"] = lambda **kw: json.dumps(SCENE)
        self.reload_all()

    def ask_scripts(self, rows):
        self.asked.append(rows)
        return self.answer

    def nothing(self, *args, **kwargs):
        pass

    save_settings = save_setups = reload_scene = resolve_scene_refs = query_values = nothing
    layout_cards = rebuild_rows = refresh_rows = refresh_cards = update_status = nothing

    def resolve_all(self, setups=None, strict=False):
        return False


for _name in Window.REAL:
    setattr(Window, _name, getattr(window.SceneManager, _name))


def stored(setups, **extra):
    """The text a file keeps in rootNode.OpenManager_Dat."""
    return model.encode(setups, [], extra or None)


def setup(sid=1, ops=None, **scripts):
    """A setup that only sets what is asked: tone-mapping operators (Post-Production card) and scripts (pre_setup,
    post_setup, pre_render, post_render: Script Editor card; pre_file, post_file: Script File card)."""
    s = model.empty_setup(sid)
    s["resolution"]["enabled"] = False
    s["camera"].update(handle=7, name="Cam")
    if ops is not None:
        s["post"].update(enabled=True, cats={"tonemap": {"ops": ops}})
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


class Base(unittest.TestCase):
    def setUp(self):
        rt.reset()
        rt.add_node(7, "CoronaCam", "Cam")
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


if __name__ == "__main__":
    unittest.main()
