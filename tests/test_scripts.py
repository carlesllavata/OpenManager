"""Scripts that come with a file only run once trusted (model.py, no 3ds Max)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "package", "OpenManager"))
from openmanager import model  # noqa: E402


def setup_with_scripts():
    s = model.empty_setup(1)
    s["snippet"].update(enabled=True, pre_setup="print 1", post_setup="  ", pre_render="", post_render="print 4")
    s["scripts"].update(enabled=True, pre_render={"enabled": True, "path": "D:/s/pre.ms"},
                        post_render={"enabled": False, "path": "D:/s/post.ms"})
    return s


class CodePieces(unittest.TestCase):
    def test_only_enabled_and_not_empty(self):
        got = [(p["slot"], p["kind"], p["text"]) for p in model.code_pieces(setup_with_scripts())]
        self.assertEqual(got, [("Pre-Setup script", "code", "print 1"), ("Post-Render script", "code", "print 4"),
                               ("Pre-Render file", "file", "D:/s/pre.ms")])

    def test_cards_off(self):
        s = setup_with_scripts()
        s["snippet"]["enabled"] = False
        s["scripts"]["enabled"] = False
        self.assertEqual(model.code_pieces(s), [])


class ScriptKey(unittest.TestCase):
    def test_changed_code_is_a_new_script(self):
        self.assertNotEqual(model.script_key("code", "print 1"), model.script_key("code", "print 2"))
        self.assertEqual(model.script_key("code", "print 1"), model.script_key("code", "print 1"))

    def test_files_by_path(self):
        self.assertEqual(model.script_key("file", "D:/s/pre.ms"), model.script_key("file", "D:\\s\\pre.ms "))


class FilterScripts(unittest.TestCase):
    acts = [("res", 1, 1), ("code", "print 1"), ("renderscripts", "D:/s/pre.ms", "", "print 3", "print 4"),
            ("code", "print 2")]

    def test_nothing_trusted(self):
        acts, refused = model.filter_scripts(self.acts, lambda kind, text: False)
        self.assertEqual(acts, [("res", 1, 1), ("renderscripts", "", "", "", "")])
        self.assertEqual(refused, ["print 1", "D:/s/pre.ms", "print 3", "print 4", "print 2"])

    def test_some_trusted(self):
        ok = {"print 2", "print 4"}
        acts, refused = model.filter_scripts(self.acts, lambda kind, text: text in ok)
        self.assertEqual(acts, [("res", 1, 1), ("renderscripts", "", "", "", "print 4"), ("code", "print 2")])
        self.assertEqual(refused, ["print 1", "D:/s/pre.ms", "print 3"])

    def test_all_trusted(self):
        self.assertEqual(model.filter_scripts(self.acts, lambda kind, text: True), (list(self.acts), []))


if __name__ == "__main__":
    unittest.main()
