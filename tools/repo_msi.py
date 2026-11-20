# SPDX-License-Identifier: GPL-3.0-or-later
r"""The Windows Installer package of an OPEN3D program, made beside its zip by python -I tools/repo.py package.

A part of the common tool: tools/repo_package.py loads it when tools/repo.toml has a [package.msi]
table, which only a program has (a [package] with `exe`). Its keys:

    upgrade_code    a GUID made once for the program and never changed: by it Windows Installer knows
                    that a new version replaces the one installed
    shortcut        the name of the program's shortcut in the Start menu
    icon            the .ico file of the repository that the exe carries, shown in Installed apps

dist/<name>-<version>-windows-x64.msi installs the files of the zip, at the same places, into
C:\Program Files\Open3D\<name>, for everyone on the computer, and one shortcut to the exe in the Start
menu of all users. Its Manufacturer is "Open3D", the publisher the Open3D launcher looks for. A newer
version, or another build of the same one, replaces what is installed (a major upgrade); an older one
stops with a message. It has no dialogs and no custom actions. Outside its folder it writes only the
shortcut and, because Windows Installer needs one to know that the shortcut is there, the value
StartMenuShortcut under HKEY_CURRENT_USER\Software\Open3D\<name>, besides what Windows Installer keeps
of every package. Uninstalling removes them all. Windows asks for permission to install it, to update
it and to remove it.

WiX 5 makes it from a source this file writes: `wix` on PATH, or the .NET global tool
(dotnet tool install --global wix --version 5.0.2). Before it goes into dist/ it is checked:

1. WiX's own validation, the ICEs of Windows Installer. ICE61 is left out: it warns that another build
   of the same version is replaced too, which is meant.
2. What the package says, read with Windows Installer's own msi.dll, which installs nothing: for
   everyone on the computer and for 64-bit Windows; its name, Manufacturer, version and UpgradeCode;
   the major upgrade and the message for an older version; one cabinet inside it; its folder; the one
   shortcut and its value; and rows in no table but those of files, a shortcut and an icon, so no
   custom action, dialog, service or other registry value.
3. The files WiX takes out of it are those of the zip, byte for byte, and the exe has the version as
   its file version; the icon is the icon.
4. Its tables and its summary name no folder of this computer.

Each build has a new ProductCode and package code, so two builds are never the same bytes. All the files
go into one cabinet of up to 2000 MB, the most a cabinet holds.

A repository that makes its zip with a script of its own, not with tools/repo.py, makes the MSI of the
folder the zip is made from, with tools/repo.py and tools/repo_package.py beside this file:

    python -I tools/repo_msi.py FOLDER --out FILE.msi --name NAME --version X.Y.Z --exe PATH_IN_FOLDER
        --upgrade-code GUID --shortcut NAME --icon FILE.ico [--repo REPOSITORY]

The keys are those of [package.msi], and the icon is a file of the repository (the current folder unless
--repo names it). It makes and checks the MSI as above, from every file in FOLDER, and writes FILE.msi;
nothing else, not SHA256SUMS.txt.
"""

import argparse
import ctypes
import importlib.util
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from xml.sax.saxutils import escape, quoteattr


