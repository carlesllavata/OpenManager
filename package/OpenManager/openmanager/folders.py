# SPDX-License-Identifier: GPL-3.0-or-later
"""Where OpenManager keeps its files, and the copy of the ones it kept in 3ds Max's plugcfg folder.

Its settings (SETTINGS_FILES) are in %APPDATA%\\Open3D\\OpenManager, one set for every 3ds Max, and
everything else it writes is in %LOCALAPPDATA%\\Open3D\\OpenManager: the previews of the HDRI card
(OpenManager_hdri) and the thumbnails, exports and render presets of a scene that is not saved yet.
OPEN3D_SETTINGS_DIR and OPEN3D_DATA_DIR move them, as for every Open3D app (D-042, D-044).

Before, they were in the plugcfg folder of each 3ds Max, one set per version:
%LOCALAPPDATA%\\Autodesk\\3dsMax\\<year> - 64bit\\<language>\\<locale>\\plugcfg (or <language>\\plugcfg).
At start, before anything reads or writes the new folders, session() looks at the folders of every
version there, whichever version is running, takes the settings of the newest one that has some, and
its HDRI previews, and copies them into the new folders once. Every old folder is left as it was, and
the settings of the other versions stay where they are (D-048, D-049). When a copy fails, that session
uses the old folder and the next start tries again.

Neither 3ds Max nor Qt is imported when this module is.
"""

import dataclasses
import os
import re
import stat
import tempfile
from pathlib import Path

from . import open3d_settings

APP = "OpenManager"
# The settings files: in the settings folder, with the names they had in plugcfg.
SETTINGS_FILES = ("OpenManager.json", "OpenManager_default.json", "OpenManager_notify.txt")
# The previews the HDRI card makes: a folder in the data folder, with the name it had in plugcfg.
HDRI = "OpenManager_hdri"
# For tests only: a folder in place of %LOCALAPPDATA%\Autodesk\3dsMax, with plugcfg folders of before in
# it, so that a test never reads the person's own. The plugcfg of the running 3ds Max is then left out.
TEST_OLD_FOLDERS = "OPENMANAGER_TEST_OLD_FOLDERS"

_VERSION = re.compile(r"(\d{4}) - 64bit", re.I)
_LOCALE = re.compile(r"[a-z]{2,3}-[a-z]{2,4}", re.I)
_session = None  # the Folders of this session, once session() has made them


@dataclasses.dataclass(frozen=True)
class Folders:
    """The folders of a session: `settings` holds SETTINGS_FILES, `data` everything else, `hdri` the HDRI
    previews. Each is the new folder, or the old one whose copy failed. `carried`: (old, new, CarryOver)
    for each copy tried."""

    settings: Path
    data: Path
    hdri: Path
    carried: tuple = ()


def session():
    """The folders of this session. The first call carries the old ones over (prepare), says in the
    MAXScript Listener what it copied, and tells MAXScript where the settings are (omgr_settingsDir, which
    OpenManager_startup.ms reads); later calls give the same folders."""
    global _session
    if _session is None:
        _session = prepare(os.environ, running_plugcfg())
        for line in report(_session):
            print(line)
        _tell_max(_session.settings)
    return _session


def new_settings_dir(environ):
    """%APPDATA%\\Open3D\\OpenManager, or OpenManager in the folder OPEN3D_SETTINGS_DIR names."""
    return open3d_settings.app_settings_dir(APP, environ) or Path.home() / "AppData/Roaming/Open3D" / APP


def new_data_dir(environ):
    """%LOCALAPPDATA%\\Open3D\\OpenManager, or OpenManager in the folder OPEN3D_DATA_DIR names."""
    return open3d_settings.app_data_dir(APP, environ) or Path.home() / "AppData/Local/Open3D" / APP


def prepare(environ, running=None):
    """The folders of a session, once the old ones have been carried over: the settings of the newest
    3ds Max that has some (newest), and its HDRI previews, each only while its new folder is missing.
    `environ`: the variables; `running`: (year, plugcfg) of the 3ds Max this runs in, looked at too in
    case its plugcfg is not in the usual place. It never raises for a folder or a file."""
    settings, data = new_settings_dir(environ), new_data_dir(environ)
    hdri = data / HDRI
    found = Folders(settings, data, hdri)
    if os.path.lexists(settings) and os.path.lexists(hdri):
        return found
    source = newest(old_plugcfgs(environ, running))
    if source is None:
        return found
    carried = []
    if not os.path.lexists(settings):
        outcome = carry_settings(source, settings)
        carried.append((source, settings, outcome))
        if outcome.kind == open3d_settings.FAILED:
            found = dataclasses.replace(found, settings=source)
    old_hdri = source / HDRI
    if not os.path.lexists(hdri) and os.path.isdir(old_hdri):
        outcome = open3d_settings.carry_over(old_hdri, hdri)
        carried.append((old_hdri, hdri, outcome))
        if outcome.kind == open3d_settings.FAILED:
            found = dataclasses.replace(found, hdri=old_hdri)
    return dataclasses.replace(found, carried=tuple(carried))


