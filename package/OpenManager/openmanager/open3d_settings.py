# SPDX-License-Identifier: GPL-3.0-or-later
"""What every OPEN3D app shares: the language, one preference in settings.json (D-050 to D-058), and
the folders each app keeps its own files in (D-042 to D-049).

This file is a copy. Its original is common/settings/open3d_settings.py in the OPEN3D root, which
also holds the contract it keeps (common/settings.md): change it there, never here. Standard library
only, Python 3.11 or newer.

The file is %APPDATA%\\Open3D\\settings.json, or settings.json in the folder that OPEN3D_SETTINGS_DIR
names. It is a JSON object whose "language" is "en" or "es". Reading never fails and never writes: no
file, no key, a file that cannot be read and any other value all mean "no preference yet", and then
the language of Windows decides (Spanish if it is Spanish, otherwise English). Writing keeps every
other key, and happens only when a person changes the language.

A language is its code: "en" or "es"; None is no preference.

An app keeps its settings in %APPDATA%\\Open3D\\<app> (app_settings_dir) and everything else it
writes in %LOCALAPPDATA%\\Open3D\\<app> (app_data_dir), or in <app> inside the folders that
OPEN3D_SETTINGS_DIR and OPEN3D_DATA_DIR name. At start, before it reads its settings, it copies the
folders it used before into the new ones with carry_over: once, whole, and leaving the old ones as
they were.
"""

import contextlib
import ctypes
import dataclasses
import json
import math
import os
import shutil
import stat
import sys
import time
from pathlib import Path

DIR_VARIABLE = "OPEN3D_SETTINGS_DIR"
DATA_DIR_VARIABLE = "OPEN3D_DATA_DIR"
FILE_NAME = "settings.json"
LANGUAGES = ("en", "es")
# What carry_over did (CarryOver.kind).
NOTHING, COPIED, FAILED = "nothing", "copied", "failed"
_KEY = "language"
_PRIMARY_LANGUAGE = 0x03FF
_LANG_SPANISH = 0x0A


def settings_dir(environ=None):
    """The folder of the shared settings: the one OPEN3D_SETTINGS_DIR names, otherwise
    %APPDATA%\\Open3D. None when neither variable is set. An empty value counts as not set."""
    return _open3d_dir(os.environ if environ is None else environ, DIR_VARIABLE, "APPDATA")


def data_dir(environ=None):
    """The folder of the other files of every app (caches, logs, recovery files, databases): the one
    OPEN3D_DATA_DIR names, otherwise %LOCALAPPDATA%\\Open3D. None when neither variable is set. An
    empty value counts as not set."""
    return _open3d_dir(os.environ if environ is None else environ, DATA_DIR_VARIABLE, "LOCALAPPDATA")


def app_settings_dir(app, environ=None):
    """The folder of an app's own settings (D-042): `app` in settings_dir, such as
    %APPDATA%\\Open3D\\OpenTools. None when there is no settings_dir."""
    folder = settings_dir(environ)
    return folder / app if folder is not None else None


def app_data_dir(app, environ=None):
    """The folder of everything else an app writes (D-044): `app` in data_dir, such as
    %LOCALAPPDATA%\\Open3D\\OpenTools. None when there is no data_dir."""
    folder = data_dir(environ)
    return folder / app if folder is not None else None


def _open3d_dir(environ, variable, base):
    """The folder a variable names, otherwise Open3D in the folder `base` names."""
    if environ.get(variable):
        return Path(environ[variable])
    if environ.get(base):
        return Path(environ[base]) / "Open3D"
    return None


@dataclasses.dataclass(frozen=True)
class CarryOver:
    """What carry_over did. `kind` is NOTHING (the new folder is there already, or there is no old
    folder), COPIED or FAILED. When it copied, `files` is how many files, and `left_out` what was not
    copied (a file that could not be read, such as one in use, or a link), as pairs of its path inside
    the old folder and why. When it failed, nothing was put in place and the new folder is still
    missing, so the next start tries again; `reason` says why."""

    kind: str
    files: int = 0
    left_out: tuple = ()
    reason: str = ""


