"""Output path building and the batch checks (model.py: no 3ds Max needed).

    "C:\\Program Files\\Autodesk\\3ds Max 2027\\Python\\python.exe" -I tests\\run.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "package", "OpenManager"))
from openmanager import model  # noqa: E402


def output(*tokens, project="D:/out"):
    toks = []
    for kind, value in tokens:
        t = model.new_token(kind)
        if value is not None:
            t["value"] = value
        toks.append(t)
    return {"enabled": True, "project_path": project, "preset": toks}


def build(out, camera="Cam01", scene_name="", file_name="house_v012.max"):
    return model.build_path(out, file_name, camera, scene_name, 0, "PC", "me")


class CleanName(unittest.TestCase):
    def test_invalid_characters_become_underscores(self):
        self.assertEqual(model.clean_name('CAM:Bad*1?"<>|'), "CAM_Bad_1_____")

    def test_slashes_are_not_folders_in_names(self):
        self.assertEqual(model.clean_name("Front/Back"), "Front_Back")

    def test_typed_tokens_keep_folders_and_trim_folder_ends(self):
        self.assertEqual(model.clean_name("renders. \\final", keep_folders=True), "renders/final")

    def test_control_characters(self):
        self.assertEqual(model.clean_name("a\tb\nc"), "a_b_c")

    def test_dot_inside_a_name_stays(self):
        self.assertEqual(model.clean_name("."), ".")


class BuildPath(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(build(output(("Camera", None), ("Extension", ".png"))), ("D:/out/Cam01.png", None))

    def test_camera_with_colon_is_cleaned(self):
        path, problem = build(output(("Camera", None), ("Extension", ".png")), camera="CAM:Bad")
        self.assertEqual((path, problem), ("D:/out/CAM_Bad.png", None))

    def test_scene_name_folder_with_trailing_dot(self):
        out = output(("SceneName", None), ("Camera", None), ("Extension", ".jpg"))
        out["preset"][0]["folder"] = True
        self.assertEqual(build(out, scene_name="Day v2."), ("D:/out/Day v2/Cam01.jpg", None))

    def test_no_project(self):
        self.assertEqual(build(output(("Camera", None), ("Extension", ".png"), project=""))[1], "No project path")

    def test_missing_camera_says_why(self):
        problem = build(output(("Camera", None), ("Extension", ".png")), camera=None)[1]
        self.assertIn("Camera token has no value", problem)
        self.assertIn("no camera", problem)

    def test_unsaved_scene(self):
        problem = build(output(("FileName (Full)", None), ("Extension", ".png")), file_name="")[1]
        self.assertIn("not saved", problem)

    def test_no_extension(self):
        self.assertEqual(build(output(("Camera", None)))[1], "No Extension token")

    def test_empty_file_name(self):
        out = output(("Text", "renders"), ("Extension", ".png"))
        out["preset"][0]["folder"] = True
        self.assertEqual(build(out)[1], "The file name is empty")

    def test_project_path_with_bad_characters(self):
        self.assertIn("project path", build(output(("Camera", None), ("Extension", ".png"), project="D:/a|b"))[1])

    def test_final_path_still_returns_valid_flag(self):
        self.assertEqual(model.final_path(output(("Camera", None), ("Extension", ".png")), "a.max", "C", "", 0, "", ""),
                         ("D:/out/C.png", True))


class CheckJobs(unittest.TestCase):
    def test_all_good(self):
        r = model.check_jobs([{"label": "A", "output": True, "path": "D:/a.png", "problem": None}])
        self.assertEqual(r, [{"path": "D:/a.png", "errors": [], "warnings": []}])

    def test_invalid_output_is_an_error(self):
        r = model.check_jobs([{"label": "A", "output": True, "path": "D:/", "problem": "No Extension token"}])
        self.assertEqual(r[0]["path"], "")
        self.assertIn("No Extension token", r[0]["errors"][0])

    def test_output_off_and_scene_saves_nothing(self):
        r = model.check_jobs([{"label": "A", "output": False, "scene_output": ""}])
        self.assertIn("Nothing would be saved", r[0]["errors"][0])

    def test_output_off_uses_the_scene_output(self):
        r = model.check_jobs([{"label": "A", "output": False, "scene_output": "D:/scene.exr"}])
        self.assertEqual((r[0]["path"], r[0]["errors"]), ("D:/scene.exr", []))

    def test_missing_camera(self):
        r = model.check_jobs([{"label": "A", "output": True, "path": "D:/a.png", "camera_missing": "Cam01"}])
        self.assertIn("Cam01", r[0]["errors"][0])

    def test_same_file_twice_warns_the_second(self):
        r = model.check_jobs([{"label": "#1 A", "output": True, "path": "D:/x.png"},
                              {"label": "#2 B", "output": False, "scene_output": "d:\\X.png"}])
        self.assertEqual(r[0]["warnings"], [])
        self.assertIn("#1 A", r[1]["warnings"][0])


class FindWritten(unittest.TestCase):
    def setUp(self):
        import tempfile
        import time
        self.dir = tempfile.mkdtemp(prefix="om_test_")
        self.now = time.time()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def touch(self, name, age=0.0):
        p = os.path.join(self.dir, name)
        with open(p, "wb") as f:
            f.write(b"x")
        os.utime(p, (self.now - age, self.now - age))
        return p

    def test_single_file(self):
        p = self.touch("Cam01.png")
        self.assertEqual(model.find_written(p, self.now), [os.path.normpath(p)])

    def test_old_file_does_not_count(self):
        p = self.touch("Cam01.png", age=3600)
        self.assertEqual(model.find_written(p, self.now), [])

    def test_frames_of_an_animation(self):
        self.touch("Cam010000.png")
        self.touch("Cam010001.PNG")
        self.touch("Cam01_Alpha0000.png")  # a render element, not a frame
        found = [os.path.basename(f) for f in model.find_written(os.path.join(self.dir, "Cam01.png"), self.now)]
        self.assertEqual(found, ["Cam010000.png", "Cam010001.PNG"])

    def test_nothing_written(self):
        self.assertEqual(model.find_written(os.path.join(self.dir, "nope.png"), self.now), [])
        self.assertEqual(model.find_written("", self.now), [])


if __name__ == "__main__":
    unittest.main()
