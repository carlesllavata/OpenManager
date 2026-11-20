# SPDX-License-Identifier: GPL-3.0-or-later
"""The release package of an OPEN3D repository: python -I tools/repo.py package [--checked].

A part of the common tool: tools/repo.py loads it, and the [package] table of tools/repo.toml says
what goes in (the heading of tools/repo.py lists its keys). In order:

1. The version: every place that holds it agrees, and CHANGELOG.md has its "## X.Y.Z" section.
2. The quick checks of tools/check.ps1, unless --checked says they were just run.
3. The commands of `build`. Cargo gets the options that keep this computer's folders out of what it
   builds, added to the rustflags of [target.x86_64-pc-windows-msvc] in the repository's Cargo
   settings (RUSTFLAGS, when it is set, takes the place of those, as it always does for cargo).
4. With third_party = "cargo", the licence of every library linked into the program is checked, and
   their texts are gathered in THIRD-PARTY-LICENSES.txt.
5. The files the table names, under the names it gives; never __pycache__, .pyc or .pyo. LICENSE is
   always in: at the zip's root, or inside the bundle for a 3ds Max plugin.
6. No file in it may hold a folder of this computer, the folder of a Windows user or a word of the
   private list. A plugin's PackageContents.xml must say the version, and so must a program's file
   version and, where the table asks, its answer to --version.
7. With a [package.msi] table, dist/<name>-<version>-windows-x64.msi, which installs the same files
   into Program Files and is checked before it is written (tools/repo_msi.py).
8. dist/<name>-<version>-windows-x64.zip (-3dsmax.zip for a plugin) and dist/SHA256SUMS.txt, with a
   line for each file made, in the order of their names. Every file in the zip has the same date and
   they follow the order of their names, so the same files always give the same zip, byte for byte,
   with the same Python.

A folder in `files` holds the files Git tracks in it, and the new ones it would track; a folder that
Git knows nothing of, because a build makes it, is taken whole.
"""

import fnmatch
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

repo = sys.modules["open3d_repo"]  # tools/repo.py, which loads this file

CHANGELOG = "CHANGELOG.md"
DIST = "dist"
SUMS = "SHA256SUMS.txt"
THIRD_PARTY = "THIRD-PARTY-LICENSES.txt"
CARGO_TARGET = "{cargo_target}"
# The only target the packages are made for: the zip says windows-x64.
TARGET = "x86_64-pc-windows-msvc"
# The date of every file in the zip, the first one a zip can hold: the same files give the same zip.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
WILDCARDS = re.compile(r"[*?\[]")

# Licences of libraries that may be linked into a GPL-3.0-or-later program.
COMPATIBLE = {
    "0BSD",
    "Apache-2.0",
    "Apache-2.0 WITH LLVM-exception",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSL-1.0",
    "CC0-1.0",
    "CDLA-Permissive-2.0",
    "ISC",
    "LGPL-2.1-or-later",
    "LGPL-3.0-or-later",
    "MIT",
    "MIT-0",
    "MPL-2.0",
    "OFL-1.1",
    "Ubuntu-font-1.0",
    "Unicode-3.0",
    "Unicode-DFS-2016",
    "Unlicense",
    "Zlib",
    "GPL-3.0-or-later",
}
LICENCE_FILES = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|UNLICENSE|COPYRIGHT)", re.IGNORECASE)


def fail(text):
    raise repo.Failure(text)


# ---------------------------------------------------------------------------------- the settings