def common_tool():
    """tools/repo.py, which loads tools/repo_package.py and this file; loaded from beside this file when this
    file runs on its own, as repo.py loads its parts."""
    if "open3d_repo" not in sys.modules:
        spec = importlib.util.spec_from_file_location("open3d_repo", Path(__file__).absolute().with_name("repo.py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules["open3d_repo"] = module
        writes, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = writes
    return sys.modules["open3d_repo"]


repo = common_tool()

MANUFACTURER = "Open3D"
# The most a cabinet holds, uncompressed, in megabytes; WiX would make a new one every 200.
CABINET_MB = 2000
KEYS = {"upgrade_code", "shortcut", "icon"}
GUID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")
# What Windows refuses in the name of a file, and so of a shortcut.
NOT_IN_A_NAME = re.compile(r'[\\/:*?"<>|]')
# The value by which Windows Installer knows that the shortcut is there.
SHORTCUT_VALUE = "StartMenuShortcut"
ICON = "ProductIcon.ico"
# The tables of a package that only copies files and makes a shortcut. Rows in any other table do
# something else: a custom action, a dialog, a service, a file type, an environment variable...
TABLES = {
    "AdminExecuteSequence",
    "AdminUISequence",
    "AdvtExecuteSequence",
    "Component",
    "Directory",
    "Feature",
    "FeatureComponents",
    "File",
    "Icon",
    "InstallExecuteSequence",
    "InstallUISequence",
    "LaunchCondition",
    "Media",
    "MsiFileHash",
    "Property",
    "Registry",
    "Shortcut",
    "Upgrade",
    "_Validation",
}
# Answers of msi.dll.
MORE_DATA, NO_MORE_ITEMS = 234, 259


def fail(text):
    raise repo.Failure(text)


# ---------------------------------------------------------------------------------- the settings


def msi_table(package):
    """The [package.msi] table, once it is known to be well written."""
    msi = package["msi"]
    where = f"{repo.SETTINGS}: [package.msi]"
    if not isinstance(msi, dict):
        fail(f"{repo.SETTINGS}: msi is a table of its own, [package.msi]")
    unknown = sorted(set(msi) - KEYS)
    if unknown:
        fail(f"{where} has keys it does not know: {', '.join(unknown)}")
    if "exe" not in package or "bundle" in package:
        fail(f"{where} is for a program: its [package] names the exe, and a 3ds Max plugin has no MSI")
    if not isinstance(msi.get("upgrade_code"), str) or not GUID.fullmatch(msi["upgrade_code"]):
        fail(f'{where} needs the upgrade_code of the program, a GUID like "8F0C2D5E-1B3A-4C6D-9E7F-0A1B2C3D4E5F"')
    shortcut = msi.get("shortcut")
    if not isinstance(shortcut, str) or not shortcut.strip() or NOT_IN_A_NAME.search(shortcut):
        fail(f'{where} needs the name of the shortcut in the Start menu, such as shortcut = "{package["name"]}"')
    if not isinstance(msi.get("icon"), str) or not msi["icon"].lower().endswith(".ico"):
        fail(f'{where} needs the icon the exe carries, an .ico file such as icon = "assets/icon.ico"')
    return msi


def check_version(version):
    """A version Windows Installer can compare: three numbers, up to 255, 255 and 65535."""
    parts = [int(number) for number in version.split(".")]
    if len(parts) != 3 or parts[0] > 255 or parts[1] > 255 or parts[2] > 65535:
        fail(f"the version of an MSI is three numbers up to 255.255.65535, and {version} is not")


def registry_key(name):
    return f"Software\\{MANUFACTURER}\\{name}"


# ------------------------------------------------------------------------------------ the source


def folder_of(name):
    """The folder a file of the zip is in, as "a/b"; "" for the root."""
    parent = PurePosixPath(name).parent.as_posix()
    return "" if parent == "." else parent


def folder_ids(names):
    """{folder inside the install folder: the Id of its Directory}; the install folder is ""."""
    folders = {""}
    for name in names:
        folders.update(parent.as_posix() for parent in PurePosixPath(name).parents if parent.as_posix() != ".")
    return {folder: f"Folder{number}" if folder else "INSTALLFOLDER" for number, folder in enumerate(sorted(folders))}


def source(name, version, msi, exe, files, icon):
    """The WiX source of the package. `files` are those of the zip, {name in the zip: the full path of a copy},
    `exe` is the program among them and `icon` the full path of its icon."""
    ids = folder_ids(files)

    def directory(folder, indent):
        """The Directory of a folder, with those inside it."""
        inside = [
            line for sub in sorted(ids) if sub and folder_of(sub) == folder for line in directory(sub, indent + 2)
        ]
        named = PurePosixPath(folder).name if folder else name
        opened = " " * indent + f"<Directory Id={quoteattr(ids[folder])} Name={quoteattr(named)}"
        return [opened + ">", *inside, " " * indent + "</Directory>"] if inside else [opened + " />"]

    exe_folder = ids[folder_of(exe)]
    target = f"[{exe_folder}]{PurePosixPath(exe).name}"
    downgrade = f"A newer version of {name} is already installed."
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f"<!-- {escape(name)} {escape(version)}: written by tools/repo_msi.py from tools/repo.toml. -->",
        '<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">',
        f"  <Package Name={quoteattr(name)} Manufacturer={quoteattr(MANUFACTURER)} Version={quoteattr(version)}",
        f'      UpgradeCode={quoteattr(msi["upgrade_code"].upper())} Scope="perMachine" Language="1033">',
        f'    <MajorUpgrade AllowSameVersionUpgrades="yes" DowngradeErrorMessage={quoteattr(downgrade)} />',
        f'    <MediaTemplate EmbedCab="yes" MaximumUncompressedMediaSize="{CABINET_MB}" />',
        f"    <Icon Id={quoteattr(ICON)} SourceFile={quoteattr(str(icon))} />",
        f'    <Property Id="ARPPRODUCTICON" Value={quoteattr(ICON)} />',
        "    <!-- It has no dialogs, so Installed apps offers nothing to modify. -->",
        '    <Property Id="ARPNOMODIFY" Value="1" />',
        '    <StandardDirectory Id="ProgramFiles64Folder">',
        '      <Directory Id="Open3DFolder" Name="Open3D">',
        *directory("", 8),
        "      </Directory>",
        "    </StandardDirectory>",
        '    <Feature Id="Main">',
        *(
            f"      <Component Directory={quoteattr(ids[folder_of(file)])}>"
            f"<File Name={quoteattr(PurePosixPath(file).name)} Source={quoteattr(str(files[file]))} /></Component>"
            for file in sorted(files)
        ),
        "      <!-- The shortcut has a component of its own, which Windows Installer knows by its value. -->",
        '      <Component Directory="ProgramMenuFolder">',
        f"        <Shortcut Name={quoteattr(msi['shortcut'])} Target={quoteattr(target)}"
        f" WorkingDirectory={quoteattr(exe_folder)} />",
        f'        <RegistryValue Root="HKCU" Key={quoteattr(registry_key(name))} Name="{SHORTCUT_VALUE}"'
        ' Type="integer" Value="1" KeyPath="yes" />',
        "      </Component>",
        "    </Feature>",
        "  </Package>",
        "</Wix>",
    ]
    return "\n".join(lines) + "\n"


# -------------------------------------------------------------------- reading a package: msi.dll


def read_msi(path):
    """Every table of a package and its summary, read with msi.dll, which installs nothing.

    {"tables": {table: [{column: text}]}, "summary": {property number: value}}. A number is given as
    its text and an empty field as ""; a column of binary data (an icon, a cabinet) is left out.
    """
    msi = ctypes.WinDLL("msi")
    opened = []

    def checked(code, what):
        if code != 0:
            fail(f"msi.dll could not read {Path(path).name}: {what} (error {code})")

    def handle():
        value = ctypes.c_ulong(0)
        opened.append(value)
        return value

    def longer(ask):
        """What a call of msi.dll gives as text: asked once for its length, then again with room for it."""
        size = ctypes.c_uint(0)
        buffer = ctypes.create_unicode_buffer(1)
        code = ask(buffer, size)
        if code == MORE_DATA:
            size.value += 1
            buffer = ctypes.create_unicode_buffer(size.value)
            code = ask(buffer, size)
        return code, buffer.value

    def field(record, number):
        code, value = longer(lambda buffer, size: msi.MsiRecordGetStringW(record, number, buffer, ctypes.byref(size)))
        checked(code, f"field {number}")
        return value

    def rows(database, query):
        view = handle()
        checked(msi.MsiDatabaseOpenViewW(database, query, ctypes.byref(view)), query)
        checked(msi.MsiViewExecute(view, 0), query)
        names, types = [], []
        for asked, found in ((0, names), (1, types)):  # the names of the columns, then their types
            info = handle()
            checked(msi.MsiViewGetColumnInfo(view, asked, ctypes.byref(info)), query)
            found += [field(info, number) for number in range(1, msi.MsiRecordGetFieldCount(info) + 1)]
        columns = enumerate(zip(names, types, strict=True), 1)
        texts = [(number, column) for number, (column, kind) in columns if kind[:1] not in "vV"]  # "v": binary
        found = []
        while True:
            record = handle()
            code = msi.MsiViewFetch(view, ctypes.byref(record))
            if code == NO_MORE_ITEMS:
                return found
            checked(code, query)
            found.append({column: field(record, number) for number, column in texts})

    def summary(database):
        info = handle()
        checked(msi.MsiGetSummaryInformationW(database, None, 0, ctypes.byref(info)), "its summary")
        said = {}
        for number in (2, 3, 4, 5, 6, 7, 8, 9, 15, 18):
            kind, value, stamp = ctypes.c_uint(0), ctypes.c_int(0), ctypes.create_string_buffer(8)

            def ask(buffer, size, number=number, kind=kind, value=value, stamp=stamp):
                where = (ctypes.byref(kind), ctypes.byref(value), stamp, buffer, ctypes.byref(size))
                return msi.MsiSummaryInfoGetPropertyW(info, number, *where)

            code, text = longer(ask)
            checked(code, f"property {number} of its summary")
            said[number] = {3: value.value, 30: text}.get(kind.value)  # VT_I4, VT_LPSTR; else nothing
        return said

    try:
        database = handle()
        checked(msi.MsiOpenDatabaseW(str(path), None, ctypes.byref(database)), "opening it")
        names = [row["Name"] for row in rows(database, "SELECT `Name` FROM `_Tables`")]
        # The names come from the package's own list of its tables.
        tables = {name: rows(database, f"SELECT * FROM `{name}`") for name in names}  # noqa: S608
        return {"tables": tables, "summary": summary(database)}
    finally:
        for value in reversed(opened):
            if value.value:
                msi.MsiCloseHandle(value)


# ------------------------------------------------------------------------ what the package says


def long_name(value):
    """The long name in a DefaultDir or a FileName, which may be "short|long" and "target:source"."""
    return value.split(":")[0].split("|")[-1]


def policy(read, expected):
    """What the package does that an OPEN3D program's may not, as lines to show; none when it is right.

    `read` is what read_msi gives, plus "extracted": {File key or Icon name: bytes}, as WiX takes them
    out. `expected` has the name, version, upgrade_code, shortcut, exe, files ({name in the zip:
    bytes}) and icon (bytes).
    """
    tables, summary, extracted = read["tables"], read["summary"], read["extracted"]
    properties = {row["Property"]: row["Value"] for row in tables.get("Property", [])}
    name, version = expected["name"], expected["version"]
    problems = []

    # Who it is for, and what it is.
    if properties.get("ALLUSERS") != "1" or "MSIINSTALLPERUSER" in properties or (summary.get(15) or 0) & 8:
        problems.append("it is not for everyone on the computer, with Windows asking for permission")
    if summary.get(7) != "x64;1033":
        problems.append(f"its summary says the platform {summary.get(7)!r}, not 'x64;1033'")
    for key, wanted in (("ProductName", name), ("Manufacturer", MANUFACTURER), ("ProductVersion", version)):
        if properties.get(key) != wanted:
            problems.append(f"its {key} is {properties.get(key)!r}, not {wanted!r}")
    code = "{" + expected["upgrade_code"].upper() + "}"
    if properties.get("UpgradeCode", "").upper() != code:
        problems.append(f"its UpgradeCode is {properties.get('UpgradeCode')}, not the {code} of {repo.SETTINGS}")

    # A newer version replaces it; an older one stops with a message.
    upgrades = {(row["UpgradeCode"].upper(), row["ActionProperty"]) for row in tables.get("Upgrade", [])}
    if upgrades != {(code, "WIX_UPGRADE_DETECTED"), (code, "WIX_DOWNGRADE_DETECTED")}:
        problems.append("it is not a major upgrade of its own UpgradeCode alone")
    if "RemoveExistingProducts" not in {row["Action"] for row in tables.get("InstallExecuteSequence", [])}:
        problems.append("it does not remove the version installed before it")
    if not any(row["Condition"] == "NOT WIX_DOWNGRADE_DETECTED" for row in tables.get("LaunchCondition", [])):
        problems.append("an older version would not stop with a message")

    # Nothing but files, a shortcut and an icon, from one cabinet inside it.
    for table in sorted(set(tables) - TABLES):
        if tables[table]:
            problems.append(f"its table {table} has {repo.counted(len(tables[table]), 'row')}: it does more")
    media = tables.get("Media", [])
    if len(media) != 1 or not media[0]["Cabinet"].startswith("#"):
        problems.append("its files are not in one cabinet inside it")

    # Its folder, and every component inside it but the shortcut's.
    directories = {
        row["Directory"]: (row["Directory_Parent"], long_name(row["DefaultDir"])) for row in tables.get("Directory", [])
    }
    install = directories.get("INSTALLFOLDER", ("", ""))
    suite = directories.get(install[0], ("", ""))
    program_files = directories.get(suite[0], ("", ""))
    if (install[1], suite[1], suite[0], program_files[0]) != (name, "Open3D", "ProgramFiles64Folder", "TARGETDIR"):
        problems.append(f"it does not install into Program Files\\Open3D\\{name}")

    def inside(directory):
        """The folder inside the install folder, as "a/b" ("" for the install folder); None outside it."""
        parts = []
        while directory != "INSTALLFOLDER":
            if not directories.get(directory, ("", ""))[0] or len(parts) > 100:
                return None
            parts.append(directories[directory][1])
            directory = directories[directory][0]
        return "/".join(reversed(parts))

    components = {row["Component"]: row for row in tables.get("Component", [])}
    for row in components.values():
        if row["Directory_"] != "ProgramMenuFolder" and inside(row["Directory_"]) is None:
            problems.append(f"its component {row['Component']} goes outside its folder")

    # The files: those of the zip, byte for byte.
    installed = {}
    for row in tables.get("File", []):
        folder = inside(components.get(row["Component_"], {}).get("Directory_", ""))
        if folder is None:
            problems.append(f"its file {long_name(row['FileName'])} goes outside its folder")
        else:
            installed[f"{folder}/{long_name(row['FileName'])}".lstrip("/")] = row
    files = expected["files"]
    problems += [f"it lacks {file}, which the zip has" for file in sorted(set(files) - set(installed))]
    problems += [f"it has {file}, which the zip has not" for file in sorted(set(installed) - set(files))]
    for file in sorted(set(files) & set(installed)):
        row = installed[file]
        if row["FileSize"] != str(len(files[file])) or extracted.get(row["File"]) != files[file]:
            problems.append(f"its {file} is not the one in the zip")
    exe = installed.get(expected["exe"])
    if exe and ".".join(exe["Version"].split(".")[:3]) != version:
        problems.append(f"the file version of its {expected['exe']} is {exe['Version'] or 'missing'}, not {version}")

    # One shortcut in the Start menu, to the exe, kept by its value: the only one in the registry.
    shortcuts, registry = tables.get("Shortcut", []), tables.get("Registry", [])
    kept = components.get(shortcuts[0]["Component_"], {}) if len(shortcuts) == 1 else {}
    if len(shortcuts) != 1:
        problems.append(f"it has {repo.counted(len(shortcuts), 'shortcut')}, not one in the Start menu")
    else:
        shortcut = shortcuts[0]
        if shortcut["Directory_"] != "ProgramMenuFolder" or long_name(shortcut["Name"]) != expected["shortcut"]:
            problems.append(f"its shortcut is not {expected['shortcut']!r} in the Start menu")
        exe_folder = components[exe["Component_"]]["Directory_"] if exe else None
        if not exe or shortcut["Target"] not in (f"[#{exe['File']}]", f"[{exe_folder}]{long_name(exe['FileName'])}"):
            problems.append(f"its shortcut goes to {shortcut['Target']}, not to {expected['exe']}")
    value = {"Root": "1", "Key": registry_key(name), "Name": SHORTCUT_VALUE, "Value": "#1"}
    values = [row for row in registry if row["Registry"] == kept.get("KeyPath")]
    if kept and (
        kept["Directory_"] != "ProgramMenuFolder" or [{k: row[k] for k in value} for row in values] != [value]
    ):
        problems.append(f"its shortcut is not kept by the value HKEY_CURRENT_USER\\{value['Key']}\\{SHORTCUT_VALUE}")
    for row in registry:
        if row["Registry"] != kept.get("KeyPath"):
            problems.append(f"it writes the registry value {row['Name'] or '(default)'} of {row['Key']}")

    # The icon of Installed apps.
    if extracted.get(properties.get("ARPPRODUCTICON")) != expected["icon"]:
        problems.append("Installed apps would not show the icon of the exe")
    return problems


# ----------------------------------------------------------------------------- making the package


def wix(args, what, show=True, cwd=None):
    """Runs WiX and returns what it said. It is shown when WiX fails, and its warnings when `show`."""
    options = {"cwd": cwd, "capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace"}
    done = repo.call(repo.command(["wix", *args]), **options)
    said = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    if done.returncode != 0:
        fail(f"{what} failed (exit code {done.returncode})" + "".join("\n  " + line for line in said))
    for line in said if show else []:
        repo.say("    " + line)
    return said


def taken_out(folder):
    """What `wix msi decompile -x` took out of the package: {File key or Icon name: bytes}."""
    found = {}
    for kind in ("File", "Icon"):
        if (folder / kind).is_dir():
            found.update({path.name: path.read_bytes() for path in (folder / kind).iterdir() if path.is_file()})
    return found


def tables_text(read):
    """Every text of the package's tables and summary, one to a line."""
    texts = [str(value) for value in read["summary"].values() if value is not None]
    texts += [value for rows in read["tables"].values() for row in rows for value in row.values()]
    return "\n".join(texts).encode("utf-8")


def make_msi(folder, settings, version, contents, out, folders):
    """Makes the MSI of the program in `folder`, checks it and writes it to `out`, which it returns.

    `contents` is what the zip holds, {name: bytes}, and `folders` the folders of this computer that a
    package must not name.
    """
    package = settings["package"]
    msi = msi_table(package)
    check_version(version)
    icon = folder / msi["icon"]
    if not icon.is_file():
        fail(f"{msi['icon']}, the icon of [package.msi], was not found")
    size = sum(len(data) for data in contents.values())
    if size > CABINET_MB * 2**20:
        fail(f"the files come to {size / 2**20:.0f} MB, and the one cabinet of an MSI holds at most {CABINET_MB} MB")
    said = wix(["--version"], "wix --version", show=False)
    repo.say(f"  the MSI, made with WiX {said[0].split('+')[0] if said else '(of no known version)'}:")
    with tempfile.TemporaryDirectory(prefix="open3d-msi-") as work:
        work = Path(work)
        # WiX takes the files from copies of what the zip holds, never from the repository's own files.
        copies = {name: work / "files" / name for name in contents}
        for name, data in contents.items():
            copies[name].parent.mkdir(parents=True, exist_ok=True)
            copies[name].write_bytes(data)
        wxs, built, taken = work / "package.wxs", work / "package.msi", work / "taken out"
        wxs.write_text(source(package["name"], version, msi, package["exe"], copies, icon.absolute()), "utf-8")
        build = ["build", str(wxs), "-arch", "x64", "-out", str(built), "-pdbtype", "none"]
        wix([*build, "-intermediatefolder", str(work / "build")], "wix build", cwd=work)
        validate = ["msi", "validate", str(built), "-sice", "ICE61", "-intermediateFolder", str(work / "ice")]
        wix(validate, "WiX's validation", cwd=work)
        repo.say("    WiX's validation (the ICEs) passed")
        decompile = ["msi", "decompile", str(built), "-x", str(taken), "-out", str(work / "taken.wxs")]
        wix(decompile, "wix msi decompile", cwd=work)
        read = {**read_msi(built), "extracted": taken_out(taken)}
        expected = {
            "name": package["name"],
            "version": version,
            "upgrade_code": msi["upgrade_code"],
            "shortcut": msi["shortcut"],
            "exe": package["exe"],
            "files": contents,
            "icon": icon.read_bytes(),
        }
        problems = policy(read, expected)
        if problems:
            fail("the MSI is not what an OPEN3D program installs:\n  " + "\n  ".join(problems))
        packager = repo.part("repo_package")
        everywhere = sorted({*folders, str(work).lower(), str(work.resolve()).lower()})
        named = packager.private_in({out.name: tables_text(read)}, folder, settings, everywhere)
        if named:
            fail("the MSI would name this computer:\n  " + "\n  ".join(named))
        repo.say(
            f"    for everyone, into Program Files\\Open3D\\{package['name']}: the {len(contents)} files of the zip,"
            f' byte for byte, and the shortcut "{msi["shortcut"]}" in the Start menu; no custom action'
        )
        packager.write_whole(out, lambda new: shutil.copyfile(built, new))
    return out


# ----------------------------------------------------------------------------- on its own


def arguments_of(arguments):
    """What the command line asks for, or a Failure that says what is wrong with it."""

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            fail(f"{message}\n{self.format_usage().strip()}")

    parser = Parser(prog="repo_msi.py", description="The MSI of the files in FOLDER, the same as the zip's.")
    parser.add_argument("folder", metavar="FOLDER", help="the folder that holds what the zip holds")
    for option in ("out", "name", "version", "exe", "upgrade-code", "shortcut", "icon"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--repo", default=".", help="the repository the icon is in")
    return parser.parse_args(arguments)


def main(arguments):
    """Makes the MSI of a folder, for a repository that makes its zip on its own (see the heading)."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        asked = arguments_of(arguments)
        folder, repository, out = Path(asked.folder).absolute(), Path(asked.repo).absolute(), Path(asked.out).absolute()
        package = {
            "name": asked.name,
            "exe": asked.exe,
            "msi": {"upgrade_code": asked.upgrade_code, "shortcut": asked.shortcut, "icon": asked.icon},
        }
        msi_table(package)
        if not re.fullmatch(r"\d+\.\d+\.\d+", asked.version):
            fail(f"'{asked.version}' is not a version: it is three numbers, like 1.2.3")
        if not folder.is_dir():
            fail(f"{folder} is not a folder")
        files = sorted(path for path in folder.rglob("*") if path.is_file())
        contents = {path.relative_to(folder).as_posix(): path.read_bytes() for path in files}
        if asked.exe not in contents:
            fail(f"{folder} has no {asked.exe}")
        if not out.parent.is_dir():
            fail(f"{out.parent}, where the MSI goes, is not a folder")
        repo.say(f"The MSI of {asked.name} {asked.version}, from {repo.counted(len(contents), 'file')} in {folder}")
        folders = repo.part("repo_package").this_computer(repository, None, also=(folder, out.parent))
        make_msi(repository, {"package": package}, asked.version, contents, out, folders)
        repo.say(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
        return 0
    except (repo.Failure, OSError) as failure:
        repo.say(f"repo_msi.py: {failure}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
