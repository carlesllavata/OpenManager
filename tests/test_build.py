"""OpenManager.bundle as tools/build.py writes it (no 3ds Max)."""
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build  # noqa: E402


class Bundle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="omgr_bundle_")
        icons = os.path.join(cls.tmp, "icons")
        for theme in build.THEMES:
            os.makedirs(os.path.join(icons, theme))
            build.write_png(os.path.join(icons, theme, "OpenManager_24.png"), build.draw_icon(24, theme, 1))
        cls.version = build.read_version()
        cls.target = build.build_bundle(cls.version, os.path.join(cls.tmp, "dist"), icons)
        cls.xml = ET.parse(os.path.join(cls.target, "PackageContents.xml")).getroot()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_versions_match_window_py(self):
        self.assertEqual(self.xml.get("AppVersion"), self.version)
        self.assertEqual({e.get("Version") for e in self.xml.iter("ComponentEntry")}, {self.version})

    def test_series_range_on_every_requirement(self):
        reqs = list(self.xml.iter("RuntimeRequirements"))
        self.assertEqual(len(reqs), 1 + len(build.COMPONENTS))
        for r in reqs:
            self.assertEqual((r.get("SeriesMin"), r.get("SeriesMax")), ("2025", "2099"))

    def test_parts_point_at_files(self):
        got = {c.get("Description"): c.find("ComponentEntry").get("ModuleName") for c in self.xml.iter("Components")}
        self.assertEqual(got, dict(build.COMPONENTS))
        for module in got.values():
            self.assertTrue(os.path.exists(os.path.join(self.target, module)), module)

    def test_tool_files_in_place(self):
        home = os.path.join(self.target, "Contents", "OpenManager")
        for f in ("omgr_core.ms", "omgr_setup.ms", "OpenManager_startup.ms", os.path.join("openmanager", "__init__.py"),
                  os.path.join("openmanager", "props.json")):
            self.assertTrue(os.path.isfile(os.path.join(home, f)), f)
        for base, dirs, files in os.walk(self.target):
            self.assertNotIn("__pycache__", dirs)
            self.assertFalse([f for f in files if f.endswith(".pyc")])

    def test_start_script_finds_the_tool(self):
        # OpenManager_bundle.ms resolves omgr_home as <scripts>\..\OpenManager
        scripts = os.path.join(self.target, "Contents", "scripts")
        self.assertTrue(os.path.isdir(os.path.normpath(os.path.join(scripts, "..", "OpenManager"))))

    def test_wrong_version_is_refused(self):
        with self.assertRaises(SystemExit):
            build.check_bundle(self.target, "9.9.9")


if __name__ == "__main__":
    unittest.main()