def table(settings):
    """The [package] table of the settings, once it is known to be well written."""
    if "package" not in settings:
        fail(f"this repository makes no release package: {repo.SETTINGS} has no [package]")
    if "version" not in settings:
        fail(f"{repo.SETTINGS}: a package needs the [version] of the repository")
    package = settings["package"]

    def words(value):
        return isinstance(value, list) and value and all(isinstance(word, str) and word for word in value)

    if not isinstance(package.get("name"), str) or not re.fullmatch(r"[A-Za-z][\w-]*", package["name"]):
        fail(f'{repo.SETTINGS}: [package] needs the name of the app, such as name = "OpenRef"')
    if not isinstance(package.get("build", []), list) or not all(words(args) for args in package.get("build", [])):
        fail(f'{repo.SETTINGS}: each command of build is a list of words, such as ["cargo", "build"]')
    if not isinstance(package.get("files"), list) or not package["files"]:
        fail(f"{repo.SETTINGS}: [package] needs the files that go in")
    for item in package["files"]:
        if isinstance(item, dict) and set(item) <= {"from", "to"} and isinstance(item.get("from"), str):
            if "to" in item and (not isinstance(item["to"], str) or WILDCARDS.search(item["from"])):
                fail(f"{repo.SETTINGS}: {item}: a `to` is a name in the zip, and names with wildcards keep their own")
        elif not isinstance(item, str):
            fail(f"{repo.SETTINGS}: each of the files is a name, or {{ from, to }}; not {item}")
    if package.get("third_party", "cargo") != "cargo":
        fail(f'{repo.SETTINGS}: the only third_party there is is "cargo"')
    if "bundle" in package and not str(package["bundle"]).endswith(".bundle"):
        fail(f'{repo.SETTINGS}: a bundle is the folder of a 3ds Max plugin, such as "OpenTools.bundle"')
    if "version_answer" in package and "exe" not in package:
        fail(f"{repo.SETTINGS}: version_answer is what the program, the exe, answers to --version")
    if "msi" in package:
        repo.part("repo_msi").msi_table(package)
    return package


def zip_name(package, version):
    """The name the Open3D launcher looks for in a release."""
    plugin = "-3dsmax" if "bundle" in package else ""
    return f"{package['name'].lower()}-{version}-windows-x64{plugin}.zip"


def msi_name(package, version):
    """The name of a program's Windows Installer package, as the Open3D launcher looks for it."""
    return f"{package['name'].lower()}-{version}-windows-x64.msi"


def release_files(package, version, dist):
    """What a release carries, all in dist/: the zip, the MSI of a program that has one, and SHA256SUMS.txt."""
    names = [zip_name(package, version)] + ([msi_name(package, version)] if "msi" in package else [])
    return [dist / name for name in [*names, SUMS]]


# ---------------------------------------------------------------------------------- the version


def heading(version):
    """The heading of the version's section in the CHANGELOG: "## 1.2.3", then a space or the end of the line."""
    return re.compile(rf"^## {re.escape(version)}(?=\s|$)[^\r\n]*", re.MULTILINE)


def ready_version(folder, settings):
    """The version, once every place agrees on it and the CHANGELOG has its section."""
    version = repo.read_version(folder, settings)
    problems, _ = repo.version_step(folder, settings, None)
    if problems:
        fail("the version is not the same in every place:\n  " + "\n  ".join(problems))
    changelog = folder / CHANGELOG
    if not changelog.is_file():
        fail(f"there is no {CHANGELOG}")
    if not heading(version).search(repo.read_text(changelog)):
        fail(
            f'{CHANGELOG} has no "## {version}" section. A package is made of a version that is ready:\n'
            f'"python -I tools/repo.py release {version}" turns "## In development" into that section first.'
        )
    return version


# ------------------------------------------------------------------------------------ cargo


def cargo_home():
    return os.environ.get("CARGO_HOME") or str(Path.home() / ".cargo")


def cargo_metadata(folder, *options):
    done = repo.call(
        repo.command(["cargo", "metadata", "--format-version", "1", *options]), cwd=folder, capture_output=True
    )
    if done.returncode != 0:
        fail("cargo metadata failed: " + done.stderr.decode("utf-8", errors="replace").strip())
    return json.loads(done.stdout.decode("utf-8"))


def cargo_target(folder):
    """Where cargo builds, as cargo itself says (its settings may send it outside the repository)."""
    return Path(cargo_metadata(folder, "--no-deps")["target_directory"])


def short_path(path):
    """The 8.3 spelling Windows has for a folder, which a build script may hand over; elsewhere the folder."""
    if os.name != "nt":
        return str(path)
    import ctypes

    buffer = ctypes.create_unicode_buffer(1024)
    got = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if 0 < got < len(buffer) else str(path)