def old_plugcfgs(environ, running=None):
    """Every plugcfg folder of before that may hold OpenManager's files, as [(3ds Max year, folder)]: in
    every <year> - 64bit folder of %LOCALAPPDATA%\\Autodesk\\3dsMax (or of TEST_OLD_FOLDERS), every
    language folder's plugcfg and that of each locale in it; and `running`, without TEST_OLD_FOLDERS."""
    if environ.get(TEST_OLD_FOLDERS):
        root, found = Path(environ[TEST_OLD_FOLDERS]), []
    else:
        root = Path(environ["LOCALAPPDATA"]) / "Autodesk" / "3dsMax" if environ.get("LOCALAPPDATA") else None
        found = [running] if running else []
    for version in _subfolders(root) if root is not None else []:
        match = _VERSION.fullmatch(version.name)
        if not match:
            continue
        year = int(match.group(1))
        for language in _subfolders(version):
            found.append((year, language / "plugcfg"))
            found.extend(
                (year, locale / "plugcfg") for locale in _subfolders(language) if _LOCALE.fullmatch(locale.name)
            )
    return found


def newest(candidates):
    """The folder with OpenManager's settings of the newest 3ds Max among `candidates`, (year, folder),
    or None. Of two of the same version (two languages), the one whose settings were changed last."""
    best, chosen, seen = None, None, set()
    for year, folder in candidates:
        key = os.path.normcase(os.path.abspath(folder))
        if key in seen:
            continue
        seen.add(key)
        changed = _last_change(Path(folder))
        if changed is not None and (best is None or (year, changed) > best):
            best, chosen = (year, changed), Path(folder)
    return chosen


def carry_settings(plugcfg, new):
    """carry_over for the settings files of `plugcfg`, which they share with other plug-ins: they are put
    in a temporary folder of their own first (in %TEMP%), which carry_over then copies into `new`. Returns
    the CarryOver, with the files of `plugcfg` that were left out."""
    left_out = []
    try:
        with tempfile.TemporaryDirectory(prefix="OpenManager-settings-", ignore_cleanup_errors=True) as stage:
            for name in SETTINGS_FILES:
                why = _stage(Path(plugcfg) / name, Path(stage) / name)
                if why is not None:
                    left_out.append((Path(name), why))
            outcome = open3d_settings.carry_over(stage, new)
    except OSError as error:
        return open3d_settings.CarryOver(
            open3d_settings.FAILED, reason=f"couldn't copy them to a temporary folder ({error})"
        )
    if outcome.kind == open3d_settings.COPIED and left_out:
        outcome = dataclasses.replace(outcome, left_out=tuple(left_out) + outcome.left_out)
    return outcome


def report(folders):
    """What carrying the old folders over did, as lines for the MAXScript Listener."""
    lines = []
    for old, new, outcome in folders.carried:
        if outcome.kind == open3d_settings.COPIED:
            lines.append(
                "OpenManager: copied %d file(s) from %s to %s; the old ones are left as they were."
                % (outcome.files, old, new)
            )
        elif outcome.kind == open3d_settings.FAILED:
            lines.append(
                "OpenManager: could not copy %s to %s (%s); this session uses %s." % (old, new, outcome.reason, old)
            )
        for path, why in outcome.left_out:
            lines.append("OpenManager: not copied to %s: %s (%s)" % (new, Path(old) / path, why))
    return lines


def trouble(folders):
    """What the window tells when a copy failed or left something out; "" when all went well."""
    for _old, _new, outcome in folders.carried:
        if outcome.kind == open3d_settings.FAILED or outcome.left_out:
            return "Some of OpenManager's files could not be copied to the Open3D folders (see the MAXScript Listener)"
    return ""


def running_plugcfg():
    """(year, plugcfg folder) of the 3ds Max this runs in; None outside 3ds Max."""
    try:
        from pymxs import runtime as rt

        # 27000 is 3ds Max 2025, 28000 is 2026
        return int(rt.maxVersion()[0]) // 1000 + 1998, Path(str(rt.getDir(rt.Name("plugcfg"))))
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError, IndexError):
        return None


def _tell_max(folder):
    """omgr_settingsDir: where OpenManager_startup.ms reads the notification setting."""
    try:
        from pymxs import runtime as rt

        rt.omgr_settingsDir = str(folder)
    except (ImportError, AttributeError, RuntimeError):
        pass


def _subfolders(folder):
    """The folders in `folder`, by name; none when it cannot be read."""
    try:
        with os.scandir(folder) as found:
            entries = list(found)
    except OSError:
        return []
    folders = []
    for entry in entries:
        try:
            if entry.is_dir():
                folders.append(Path(entry.path))
        except OSError:
            continue
    return sorted(folders, key=lambda path: path.name.lower())


def _last_change(folder):
    """When the settings files in `folder` were changed last (nanoseconds), or None when it has none."""
    times = []
    for name in SETTINGS_FILES:
        try:
            info = os.lstat(folder / name)
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            times.append(info.st_mtime_ns)
    return max(times) if times else None


def _stage(source, target):
    """Copies the settings file `source` into `target`, with the time it was last changed. Returns None
    (copied, or there is no such file) or why it was left out. Raises OSError when `target` cannot be
    written."""
    try:
        info = os.lstat(source)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        return str(error)
    if not stat.S_ISREG(info.st_mode):
        return "not a plain file, so not copied"
    try:
        data = source.read_bytes()
    except OSError as error:
        return str(error)
    target.write_bytes(data)
    os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns))
    return None