def carry_over(old, new):
    """Copies an app's old folder into its new one, the first time it starts with the new folders
    (D-048, D-049). Only when nothing has the name `new` and `old` is a folder: everything in `old` is
    copied into a new folder beside `new`, which takes the name `new` once the copy is complete, so a
    copy cut half way is never taken for a finished one. An existing `new` is never touched, and `old`
    is never changed, moved or deleted. Links inside `old` are not followed. A file that cannot be read
    is left out and said; the rest is still copied. Call it at start, before the app reads its
    settings. Returns a CarryOver; it never raises for a folder or a file."""
    old, new = Path(old), Path(new)
    if _exists(new) or not os.path.isdir(old):
        return CarryOver(NOTHING)
    if Path(os.path.abspath(new)).is_relative_to(os.path.abspath(old)):
        return CarryOver(FAILED, reason=f"{new} is inside {old}")
    if not new.name:
        return CarryOver(FAILED, reason=f"{new} cannot be a folder of its own")
    try:
        new.parent.mkdir(parents=True, exist_ok=True)
        temporary = _new_folder(new.parent, new.name)
    except OSError as error:
        return CarryOver(FAILED, reason=f"couldn't create a folder in {new.parent} ({error})")
    copy = _Copying()
    try:
        copy.tree(old, temporary, Path())
        _put_in_place(temporary, new)
    except (_Stop, OSError) as error:
        shutil.rmtree(temporary, ignore_errors=True)
        # Another start of the same app may have put its own copy in place meanwhile.
        return CarryOver(NOTHING) if _exists(new) else CarryOver(FAILED, reason=str(error))
    return CarryOver(COPIED, files=copy.files, left_out=tuple(copy.left_out))


class _Stop(Exception):
    """Stops carry_over: something cannot be written, or the old folder itself cannot be read."""


def _exists(path):
    """Whether something has the name `path`: a folder, a file or a link. When that cannot be told,
    it counts as there, so that it is never touched."""
    try:
        os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except (OSError, ValueError):
        return True
    return True


def _new_folder(parent, name):
    """A new, empty folder of its own in `parent`, named after `name`, for carry_over to copy into."""
    for attempt in range(100):
        candidate = parent / f"{name}.carry-{os.getpid()}-{time.time_ns()}-{attempt}.tmp"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise FileExistsError(f"every name tried in {parent} is taken")


def _put_in_place(temporary, new):
    """Gives the finished copy its name, `new`. While nothing else has that name it tries a few
    times: another program, such as an antivirus, may hold the copy for a moment."""
    last = None
    for attempt in range(10):
        if attempt:
            time.sleep(0.05)
        if _exists(new):
            raise _Stop(f"{new} appeared while the copy was made")
        try:
            # Not os.replace: nothing that has the name `new` is ever replaced.
            os.rename(temporary, new)
            return
        except OSError as error:
            last = error
    raise _Stop(f"couldn't rename {temporary} to {new} ({last})")


class _Copying:
    """The files carry_over has copied so far, and what it left out."""

    def __init__(self):
        self.files = 0
        self.left_out = []

    def tree(self, source, target, inside):
        """Copies what the folder `source` holds into the empty folder `target`; `inside` is the path
        of `source` inside the old folder. Raises _Stop when the old folder itself cannot be read or
        something cannot be written."""
        try:
            with os.scandir(source) as found:
                entries = list(found)
        except OSError as error:
            if not inside.parts:
                raise _Stop(f"couldn't read {source} ({error})") from error
            self.left_out.append((inside, str(error)))
            return
        for entry in entries:
            path, destination = inside / entry.name, target / entry.name
            try:
                kind = _kind(entry)
            except OSError as error:
                self.left_out.append((path, str(error)))
                continue
            if kind == "folder":
                try:
                    destination.mkdir()
                except OSError as error:
                    raise _Stop(_couldnt_write(destination, error)) from error
                self.tree(Path(entry.path), destination, path)
            elif kind == "file":
                why = _copy_file(Path(entry.path), destination)
                if why is None:
                    self.files += 1
                else:
                    self.left_out.append((path, why))
            else:
                self.left_out.append((path, "not a plain file or folder, so not copied"))