def cargo_command(args, target):
    """A cargo command of `build` and what it runs with, so that the program says nothing of the computer
    it was built on. Returns (the command, its environment).

    rustc writes the full path of every source file that can panic into the program, and for the
    libraries that is cargo's home, inside the user's folder. Those paths are cut down to "cargo\\..."
    and "target\\...". The flags are added with --config to the rustflags of the target in the
    repository's Cargo settings, which cargo joins with them: in an environment variable they would
    take the place of those (such as the Visual C++ runtime linked in, D-151). Where RUSTFLAGS or
    CARGO_ENCODED_RUSTFLAGS is set, cargo reads no rustflags from its settings, so the flags join those
    instead. A library that compiles C code writes its paths too (__FILE__), and rustc's flags do not
    reach the C compiler: MSVC is told to trim the same folders, in both spellings Windows has for
    them, quoted for the cc crate (CC_SHELL_ESCAPED_FLAGS).
    """
    home = cargo_home()
    flags = [f"--remap-path-prefix={home}=cargo", f"--remap-path-prefix={target}=target"]
    env = dict(os.environ)
    for variable in ("CARGO_ENCODED_RUSTFLAGS", "RUSTFLAGS"):
        if variable in env and not env[variable]:
            del env[variable]  # set but empty, it would still take the place of the settings
    if env.get("CARGO_ENCODED_RUSTFLAGS"):
        env["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(env["CARGO_ENCODED_RUSTFLAGS"].split("\x1f") + flags)
    elif env.get("RUSTFLAGS"):
        env["CARGO_ENCODED_RUSTFLAGS"] = "\x1f".join(env.pop("RUSTFLAGS").split() + flags)
    else:
        # A TOML array of strings; JSON writes one, with the backslashes of the folders escaped.
        args = [args[0], "--config", f"target.{TARGET}.rustflags={json.dumps(flags)}", *args[1:]]
    trims = " ".join("'/d1trimfile:%s\\'" % folder for folder in dict.fromkeys([home, short_path(home), str(target)]))
    env["CFLAGS"] = (env.get("CFLAGS", "") + " " + trims).strip()
    env["CC_SHELL_ESCAPED_FLAGS"] = "1"
    env["CARGO_TARGET_DIR"] = str(target)
    return args, env


def licence_terms(expression):
    """The alternatives of a licence expression: a list (AND) of sets (OR)."""
    expression = expression.replace("/", " OR ").replace("(", " ").replace(")", " ")
    return [{term.strip() for term in part.split(" OR ") if term.strip()} for part in expression.split(" AND ")]


def third_party(folder, name, version):
    """Checks the licence of every library linked into the program and gathers their texts in one file."""
    meta = cargo_metadata(folder, "--filter-platform", TARGET, "--locked")
    used = {node["id"] for node in meta["resolve"]["nodes"]}
    # Libraries only needed to build or to test are not in the program: only normal dependencies are
    # followed, from the program itself.
    root = meta["resolve"]["root"]
    linked, queue = set(), [root]
    by_id = {node["id"]: node for node in meta["resolve"]["nodes"]}
    while queue:
        current = queue.pop()
        if current in linked:
            continue
        linked.add(current)
        for dep in by_id[current]["deps"]:
            if any(kind.get("kind") is None for kind in dep["dep_kinds"]):
                queue.append(dep["pkg"])
    libraries = sorted(
        (p for p in meta["packages"] if p["id"] in linked and p["id"] in used and p["id"] != root),
        key=lambda p: (p["name"].lower(), p["version"]),
    )
    lines = [
        f"{name} {version} contains the following libraries. Each is listed with its licence and,",
        "below, the licence texts that come with it.",
        "",
    ]
    problems = []
    for library in libraries:
        licence = library.get("license") or "(see its licence file)"
        lines.append(f"  {library['name']} {library['version']}  -  {licence}")
        if library.get("license"):
            for alternatives in licence_terms(library["license"]):
                if not alternatives & COMPATIBLE:
                    problems.append(f"{library['name']} {library['version']}: {library['license']}")
    if problems:
        fail("licences that need a look before distributing:\n  " + "\n  ".join(problems))
    for library in libraries:
        where = Path(library["manifest_path"]).parent
        texts = sorted(f for f in where.iterdir() if f.is_file() and LICENCE_FILES.match(f.name))
        if not texts:
            continue
        lines += ["", "=" * 100, f"{library['name']} {library['version']}", "=" * 100]
        for text in texts:
            lines += ["", f"--- {text.name} ---", "", text.read_text(encoding="utf-8", errors="replace").rstrip()]
    counted = f"{len(libraries)} {'library' if len(libraries) == 1 else 'libraries'}"
    repo.say(f"  {counted}, all with licences compatible with GPL-3.0-or-later")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------- what goes in


def kept(name):
    """Whether a file goes into a package at all: Python's caches never do."""
    return "__pycache__" not in name.split("/") and not name.endswith((".pyc", ".pyo"))


def gather(folder, package, known, target):
    """What goes into the zip: {its name in the zip: the file it comes from}.

    `known` is what Git tracks or would track; `target` gives cargo's target folder when it is named.
    """
    chosen = {}

    def put(name, source):
        if name in chosen:
            fail(f"two files would be {name} in the zip")
        chosen[name] = source

    for item in package["files"]:
        source, to = (item, item) if isinstance(item, str) else (item["from"], item.get("to", item["from"]))
        source, to = source.rstrip("/"), to.rstrip("/")
        if WILDCARDS.search(source):
            for name in known:
                if fnmatch.fnmatchcase(name, source) and kept(name):
                    put(name, folder / name)
            continue
        built = CARGO_TARGET in source
        path = Path(source.replace(CARGO_TARGET, str(target()))) if built else folder / source
        if path.is_file():
            put(to, path)
        elif path.is_dir():
            inside = [] if built else [name[len(source) + 1 :] for name in known if name.startswith(source + "/")]
            if not inside:
                inside = sorted(file.relative_to(path).as_posix() for file in path.rglob("*") if file.is_file())
            for name in inside:
                if kept(name):
                    put(f"{to}/{name}", path / name)
        else:
            fail(f"{path if built else source} was not found")
    licence = f"{package['bundle']}/LICENSE" if "bundle" in package else "LICENSE"
    if licence not in chosen:
        if not (folder / "LICENSE").is_file():
            fail("there is no LICENSE: every OPEN3D package carries its licence")
        chosen[licence] = folder / "LICENSE"
    return chosen


# ----------------------------------------------------------------------- what the files may not say


def this_computer(folder, target, also=()):
    """The folders of this computer a package must never name, in each spelling Windows has for them."""
    home = str(Path.home())
    folders = [home, short_path(home), cargo_home(), short_path(cargo_home())]
    for place in (folder, *also):
        folders += [os.path.abspath(place), str(Path(place).resolve())]
    if target:
        folders.append(str(target))
    return sorted({place.lower() for place in folders if len(place) >= 4})


def readings(data):
    """The text a file holds: all of it in a text file; in a binary one, its 8-bit and its 16-bit strings."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return [data.decode("utf-16", errors="replace")]
    if b"\0" not in data:
        return [data.decode("utf-8", errors="replace")]
    return [
        data.decode("latin-1"),
        data.decode("utf-16-le", errors="replace"),
        data[1:].decode("utf-16-le", errors="replace"),
    ]


def private_in(contents, folder, settings, folders):
    """What the files of the package hold that belongs to this computer, as lines to show."""
    terms = repo.private_terms(folder) or []
    allowed = [repo.pattern(entry["pattern"]) for entry in settings.get("private_data", {}).get("allow", [])]
    problems = []
    for name, data in sorted(contents.items()):
        lowered = data.lower()
        for place in folders:
            if any(place.encode(encoding) in lowered for encoding in ("utf-8", "utf-16-le")):
                problems.append(f"{name}: the folder {place}")
        for text in readings(data):
            # Most files hold nothing at all: only those are read line by line, with what is allowed.
            lowered_text = text.lower()
            if not repo.USER_FOLDER.search(text) and not any(term in lowered_text for _, term in terms):
                continue
            for line in re.split(r"[\0\r\n]+", text):
                excused = [found.span() for allow in allowed for found in allow.finditer(line)]
                for start, end, what in repo.private_in_line(line, terms):
                    if not any(a < end and start < b for a, b in excused):
                        problems.append(f"{name}: {what}")
    return sorted(set(problems))


def file_version(data):
    """The first three numbers of the file version of a Windows program, or None when it has none."""
    key = data.find("VS_VERSION_INFO".encode("utf-16-le"))
    start = data.find(b"\xbd\x04\xef\xfe", key) if key >= 0 else -1
    if start < 0 or start + 16 > len(data):
        return None
    high, low = struct.unpack_from("<2I", data, start + 8)
    return f"{high >> 16}.{high & 0xFFFF}.{low >> 16}"


def check_versions(package, version, chosen, contents):
    """The plugin's PackageContents.xml, the program's file version and its answer all say the version."""
    if "bundle" in package:
        xml = f"{package['bundle']}/PackageContents.xml"
        if xml not in contents:
            fail(f"the package has no {xml}")
        found = re.search(r'\sAppVersion\s*=\s*"([^"]+)"', contents[xml].decode("utf-8", errors="replace"))
        if not found or found.group(1) != version:
            fail(f"{xml} says AppVersion {found.group(1) if found else 'nothing'}, not {version}")
        repo.say(f"  {xml}: AppVersion {version}")
    if "exe" in package:
        exe = package["exe"]
        if exe not in contents:
            fail(f"the package has no {exe}")
        said = file_version(contents[exe])
        if said != version:
            fail(f"the file version of {exe} is {said or 'missing'}, not {version}")
        note = f"  {exe}: file version {version}"
        if "version_answer" in package:
            wanted = package["version_answer"].replace("{version}", version)
            try:
                done = repo.call([str(chosen[exe]), "--version"], capture_output=True)
            except OSError as error:
                fail(f"{exe} --version could not start: {error}")
            answer = done.stdout.decode("utf-8", errors="replace").strip()
            if answer != wanted:
                fail(f"{exe} --version answers '{answer}', not '{wanted}'")
            note += f', and it answers "{answer}"'
        repo.say(note)


# -------------------------------------------------------------------------------------- the zip


def write_zip(path, contents):
    """The zip of the files, the same bytes for the same files: one date for all, in the order of their names."""
    with zipfile.ZipFile(path, "w") as archive:
        for name in sorted(contents):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            archive.writestr(info, contents[name], compresslevel=9)


def write_whole(path, write):
    """Writes a file whole or not at all: into a new file beside it, which then takes its place."""
    handle, new = tempfile.mkstemp(dir=path.parent, prefix="package-", suffix=".tmp")
    os.close(handle)
    try:
        write(Path(new))
        os.replace(new, path)
    finally:
        if os.path.exists(new):
            os.unlink(new)


# --------------------------------------------------------------------------------- the package


def make_package(folder, settings, checked=False, files=None, out=None, also=(), target=None):
    """Makes the package of the repository in `folder` and returns its zip.

    `files` is what Git tracks or would track there (Git is asked when it is not given), `out` the
    folder the zip goes into (the repository's dist/ when not given), `also` other folders of this
    computer that the package must not name, and `target` the folder cargo builds in (cargo says
    which when it is not given).
    """
    package = table(settings)
    version = ready_version(folder, settings)
    repo.say(f"Packaging {package['name']} {version}")
    if not checked and repo.check(folder, settings, full=False) != 0:
        fail("the checks failed: put them right first (tools\\check.ps1 shows them again)")
    known = repo.repo_files(folder) if files is None else files

    found = [Path(target)] if target else []

    def target():
        if not found:
            found.append(cargo_target(folder))
        return found[0]

    for args in package.get("build", []):
        repo.say("  > " + " ".join(args))
        run, env = cargo_command(args, target()) if args[0] == "cargo" else (args, None)
        if repo.call(repo.command(run), cwd=folder, env=env).returncode != 0:
            fail(" ".join(args) + " failed")
    notices = third_party(folder, package["name"], version) if "third_party" in package else None

    chosen = gather(folder, package, known, target)
    contents = {name: source.read_bytes() for name, source in chosen.items()}
    if notices is not None:
        where = f"{package['bundle']}/{THIRD_PARTY}" if "bundle" in package else THIRD_PARTY
        contents[where] = notices.encode("utf-8")
    folders = this_computer(folder, found[0] if found else None, also)
    problems = private_in(contents, folder, settings, folders)
    if problems:
        fail("the package would name this computer:\n  " + "\n  ".join(problems))
    repo.say(f"  {repo.counted(len(contents), 'file')}, none naming this computer")
    check_versions(package, version, chosen, contents)

    dist = Path(out) if out else folder / DIST
    dist.mkdir(exist_ok=True)
    made = []
    if "msi" in package:
        # Made and checked first: if it fails, nothing in dist/ has changed.
        msi = dist / msi_name(package, version)
        made.append(repo.part("repo_msi").make_msi(folder, settings, version, contents, msi, folders))
    archive = dist / zip_name(package, version)
    write_whole(archive, lambda path: write_zip(path, contents))
    made.append(archive)
    digests = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in made}
    sums = "".join(f"{digests[name]}  {name}\n" for name in sorted(digests))
    write_whole(dist / SUMS, lambda path: path.write_bytes(sums.encode()))
    for path in sorted(made):
        repo.say(f"Wrote {dist.name}/{path.name} ({path.stat().st_size / 1e6:.1f} MB), sha256 {digests[path.name]}")
    repo.say(f"  and {dist.name}/{SUMS}")
    return archive


def main(folder, settings, checked=False):
    make_package(folder, settings, checked=checked)
    return 0
