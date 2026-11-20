# SPDX-License-Identifier: GPL-3.0-or-later
"""Where OpenManager keeps its files, and the copy at start of the ones it kept in the plugcfg folder of each 3ds Max
(openmanager/folders.py). Every folder is a temporary one: the variables that name the folders point there, and the
3ds Max folders of before are fakes."""

import contextlib
import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "package", "OpenManager")
sys.path.insert(0, HERE)
sys.path.insert(0, TOOL)
import fake_max  # noqa: E402

rt = fake_max.install()
from openmanager import folders, open3d_settings  # noqa: E402

DAY = 86_400 * 10**9  # in nanoseconds
JAN_2026 = 1_767_225_600 * 10**9


def settings_of(year):
    """OpenManager's settings as a 3ds Max of that year keeps them, each set told apart by its year."""
    return {
        "OpenManager.json": b'{\n "theme": {"main": "dark"},\n "notify": false,\n "year": %d\n}' % year,
        "OpenManager_default.json": b'{\n "theme": {"main": "light"},\n "year": %d\n}' % year,
        "OpenManager_notify.txt": b"0",
    }


def make_plugcfg(root, year, language="ENU", locale="en-US", settings=None, hdri=0, changed=JAN_2026):
    """A plugcfg folder of before in `root` (which stands for %LOCALAPPDATA%\\Autodesk\\3dsMax): files of other
    plug-ins, OpenManager's settings (`settings`: {name: bytes}) changed at `changed`, and `hdri` HDRI previews.
    Returns the folder."""
    folder = Path(root, "%d - 64bit" % year, language, *([locale] if locale else []), "plugcfg")
    folder.mkdir(parents=True)
    (folder / "vray_dr.cfg").write_bytes(b"render-node 20204 1\n")
    (folder / "Corona").mkdir()
    (folder / "Corona" / "CoronaMaterialLibrary.cfg").write_bytes(b"x" * 300)
    (folder / "Puzles_SceneManager.json").write_bytes(b"{}")  # an older name: not OpenManager's settings
    for name, content in (settings or {}).items():
        (folder / name).write_bytes(content)
        os.utime(folder / name, ns=(changed, changed))
    if hdri:
        (folder / folders.HDRI).mkdir()
        for n in range(hdri):
            (folder / folders.HDRI / ("sky_%d_1048576_1700000000.jpg" % n)).write_bytes(bytes(range(256)) * (n + 3))
    return folder


def snapshot(folder):
    """Every file and folder inside `folder` by its path inside it, with a file's bytes and when it was changed."""
    found = {}
    for base, names, files in os.walk(folder):
        for name in names:
            found[os.path.relpath(os.path.join(base, name), folder)] = None
        for name in files:
            path = Path(base, name)
            found[os.path.relpath(path, folder)] = (path.read_bytes(), os.stat(path).st_mtime_ns)
    return found