def _kind(entry):
    """ "folder" or "file" for a plain folder or file; None for a link, a junction or anything else."""
    if entry.is_symlink():
        return None
    info = entry.stat(follow_symlinks=False)
    if getattr(info, "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT:
        return None
    if stat.S_ISDIR(info.st_mode):
        return "folder"
    return "file" if stat.S_ISREG(info.st_mode) else None


def _copy_file(source, target):
    """Copies the file `source` into the new file `target`, with its contents and the time it was last
    changed. Returns None, or why `source` cannot be read; then `target` is not left behind. Raises
    _Stop when `target` cannot be written. `source` is opened as other programs may still use it."""
    try:
        reader = open(source, "rb")
    except OSError as error:
        return str(error)
    with reader:
        try:
            info = os.fstat(reader.fileno())
        except OSError:
            info = None
        try:
            writer = open(target, "xb")
        except OSError as error:
            raise _Stop(_couldnt_write(target, error)) from error
        why = None
        try:
            with writer:
                while True:
                    try:
                        chunk = reader.read(1 << 16)
                    except OSError as error:
                        why = str(error)
                        break
                    if not chunk:
                        break
                    writer.write(chunk)
                if why is None:
                    writer.flush()
                    os.fsync(writer.fileno())
        except OSError as error:
            raise _Stop(_couldnt_write(target, error)) from error
    if why is not None:
        with contextlib.suppress(OSError):
            os.unlink(target)
        return why
    if info is not None:
        with contextlib.suppress(OSError):
            os.utime(target, ns=(info.st_atime_ns, info.st_mtime_ns))
    return None


def _couldnt_write(path, error):
    return f"couldn't write {path} ({error})"


def language(folder):
    """The language to show: the preference in `folder`, or the language of Windows when there is none."""
    return (read_language(folder) if folder is not None else None) or windows_language()


def read_language(folder):
    """The preference kept in `folder`; None when there is none yet. It never fails and never writes."""
    try:
        data = (Path(folder) / FILE_NAME).read_bytes()
    except OSError:
        return None
    return language_in(data)


def language_in(data):
    """The preference in the bytes of a settings.json."""
    found = _parse(data)
    code = found.get(_KEY) if found is not None else None
    return code if isinstance(code, str) and code in LANGUAGES else None


def write_language(folder, language):
    """Keeps `language` in `folder` as the shared preference; None takes the preference out, and then
    the language of Windows decides. Every other key of the file stays. The folder is created if it
    is missing, and the file is written whole into a new file beside it, which then takes its place.
    Call it only when a person changes the language.

    Returns None when it is written, otherwise what failed: it never raises for a file that cannot
    be written.
    """
    if language is not None and language not in LANGUAGES:
        raise ValueError(f"not a language: {language!r}")
    folder = Path(folder)
    path = folder / FILE_NAME
    try:
        old = path.read_bytes()
    except FileNotFoundError:
        old = None
    except OSError as error:
        # Its other keys could not be kept.
        return f"couldn't read {path} ({error})"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return f"couldn't create {folder} ({error})"
    return _replace(path, with_language(old, language))


def with_language(old, language):
    """What a settings.json holds after write_language: every key of `old` (bytes, or None for no
    file) and the language, or no "language" key for None. An `old` that is not a JSON object is not
    kept."""
    found = (_parse(old) if old is not None else None) or {}
    if language is None:
        found.pop(_KEY, None)
    else:
        found[_KEY] = language
    return (json.dumps(found, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def windows_language():
    """The language of Windows (D-052): Spanish when the user's interface language is Spanish, of
    any country; otherwise English."""
    return language_for_windows(_user_interface_language())


def language_for_windows(langid):
    """windows_language for a Windows language identifier (a LANGID): Spanish when its primary
    language is Spanish."""
    return "es" if langid & _PRIMARY_LANGUAGE == _LANG_SPANISH else "en"


def _user_interface_language():
    """The user's interface language, as GetUserDefaultUILanguage gives it; 0 outside Windows."""
    if sys.platform != "win32":
        return 0
    function = ctypes.windll.kernel32.GetUserDefaultUILanguage
    function.restype = ctypes.c_uint16
    function.argtypes = []
    return function()


def _parse(data):
    """The JSON object in the bytes of a settings.json (UTF-8, with or without a byte order mark),
    or None. Numbers too large for a double and NaN or Infinity make it unreadable, as in the Rust
    and C++ copies."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        found = json.loads(
            text.removeprefix("﻿"), parse_float=_finite_float, parse_int=_finite_int, parse_constant=_no_constant
        )
    except (ValueError, RecursionError):
        return None
    return found if isinstance(found, dict) else None


def _finite_float(text):
    value = float(text)
    if math.isinf(value):
        raise ValueError(f"too large: {text}")
    return value


def _finite_int(text):
    if math.isinf(float(text)):
        raise ValueError(f"too large: {text}")
    return int(text)


def _no_constant(text):
    raise ValueError(f"not JSON: {text}")


def _replace(path, data):
    """Writes `data` into a new file in the folder of `path`, which then takes the place of `path`:
    another app never reads half a file. Returns None, or what failed."""
    temporary = None
    try:
        for attempt in range(100):
            candidate = path.with_name(f"{FILE_NAME}.{os.getpid()}-{time.time_ns()}-{attempt}.tmp")
            try:
                handle = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
            except FileExistsError:
                continue
            temporary = candidate
            break
        else:
            return f"couldn't create a file in {path.parent} (every name tried is taken)"
        with os.fdopen(handle, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        temporary = None
        return None
    except OSError as error:
        return f"couldn't write {path} ({error})"
    finally:
        if temporary is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
