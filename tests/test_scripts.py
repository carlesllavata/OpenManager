# SPDX-License-Identifier: GPL-3.0-or-later
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


class RenderPreset(unittest.TestCase):
    """The render preset of a setup is asked about and trusted like a script file."""

    def test_it_is_one_of_the_pieces_shown(self):
        s = setup_with_scripts()
        s["render_preset"].update(enabled=True, path=" D:/p/final.rps ")
        self.assertEqual(model.code_pieces(s)[-1], {"slot": "Render preset", "kind": "preset", "text": "D:/p/final.rps"})
        self.assertEqual(len(model.code_pieces(s)), 4)

    def test_only_when_its_card_is_on_and_has_a_path(self):
        for card in ({"enabled": False, "path": "D:/p/final.rps"}, {"enabled": True, "path": ""}, {"enabled": True, "path": "  "},
                     {"enabled": True, "path": None}, {"enabled": True, "path": 5}, {"enabled": True}, None):
            s = model.empty_setup(1)
            s["render_preset"] = card
            self.assertEqual(model.code_pieces(s), [], card)

    def test_remembered_by_its_path(self):
        self.assertEqual(model.script_key("preset", "D:/p/final.rps"), model.script_key("preset", "D:\\p\\final.rps "))
        self.assertNotEqual(model.script_key("preset", "D:/p/final.rps"), model.script_key("preset", "D:/p/other.rps"))
        # a script file trusted under a path does not make a preset of the same path trusted
        self.assertNotEqual(model.script_key("preset", "D:/p/x"), model.script_key("file", "D:/p/x"))

    def test_left_out_of_the_changes_unless_allowed(self):
        acts = [("code", "print 1"), ("preset", "D:/p/final.rps"), ("res", 1, 1)]
        self.assertEqual(model.filter_presets(acts, lambda kind, text: False),
                         ([("code", "print 1"), ("res", 1, 1)], ["D:/p/final.rps"]))
        self.assertEqual(model.filter_presets(acts, lambda kind, text: (kind, text) == ("preset", "D:/p/final.rps")), (acts, []))
        self.assertEqual(model.filter_presets([("preset", 5), ("preset", ("a",))], lambda kind, text: True), ([], [5, ("a",)]))
        # the scripts are another question (filter_scripts)
        self.assertEqual(model.filter_scripts(acts, lambda kind, text: False), ([("preset", "D:/p/final.rps"), ("res", 1, 1)], ["print 1"]))


class StoredBase(unittest.TestCase):
    """The base state is stored in the file and applied without being shown: it can't carry a script."""
    hidden = [[["x"], ["code", 'messageBox "x"']],
              [["rs", "gi"], ["renderscripts", "D:/s/pre.ms", "", "print 3", ""]],
              [["output"], ["preset", "D:/s/a.rps"]],
              [["y"], ["mkdir", "D:/s/a.png"]],
              [["z"], ["post", "conf", "{}"]],
              [["w"], "code"]]
    kept = [[["res"], ["res", 1920, 1080]], [["rs", "gi"], ["rs", "gi", 1]],
            [["node", 7, "fov"], ["node", 7, "fov", 45.0]], [["env"], ["envraw", "CoronaSky", "Sky", True]]]

    def test_only_changes_that_put_a_value_back_are_read(self):
        dropped = []
        base = model.base_from_json(self.hidden[:3] + self.kept + self.hidden[3:], dropped)
        self.assertEqual(base, {("res",): ("res", 1920, 1080), ("rs", "gi"): ("rs", "gi", 1),
                                ("node", 7, "fov"): ("node", 7, "fov", 45.0), ("env",): ("envraw", "CoronaSky", "Sky", True)})
        self.assertEqual(len(dropped), len(self.hidden))

    def test_the_file_text_says_how_many_were_left_out(self):
        d = model.decode(model.encode([model.empty_setup(1)], [], {"base": self.hidden + self.kept}))
        self.assertEqual(d["base_dropped"], len(self.hidden))
        self.assertEqual(len(d["base"]), len(self.kept))
        self.assertEqual(model.decode(model.encode([], [], {"base": self.kept}))["base_dropped"], 0)

    def test_nothing_read_from_a_file_puts_a_script_back(self):
        base = model.decode(model.encode([], [], {"base": self.hidden + self.kept}))["base"]
        restore, _ = model.base_step(base, [], lambda a: None)
        self.assertEqual(len(restore), len(self.kept))
        self.assertEqual(model.filter_scripts(restore, lambda kind, text: False), (restore, []))

    def test_what_openmanager_stores_comes_back_whole(self):
        # every kind of change a base holds (maxlink.capture), through the text of the file
        base = {("rs", "gi"): ("rs", "gi", 1), ("node", 7, "fov"): ("node", 7, "fov", 45.0),
                ("layer", "L", "on"): ("layer", "L", "on", True), ("map", "CoronaBitmap", "hdr", "uAngle"): ("map", "CoronaBitmap", "hdr", "uAngle", 90.0),
                ("res",): ("res", 1920, 1080), ("time",): ("timeraw", 0, 100, 0, 1, 0, 100, 1, ""),
                ("sun",): ("lightson", "sun", ((3, True),)), ("dome",): ("lightson", "dome", ()),
                ("env",): ("envraw", "", "", True), ("output",): ("outputraw", False, "", ()),
                ("xref", "a.max"): ("xref", "a.max", True), ("atmos", "Fog"): ("atmos", "Fog", True),
                ("element", "Beauty"): ("element", "Beauty", True), ("posttone",): ("posttone", "[]"), ("postlm",): ("postlm", "{}")}
        d = model.decode(model.encode([], [], {"base": model.base_to_json(base)}))
        self.assertEqual(d["base"], base)
        self.assertEqual(d["base_dropped"], 0)


if __name__ == "__main__":
    unittest.main()
