"""Base state: what a setup changed is put back when the next one doesn't control it (model.py, no 3ds Max)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "package", "OpenManager"))
from openmanager import model  # noqa: E402


class FakeScene(object):
    """Values a capture reads, keyed like model.action_key."""

    def __init__(self, **values):
        self.values = dict(values)
        self.reads = []

    def capture(self, a):
        k = model.action_key(a)
        self.reads.append(k)
        if k == ("res",):
            return ("res",) + self.values["res"]
        if k[0] == "rs":
            return ("rs", a[1], self.values[a[1]]) if a[1] in self.values else None
        if k[0] == "layer":
            return ("layer", a[1], a[2], self.values.get(a[1], True))
        return None


class ActionKey(unittest.TestCase):
    def test_same_thing_same_key(self):
        self.assertEqual(model.action_key(("rs", "gi", 1)), model.action_key(("rs", "gi", 5)))
        self.assertEqual(model.action_key(("env", "CoronaSky", "Sky", -1)), model.action_key(("envoff",)))
        self.assertEqual(model.action_key(("node", 12, "fov", 45.0)), ("node", 12, "fov"))
        self.assertEqual(model.action_key(("map", "CoronaBitmap", "hdr", "uAngle", 90.0)), ("map", "CoronaBitmap", "hdr", "uAngle"))

    def test_views_and_scripts_are_not_put_back(self):
        for a in (("camera", 1, False, 0), ("background", 1, ""), ("code", "x"), ("preset", "a.rps"),
                  ("renderscripts", "", "", "", ""), ("mkdir", "D:/a.png"), ("renderview",)):
            self.assertIsNone(model.action_key(a), a)


class BaseStep(unittest.TestCase):
    def test_first_setup_keeps_what_it_replaces(self):
        scene = FakeScene(res=(1920, 1080), gi=1)
        restore, base = model.base_step({}, [("res", 800, 600), ("rs", "gi", 2)], scene.capture)
        self.assertEqual(restore, [])
        self.assertEqual(base, {("res",): ("res", 1920, 1080), ("rs", "gi"): ("rs", "gi", 1)})

    def test_next_setup_puts_back_what_it_does_not_control(self):
        scene = FakeScene(res=(1920, 1080), gi=1)
        _, base = model.base_step({}, [("res", 800, 600), ("rs", "gi", 2)], scene.capture)
        restore, base = model.base_step(base, [("res", 640, 480)], scene.capture)
        self.assertEqual(restore, [("rs", "gi", 1)])
        # the resolution keeps its original value, not the one of the first setup
        self.assertEqual(base, {("res",): ("res", 1920, 1080)})

    def test_controlled_again_is_not_read_again(self):
        scene = FakeScene(res=(1920, 1080))
        _, base = model.base_step({}, [("res", 800, 600)], scene.capture)
        model.base_step(base, [("res", 640, 480)], scene.capture)
        self.assertEqual(scene.reads, [("res",)])

    def test_something_nobody_controls_is_read_fresh(self):
        # a change made by hand while no setup controlled it becomes the new base
        scene = FakeScene(res=(1920, 1080))
        _, base = model.base_step({}, [("res", 800, 600)], scene.capture)
        _, base = model.base_step(base, [], scene.capture)
        scene.values["res"] = (1000, 1000)
        _, base = model.base_step(base, [("res", 640, 480)], scene.capture)
        self.assertEqual(base[("res",)], ("res", 1000, 1000))

    def test_unreadable_value_is_not_put_back(self):
        scene = FakeScene()
        restore, base = model.base_step({}, [("rs", "unknown", 3)], scene.capture)
        self.assertEqual(base, {})
        restore, base = model.base_step(base, [], scene.capture)
        self.assertEqual(restore, [])

    def test_empty_setup_puts_back_everything(self):
        scene = FakeScene(res=(1920, 1080), LY_B=True)
        _, base = model.base_step({}, [("res", 800, 600), ("layer", "LY_B", "on", False)], scene.capture)
        restore, base = model.base_step(base, [], scene.capture)
        self.assertEqual(restore, [("res", 1920, 1080), ("layer", "LY_B", "on", True)])
        self.assertEqual(base, {})


class Undo(unittest.TestCase):
    def test_restore_changes_have_the_key_of_what_they_undo(self):
        self.assertEqual(model.action_key(("timeraw", 0, 100, 0, 1, 0, 100, 1, "")), ("time",))
        self.assertEqual(model.action_key(("lightson", "dome", ((1, True),))), ("dome",))
        self.assertEqual(model.action_key(("envraw", "", "", True)), ("env",))
        self.assertEqual(model.action_key(("outputraw", False, "", ())), ("output",))

    def test_camera_is_undone_but_not_part_of_the_base(self):
        self.assertIsNone(model.action_key(("camera", 5, False, 0)))
        self.assertEqual(model.undo_key(("camera", 5, False, 0)), ("camera",))

    def test_first_value_wins(self):
        scene = FakeScene(res=(1920, 1080))
        rec = model.undo_capture({}, [("res", 800, 600)], scene.capture)
        scene.values["res"] = (800, 600)
        model.undo_capture(rec, [("res", 640, 480), ("rs", "gi", 2)], scene.capture)
        self.assertEqual(rec, {("res",): ("res", 1920, 1080)})  # gi can't be read in this fake scene
        self.assertEqual(scene.reads, [("res",), ("rs", "gi")])

    def test_things_that_cannot_be_undone_are_skipped(self):
        scene = FakeScene()
        self.assertEqual(model.undo_capture({}, [("code", "x"), ("preset", "a.rps")], scene.capture), {})
        self.assertEqual(scene.reads, [])


class Storage(unittest.TestCase):
    def test_round_trip_through_the_max_file_text(self):
        base = {("res",): ("res", 1920, 1080), ("node", 7, "fov"): ("node", 7, "fov", 45.0),
                ("sun",): ("lightson", ((3, True), (4, False))),
                ("rs", "bg"): ("rs", "bg", ("$color", "#ff0000"))}
        text = model.encode([model.empty_setup(1)], [], {"base": model.base_to_json(base)})
        self.assertEqual(model.decode(text)["base"], base)

    def test_files_without_a_base(self):
        self.assertEqual(model.decode(model.encode([], []))["base"], {})
        self.assertEqual(model.base_from_json([["bad"], 3, None]), {})


if __name__ == "__main__":
    unittest.main()