class Scratch(unittest.TestCase):
    """A temporary folder for each test: Roaming and Local stand for %APPDATA% and %LOCALAPPDATA%, `old` for
    %LOCALAPPDATA%\\Autodesk\\3dsMax."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.roaming, self.local = self.root / "Roaming", self.root / "Local"
        self.old = self.local / "Autodesk" / "3dsMax"
        self.environ = {
            "APPDATA": str(self.roaming),
            "LOCALAPPDATA": str(self.local),
            folders.TEST_OLD_FOLDERS: str(self.old),
        }
        self.settings = self.roaming / "Open3D" / "OpenManager"
        self.data = self.local / "Open3D" / "OpenManager"
        self.addCleanup(setattr, folders, "_session", None)


class NewFolders(Scratch):
    def test_they_are_in_the_open3d_folders(self):
        self.assertEqual(folders.new_settings_dir(self.environ), self.settings)
        self.assertEqual(folders.new_data_dir(self.environ), self.data)
        found = folders.prepare(self.environ)
        self.assertEqual((found.settings, found.data, found.hdri), (self.settings, self.data, self.data / folders.HDRI))

    def test_the_open3d_variables_move_them(self):
        environ = dict(self.environ, OPEN3D_SETTINGS_DIR=str(self.root / "suite"), OPEN3D_DATA_DIR=str(self.root / "c"))
        self.assertEqual(folders.new_settings_dir(environ), self.root / "suite" / "OpenManager")
        self.assertEqual(folders.new_data_dir(environ), self.root / "c" / "OpenManager")

    def test_the_shared_module_is_the_one_inside_the_package(self):
        self.assertEqual(Path(open3d_settings.__file__).parent, Path(folders.__file__).parent)


class Choice(Scratch):
    """Which plugcfg folder the settings are taken from: the newest 3ds Max that has some."""

    def test_the_newest_version_with_settings_whichever_one_runs(self):
        make_plugcfg(self.old, 2025, settings=settings_of(2025))
        make_plugcfg(self.old, 2026, locale=None, settings=settings_of(2026), changed=JAN_2026 + 9 * DAY)
        newest = make_plugcfg(self.old, 2027, "FRA", "fr-FR", settings=settings_of(2027))
        make_plugcfg(self.old, 2028)  # other plug-ins only
        (self.old / "2029 - 64bit").mkdir()
        (self.old / "Downloads" / "ENU" / "en-US" / "plugcfg").mkdir(parents=True)
        (self.old / "Downloads" / "ENU" / "en-US" / "plugcfg" / "OpenManager.json").write_bytes(b"{}")
        candidates = folders.old_plugcfgs(self.environ)
        self.assertEqual(folders.newest(candidates), newest)
        # a 3ds Max 2025 that runs changes nothing
        running = (2025, self.old / "2025 - 64bit" / "ENU" / "en-US" / "plugcfg")
        self.assertEqual(folders.newest(folders.old_plugcfgs(self.environ, running)), newest)

    def test_of_two_languages_of_one_version_the_one_changed_last(self):
        english = make_plugcfg(self.old, 2027, settings=settings_of(2027), changed=JAN_2026)
        german = make_plugcfg(
            self.old, 2027, "DEU", "de-DE", settings={"OpenManager.json": b"{}"}, changed=JAN_2026 + DAY
        )
        self.assertEqual(folders.newest(folders.old_plugcfgs(self.environ)), german)
        os.utime(english / "OpenManager_notify.txt", ns=(JAN_2026 + 2 * DAY, JAN_2026 + 2 * DAY))
        self.assertEqual(folders.newest(folders.old_plugcfgs(self.environ)), english)

    def test_a_plugcfg_right_in_the_language_folder_counts(self):
        folder = make_plugcfg(self.old, 2027, "JPN", None, settings={"OpenManager_notify.txt": b"1"})
        self.assertEqual(folders.newest(folders.old_plugcfgs(self.environ)), folder)

    def test_the_running_one_counts_when_its_plugcfg_is_elsewhere(self):
        environ = dict(self.environ, **{folders.TEST_OLD_FOLDERS: ""})
        make_plugcfg(self.old, 2027, settings=settings_of(2027))
        elsewhere = self.root / "network" / "plugcfg"
        elsewhere.mkdir(parents=True)
        (elsewhere / "OpenManager.json").write_bytes(b"{}")
        self.assertEqual(folders.newest(folders.old_plugcfgs(environ, (2028, elsewhere))), elsewhere)
        # with fake folders of before, the running 3ds Max's own is never looked at
        self.assertNotIn((2028, elsewhere), folders.old_plugcfgs(self.environ, (2028, elsewhere)))

    def test_with_no_settings_before_nothing_is_chosen_or_made(self):
        make_plugcfg(self.old, 2027, hdri=2)  # previews without settings are not taken
        self.assertIsNone(folders.newest(folders.old_plugcfgs(self.environ)))
        found = folders.prepare(self.environ)
        self.assertEqual(found.carried, ())
        self.assertFalse((self.roaming / "Open3D").exists())
        self.assertFalse((self.local / "Open3D").exists())


class Carry(Scratch):
    """What the first start copies, and that it is done once and leaves the old folders as they were."""

    def test_the_first_start_copies_the_newest_settings_and_previews_once(self):
        make_plugcfg(self.old, 2026, settings=settings_of(2026), hdri=1)
        newest = make_plugcfg(self.old, 2027, settings=settings_of(2027), hdri=3, changed=JAN_2026 - DAY)
        before = snapshot(self.old)
        stage = self.root / "temp"
        stage.mkdir()
        with mock.patch.object(tempfile, "tempdir", str(stage)):
            found = folders.prepare(self.environ)
        self.assertEqual((found.settings, found.hdri), (self.settings, self.data / folders.HDRI))
        self.assertEqual(
            [(old, new, outcome.kind, outcome.files) for old, new, outcome in found.carried],
            [(newest, self.settings, "copied", 3), (newest / folders.HDRI, self.data / folders.HDRI, "copied", 3)],
        )
        # the settings of 3ds Max 2027 only, with their dates; the files of other plug-ins stay out
        self.assertEqual(
            snapshot(self.settings), {k: v for k, v in snapshot(newest).items() if k in folders.SETTINGS_FILES}
        )
        self.assertEqual(snapshot(self.data / folders.HDRI), snapshot(newest / folders.HDRI))
        self.assertEqual(
            folders.report(found),
            [
                "OpenManager: copied 3 file(s) from %s to %s; the old ones are left as they were."
                % (newest, self.settings),
                "OpenManager: copied 3 file(s) from %s to %s; the old ones are left as they were."
                % (newest / folders.HDRI, self.data / folders.HDRI),
            ],
        )
        self.assertEqual(folders.trouble(found), "")
        # nothing else is left beside the new folders, nor in the temporary folder
        self.assertEqual(os.listdir(self.roaming / "Open3D"), ["OpenManager"])
        self.assertEqual(os.listdir(self.local / "Open3D"), ["OpenManager"])
        self.assertEqual(os.listdir(self.data), [folders.HDRI])
        self.assertEqual(os.listdir(stage), [])
        # a change made in the new folder stays: the second start copies nothing
        (self.settings / "OpenManager_notify.txt").write_bytes(b"1")
        again = folders.prepare(self.environ)
        self.assertEqual((again.settings, again.hdri, again.carried), (found.settings, found.hdri, ()))
        self.assertEqual((self.settings / "OpenManager_notify.txt").read_bytes(), b"1")
        self.assertEqual(snapshot(self.old), before)

    def test_only_the_settings_files_there_are_copied(self):
        newest = make_plugcfg(self.old, 2027, settings={"OpenManager.json": b'{"notify": true}'})
        found = folders.prepare(self.environ)
        self.assertEqual([(o.kind, o.files) for _, _, o in found.carried], [("copied", 1)])
        self.assertEqual(os.listdir(self.settings), ["OpenManager.json"])
        self.assertEqual((self.settings / "OpenManager.json").read_bytes(), (newest / "OpenManager.json").read_bytes())
        # no previews before: their folder is made when the HDRI card makes one
        self.assertFalse(self.data.exists())

    def test_the_previews_are_copied_later_if_their_folder_is_still_missing(self):
        newest = make_plugcfg(self.old, 2027, settings=settings_of(2027))
        folders.prepare(self.environ)
        (newest / folders.HDRI).mkdir()
        (newest / folders.HDRI / "a.jpg").write_bytes(b"jpg")
        found = folders.prepare(self.environ)
        self.assertEqual([(old, o.kind) for old, _, o in found.carried], [(newest / folders.HDRI, "copied")])

    def test_a_copy_that_fails_leaves_the_session_on_the_old_folder(self):
        newest = make_plugcfg(self.old, 2027, settings=settings_of(2027), hdri=1)
        before = snapshot(self.old)
        blocked = self.root / "blocked"
        blocked.write_bytes(b"a file where the folder should be")
        environ = dict(self.environ, OPEN3D_SETTINGS_DIR=str(blocked))
        found = folders.prepare(environ)
        self.assertEqual([o.kind for _, _, o in found.carried], ["failed", "copied"])
        self.assertEqual((found.settings, found.hdri), (newest, self.data / folders.HDRI))
        self.assertTrue(
            folders.report(found)[0].startswith(
                "OpenManager: could not copy %s to %s (" % (newest, blocked / "OpenManager")
            )
        )
        self.assertTrue(folders.report(found)[0].endswith("); this session uses %s." % newest))
        self.assertIn("see the MAXScript Listener", folders.trouble(found))
        # the next start copies them
        blocked.unlink()
        again = folders.prepare(environ)
        self.assertEqual([(o.kind, o.files) for _, _, o in again.carried], [("copied", 3)])
        self.assertEqual(again.settings, blocked / "OpenManager")
        self.assertEqual(snapshot(self.old), before)

    def test_a_settings_file_that_cannot_be_copied_is_left_out_and_said(self):
        newest = make_plugcfg(self.old, 2027, settings={"OpenManager.json": b"{}"})
        (newest / "OpenManager_default.json").mkdir()  # not a file
        found = folders.prepare(self.environ)
        (_, _, outcome) = found.carried[0]
        self.assertEqual((outcome.kind, outcome.files), ("copied", 1))
        self.assertEqual(outcome.left_out, ((Path("OpenManager_default.json"), "not a plain file, so not copied"),))
        self.assertIn(
            "OpenManager: not copied to %s: %s (not a plain file, so not copied)"
            % (self.settings, newest / "OpenManager_default.json"),
            folders.report(found),
        )
        self.assertTrue(folders.trouble(found))

    def test_once_the_new_folders_are_there_the_old_ones_are_not_looked_at(self):
        self.settings.mkdir(parents=True)
        (self.data / folders.HDRI).mkdir(parents=True)
        with mock.patch.object(folders, "old_plugcfgs", side_effect=AssertionError("looked at the old folders")):
            found = folders.prepare(self.environ)
        self.assertEqual((found.settings, found.carried), (self.settings, ()))


class Session(Scratch):
    """The session's folders, as 3ds Max and the window get them."""

    def setUp(self):
        super().setUp()
        rt.reset()
        environ = dict(self.environ, OPEN3D_SETTINGS_DIR="", OPEN3D_DATA_DIR="")
        patcher = mock.patch.dict(os.environ, environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        folders._session = None

    def test_the_first_call_copies_says_so_and_tells_maxscript(self):
        make_plugcfg(self.old, 2027, settings=settings_of(2027))
        listener = io.StringIO()
        with contextlib.redirect_stdout(listener):
            found = folders.session()
            self.assertIs(folders.session(), found)
        self.assertEqual(found.settings, self.settings)
        self.assertEqual(listener.getvalue().count("OpenManager: copied 3 file(s) from "), 1)
        self.assertEqual(rt.omgr_settingsDir, str(self.settings))

    def test_the_start_up_script_sets_the_folders_up(self):
        """The Python that OpenManager_startup.ms runs when 3ds Max starts, run here on the fake 3ds Max."""
        make_plugcfg(self.old, 2027, settings=settings_of(2027))
        with open(os.path.join(TOOL, "OpenManager_startup.ms"), encoding="utf-8-sig") as f:
            src = f.read()
        literal = re.search(r'python\.Execute "((?:[^"\\]|\\.)*)"', src).group(1)
        code = re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), literal)
        rt._globals["omgr_home"] = TOOL
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(code, "OpenManager_startup.ms", "exec"), {})  # noqa: S102 - the script's own fixed text
        self.assertEqual(rt.omgr_settingsDir, str(self.settings))
        self.assertEqual((self.settings / "OpenManager_notify.txt").read_bytes(), b"0")
        # the file-open check reads the notification setting there
        check = src[src.index("fn omgr_startupCheck") :]
        self.assertIn('omgr_settingsDir + "\\\\OpenManager_notify.txt"', check)


class Sources(unittest.TestCase):
    def test_only_the_copy_and_the_older_version_s_clean_up_read_plugcfg(self):
        """The settings and the previews are read and written in the Open3D folders only: 3ds Max's plugcfg folder
        is looked at by folders.py, to copy from it, and by omgr_setup.ms, which gives the settings of the version
        before OpenManager their names there."""
        found = set()
        for folder in (
            TOOL,
            os.path.join(TOOL, "openmanager"),
            os.path.join(ROOT, "package"),
            os.path.join(ROOT, "bundle"),
            ROOT,
        ):
            for name in sorted(os.listdir(folder)):
                if name.endswith((".py", ".ms", ".mcr")):
                    with open(os.path.join(folder, name), encoding="utf-8-sig") as f:
                        if re.search(r'#plugcfg\b|Name\("plugcfg"\)', f.read(), re.I):
                            found.add(name)
        self.assertEqual(found, {"folders.py", "omgr_setup.ms"})


if __name__ == "__main__":
    unittest.main()
