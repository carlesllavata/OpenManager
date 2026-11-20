# SPDX-License-Identifier: GPL-3.0-or-later
"""The common OPEN3D tool of a repository: its checks, its version, its package and its release.

    python -I tools/repo.py check               the quick checks (what tools/check.ps1 starts)
    python -I tools/repo.py check --full        also the slow ones (tools/check.ps1 -Full)
    python -I tools/repo.py check --skip NAME   leaves the check NAME out and says so, one --skip for each
                                                (tools/check.ps1 -Skip NAME); a name no check has is an
                                                error, so a wrong one cannot leave nothing out
    python -I tools/repo.py version             print the version
    python -I tools/repo.py version set X.Y.Z   write a new version into every place that holds it
    python -I tools/repo.py package             the release package in dist/ (tools/repo_package.py);
                                                --checked when the quick checks were just run
    python -I tools/repo.py release X.Y.Z       the commit "Release X.Y.Z", the package and the tag, then
                                                the pushes to approve; run again, the draft of the GitHub
                                                release (tools/repo_release.py); --dry-run to try it

What is specific to the repository is in tools/repo.toml:

    [version]           only where the repository has a version of its own
      source            { file, pattern }: where the version lives; the first match is the version
      places            a list of { file, pattern }: every match must repeat the version, or one
                        number of it when the place adds part = "major", "minor" or "patch"
      after_set         commands to run once "version set" has written every place
    [[check]]           one for each check, in the order they run
      name, run, full   its name, its command as a list, and full = true when only -Full runs it
      files             names with wildcards, such as "*.cpp" or "core/*.h": the files of the
                        repository that match are added to the command
    [licence_header]
      exclude           folders whose sources need no licence line
    [private_data]
      allow             a list of { pattern, reason }: what may stay, and why
    [package]           only where the repository makes a release package
      name              the app's name: the release is "<name> X.Y.Z" and the zip is named after it
                        in lower case, <name>-X.Y.Z-windows-x64.zip
      bundle            for a 3ds Max plugin, its folder in the zip, "<Name>.bundle": the zip ends in
                        -3dsmax.zip, LICENSE goes inside it and its PackageContents.xml must say the version
      build             commands that make what goes in, in order
      files             what goes in: a file, a folder or names with wildcards ("LICENSES/*.txt") of
                        the repository, each in its own place in the zip, or { from, to } to give it
                        another; "{cargo_target}" stands for cargo's target folder
      third_party       "cargo": THIRD-PARTY-LICENSES.txt, from the libraries cargo links in
      exe               for a program, its exe in the zip: its file version must be the version
      version_answer    what "<exe> --version" must answer; "{version}" stands for the version
    [package.msi]       only for a program that has a Windows Installer package as well, made with
                        WiX 5 beside the zip as <name>-X.Y.Z-windows-x64.msi (tools/repo_msi.py)
      upgrade_code      the GUID made once for the program, never changed
      shortcut          the name of its shortcut in the Start menu
      icon              the .ico file the exe carries, for Installed apps

A pattern is a regular expression; "^" and "$" are the start and the end of a line, and a pattern
of the version has one group. The first word of a command names its program: "python" (the one
that runs this file, with -I), "3dsmax-python" (the one of 3ds Max, with -I), "3dsmaxbatch",
"ruff", "clang-format", "wix" (also found among the .NET global tools), or any other that is on
PATH or in cargo's folder.

The checks built into this file look at every file that Git tracks or would track: a new file that
is not ignored counts too. Every command starts through call(), which never pushes, never moves or
deletes a tag, never installs anything with msiexec, and on GitHub only reads, makes drafts and adds
files to them. This file and the other tools/repo_*.py are the same in every OPEN3D repository. Only
the standard library is used; it needs Python 3.11 or newer.
"""

import fnmatch
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

REPO = Path(__file__).absolute().parent.parent
SETTINGS = "tools/repo.toml"
# The tables of the settings file and the keys of each.
TABLES = {
    "version": {"source", "places", "after_set"},
    "check": {"name", "run", "full", "files"},
    "licence_header": {"exclude"},
    "private_data": {"allow"},
    "package": {"name", "bundle", "build", "files", "third_party", "exe", "version_answer", "msi"},
}
# The numbers of a version, by the name a place gives to the one it holds.
PARTS = ("major", "minor", "patch")
# The programs of 3ds Max a command may name, and where each is inside the folder of 3ds Max.
MAX_PROGRAMS = {"3dsmax-python": "Python/python.exe", "3dsmaxbatch": "3dsmaxbatch.exe"}

LICENCE_LINE = "SPDX-License-Identifier: GPL-3.0-or-later"
SOURCES = {".rs", ".py", ".ps1", ".ms", ".mcr", ".c", ".h", ".cpp", ".hpp", ".js", ".css", ".html"}
CLIPPY_LINTS = {
    "cognitive_complexity": "deny",
    "too_many_arguments": "deny",
    "wildcard_imports": "deny",
    "dbg_macro": "warn",
    "todo": "warn",
}

# A list of words that only its owner's computer has: one per line, never committed. It is looked for
# in the repository's folder and in every folder above it.
PRIVATE_LIST = "open3d-private-terms.txt"
# A folder of a Windows user, on a drive or on a network path (through localhost or any other name);
# its group is the name of the user.
USER_FOLDER = re.compile(r"(?i)(?:\b[a-z]:|\\{2,}[\w.-]+(?:\\+[\w$-]+)?)[\\/]+users[\\/]+(\w[\w.-]*)")
PLACEHOLDER_USERS = {"public", "default", "user", "username", "name", "you"}


class Failure(Exception):
    """Something the person has to put right: the settings, a missing program, a wrong argument."""


def say(text=""):
    print(text, flush=True)


def counted(number, word):
    return f"{number} {word}" + ("" if number == 1 else "s")


# -------------------------------------------------------------------------------- starting commands


def refuse_unsafe(args):
    """Stops what the common tool never runs, whoever asks for it: a push, a deleted or moved tag, a crate
    sent to crates.io, anything msiexec does (it installs and removes), and on GitHub anything but reading,
    a draft release of a tag it has, and files added."""
    words = [str(word) for word in args]
    program = Path(words[0]).stem.lower() if words else ""
    rest = words[1:]
    if program == "git":
        unsafe = "push" in rest or ("tag" in rest and not {"-d", "--delete", "-f", "--force"}.isdisjoint(rest))
    elif program == "cargo":
        unsafe = "publish" in rest
    elif program == "gh":
        unsafe = not github_reads_or_drafts(rest)
    else:
        unsafe = program == "msiexec"  # whatever it is asked, it is Windows Installer at work
    if unsafe:
        raise Failure("refused, the common tool never runs it: " + " ".join(words))


def github_reads_or_drafts(rest):
    """Whether a gh command only reads, makes a draft release of a tag GitHub already has, or adds files."""
    if any(word.startswith("--latest") or word.startswith("--draft=") for word in rest):
        return False
    if rest[:1] == ["api"]:
        # `gh api <path>` reads; every option but --jq could make it write.
        return all(not word.startswith("-") or word == "--jq" for word in rest[1:])
    if rest[:2] in (["release", "view"], ["release", "upload"]):
        return True
    return rest[:2] == ["release", "create"] and "--draft" in rest and "--verify-tag" in rest


def call(args, **options):
    """Starts a command and waits for it to end. Every command of the common tool starts here, past the guard."""
    refuse_unsafe(args)
    return subprocess.run(args, **options)  # noqa: S603 - the guard above; the commands are this tool's or tools/repo.toml's


def part(name):
    """Another file of the common tool beside this one, such as repo_package, loaded once.

    python -I keeps this folder off sys.path, so the file is loaded by its place, and Python is told
    not to leave a tools/__pycache__ behind in the repository. It finds this file as
    sys.modules["open3d_repo"].
    """
    sys.modules.setdefault("open3d_repo", sys.modules[__name__])
    key = "open3d_" + name
    if key not in sys.modules:
        path = Path(__file__).absolute().with_name(name + ".py")
        if not path.is_file():
            raise Failure(f"tools/{path.name} was not found: it comes with tools/repo.py")
        spec = importlib.util.spec_from_file_location(key, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        writes, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = writes
    return sys.modules[key]


# ---------------------------------------------------------------------------------------- settings


def load_settings(repo):
    path = repo / SETTINGS
    if not path.is_file():
        raise Failure(f"{SETTINGS} was not found")
    try:
        settings = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise Failure(f"{SETTINGS}: {error}") from error
    for table in settings:
        if table not in TABLES:
            raise Failure(f"{SETTINGS}: unknown table [{table}]")
        if isinstance(settings[table], list) != (table == "check"):
            raise Failure(f"{SETTINGS}: each check is written under [[check]], the rest under [{table}]")
        for entry in settings[table] if table == "check" else [settings[table]]:
            unknown = sorted(set(entry) - TABLES[table])
            if unknown:
                raise Failure(f"{SETTINGS}: unknown key in [{table}]: {', '.join(unknown)}")
    if "version" in settings:
        version = settings["version"]
        if set(version.get("source", {})) != {"file", "pattern"}:
            raise Failure(f"{SETTINGS}: [version] needs a source, which is a file and a pattern")
        for place in [version["source"], *version.get("places", [])]:
            if not {"file", "pattern"} <= set(place) <= {"file", "pattern", "part"}:
                raise Failure(f"{SETTINGS}: a version place is a file, a pattern and, for one number, a part")
            if place.get("part", PARTS[0]) not in PARTS:
                raise Failure(f'{SETTINGS}: the part of a version place is "major", "minor" or "patch"')
            if pattern(place["pattern"]).groups != 1:
                raise Failure(f"{SETTINGS}: the pattern {place['pattern']} needs exactly one group")
    for step in settings.get("check", []):
        if not step.get("name") or not step.get("run"):
            raise Failure(f"{SETTINGS}: a check needs a name and a run list")
    for allowed in settings.get("private_data", {}).get("allow", []):
        if not allowed.get("pattern") or not allowed.get("reason"):
            raise Failure(f"{SETTINGS}: what [private_data] allows is a pattern and the reason for it")
        pattern(allowed["pattern"])
    return settings


def pattern(text):
    try:
        return re.compile(text, re.MULTILINE)
    except re.error as error:
        raise Failure(f"{SETTINGS}: the pattern {text} is not valid: {error}") from error


def read_text(path):
    """The text of a file, with its line endings as they are."""
    return path.read_bytes().decode("utf-8")


def repo_files(repo):
    """The files of the repository that Git tracks or would track, as paths with forward slashes.

    A new file that is not ignored counts, so a problem in it is seen before it is committed.
    """
    git = shutil.which("git")
    if not git:
        raise Failure("git was not found")
    listing = [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    done = call(listing, cwd=repo, capture_output=True)
    if done.returncode != 0:
        raise Failure("git ls-files failed: " + done.stderr.decode("utf-8", errors="replace").strip())
    names = sorted(set(done.stdout.decode("utf-8").split("\0")) - {""})
    return [name for name in names if (repo / name).is_file()]


# ------------------------------------------------------------------------------------- the version


def read_version(repo, settings):
    if "version" not in settings:
        raise Failure(f"this repository has no version: {SETTINGS} has no [version]")
    source = settings["version"]["source"]
    found = pattern(source["pattern"]).search(read_text(repo / source["file"]))
    if not found:
        raise Failure(f"{source['file']}: no version found with the pattern {source['pattern']}")
    return found.group(1)


def version_step(repo, settings, _files):
    """The version in its source and in every other place that repeats it is the same."""
    version = read_version(repo, settings)
    source = settings["version"]["source"]["file"]
    places = settings["version"].get("places", [])
    problems = []
    for place in places:
        wanted = wanted_in(place, version)
        values = [found.group(1) for found in pattern(place["pattern"]).finditer(read_text(repo / place["file"]))]
        if not values:
            problems.append(f"{place['file']}: nothing matches the pattern {place['pattern']}")
        number = f" as its {place['part']} number" if "part" in place else ""
        problems += [f"{place['file']} says {v}{number}; {source} says {version}" for v in values if v != wanted]
    return problems, "" if problems else f"{version} in {counted(len(places) + 1, 'place')}"


def wanted_in(place, version):
    """What a place must hold: the version, or the one number of it that the place names."""
    if "part" not in place:
        return version
    numbers = version.split(".")
    if len(numbers) != 3:
        raise Failure(f"{place['file']} holds one number of the version, and {version} is not three numbers")
    return numbers[PARTS.index(place["part"])]


def set_version(repo, settings, version):
    """Writes the version into its source and into every other place, then runs what follows."""
    if "version" not in settings:
        raise Failure(f"this repository has no version: {SETTINGS} has no [version]")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise Failure(f"'{version}' is not a version: it is three numbers, like 1.2.3")

    def put(wanted):
        def in_its_group(found):
            whole, start = found.group(0), found.start(0)
            return whole[: found.start(1) - start] + wanted + whole[found.end(1) - start :]

        return in_its_group

    source = settings["version"]["source"]
    texts = {}
    # In the source only the first match is the version; in the other places every match is.
    for place, count in [(source, 1)] + [(place, 0) for place in settings["version"].get("places", [])]:
        path = repo / place["file"]
        text = texts[path] if path in texts else read_text(path)
        texts[path], changed = pattern(place["pattern"]).subn(put(wanted_in(place, version)), text, count=count)
        if not changed:
            raise Failure(f"{place['file']}: nothing matches the pattern {place['pattern']}; nothing was written")
    for path, text in texts.items():
        path.write_bytes(text.encode("utf-8"))
        say(f"  wrote {path.relative_to(repo).as_posix()}")
    for args in settings["version"].get("after_set", []):
        say("  > " + " ".join(args))
        if call(command(args), cwd=repo).returncode != 0:
            raise Failure(f"{args[0]} failed")
    problems, places = version_step(repo, settings, None)
    if problems:
        raise Failure("the places do not agree after writing:\n  " + "\n  ".join(problems))
    say(f"The version is {places}.")
    return 0


# ------------------------------------------------------------------------------- the built-in steps


def licence_step(repo, settings, files):
    """Every source file carries the licence line in its first lines."""
    excluded = tuple(folder.rstrip("/") + "/" for folder in settings.get("licence_header", {}).get("exclude", []))
    sources = [name for name in files if Path(name).suffix.lower() in SOURCES and not name.startswith(excluded)]
    problems = []
    for name in sources:
        with open(repo / name, encoding="utf-8", errors="replace") as file:
            head = [file.readline() for _ in range(5)]
        if not any(LICENCE_LINE in line for line in head):
            problems.append(f"{name}: no '{LICENCE_LINE}' line in its first five lines")
    return problems, counted(len(sources), "file")


def lints_step(repo, _settings, files):
    """Every Cargo.toml carries the common lints, itself or through its workspace."""
    manifests = {name: tomllib.loads(read_text(repo / name)) for name in files if Path(name).name == "Cargo.toml"}
    problems = []
    shared = False
    for name, manifest in manifests.items():
        if "lints" in manifest.get("workspace", {}):
            shared = True
            problems += missing_lints(name, manifest["workspace"]["lints"])
    for name, manifest in manifests.items():
        if "package" not in manifest:
            continue
        if manifest.get("lints", {}).get("workspace") is not True:
            problems += missing_lints(name, manifest.get("lints", {}))
        elif not shared:
            problems.append(f"{name}: takes its lints from a workspace that has none")
    return problems, f"{len(manifests)} Cargo.toml"


def missing_lints(name, lints):
    def level(value):
        return value.get("level") if isinstance(value, dict) else value

    problems = []
    if level(lints.get("rust", {}).get("unsafe_code")) not in ("forbid", "deny"):
        problems.append(f'{name}: unsafe_code must be "forbid" or "deny"')
    for lint, wanted in CLIPPY_LINTS.items():
        if level(lints.get("clippy", {}).get(lint)) != wanted:
            problems.append(f'{name}: clippy\'s {lint} must be "{wanted}"')
    return problems


def private_terms(repo):
    """The private list of this computer, if there is one: (its line number, the term in lower case)."""
    for folder in [repo, *repo.parents]:
        path = folder / PRIVATE_LIST
        if path.is_file():
            lines = enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1)
            return [(n, line.strip().lower()) for n, line in lines if line.strip() and not line.startswith("#")]
    return None


def private_step(repo, settings, files):
    """No text file holds the folder of a Windows user or a term of the private list."""
    terms = private_terms(repo)
    allowed = [pattern(entry["pattern"]) for entry in settings.get("private_data", {}).get("allow", [])]
    problems = []
    for name in files:
        data = (repo / name).read_bytes()
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = data.decode("utf-16", errors="replace")
        elif b"\0" in data:
            continue  # not a text file
        else:
            text = data.decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            excused = [found.span() for allow in allowed for found in allow.finditer(line)]
            for start, end, what in private_in_line(line, terms or []):
                if not any(a < end and start < b for a, b in excused):
                    problems.append(f"{name}:{number}: {what}")
    listed = "no private list on this computer" if terms is None else counted(len(terms), "private term")
    return problems, f"{counted(len(files), 'file')}, {listed}"


def private_in_line(line, terms):
    """What a line holds that belongs to one computer: (start, end, what it is)."""
    found = []
    for user in USER_FOLDER.finditer(line):
        if user.group(1).lower() not in PLACEHOLDER_USERS:
            found.append((user.start(), user.end(), "the folder of a Windows user"))
    lowered = line.lower()
    for number, term in terms:
        start = lowered.find(term)
        while start >= 0:
            found.append((start, start + len(term), f"term {number} of {PRIVATE_LIST}"))
            start = lowered.find(term, start + 1)
    return found


# -------------------------------------------------------------------------------------- the checks


def command(args):
    """The command to start: its program, given by name, is looked for on this computer."""
    name, rest = args[0], list(args[1:])
    if name == "python":
        return [sys.executable, "-I", *rest]
    if name in MAX_PROGRAMS:
        return [max_program(name), *(["-I"] if name == "3dsmax-python" else []), *rest]
    cargo_bin = Path(os.environ.get("CARGO_HOME") or Path.home() / ".cargo") / "bin"
    found = shutil.which(name) or shutil.which(name, path=str(cargo_bin))
    if found:
        return [found, *rest]
    if name == "ruff" and importlib.util.find_spec("ruff"):
        return [sys.executable, "-I", "-m", "ruff", *rest]
    if name == "clang-format" and (found := visual_studio_clang_format()):
        return [found, *rest]
    if name == "wix" and (found := dotnet_tool("wix")):
        return [found, *rest]
    elsewhere = {
        "ruff": " and not in this Python",
        "clang-format": " and Visual Studio has none",
        "wix": " nor among the .NET global tools (dotnet tool install --global wix --version 5.0.2)",
    }
    raise Failure(f"{name} was not found: it is not on PATH" + elsewhere.get(name, ""))


def dotnet_tool(name):
    """A .NET global tool, where `dotnet tool install --global` puts it; None without one."""
    home = Path(os.environ.get("DOTNET_CLI_HOME") or Path.home())
    program = home / ".dotnet" / "tools" / (name + ".exe")
    return str(program) if program.is_file() else None


def max_program(name):
    """A program of 3ds Max, in the folder its installer names in ADSK_3DSMAX_x64_<year>; the newest year."""
    folders = {}
    for variable, folder in os.environ.items():
        year = re.fullmatch(r"(?i)ADSK_3DSMAX_x64_(\d{4})", variable)
        if year and folder:
            folders[int(year.group(1))] = folder
    if not folders:
        raise Failure(f"{name} was not found: no ADSK_3DSMAX_x64_<year> variable says where 3ds Max is")
    program = Path(folders[max(folders)]) / MAX_PROGRAMS[name]
    if not program.is_file():
        raise Failure(f"{name} was not found: the folder of 3ds Max {max(folders)} has no {MAX_PROGRAMS[name]}")
    return str(program)


def visual_studio_clang_format():
    """The clang-format that comes with Visual Studio, which its own vswhere.exe finds; None without one."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    asked = [str(vswhere), "-utf8", "-products", "*", "-property", "installationPath"]
    done = call(asked, capture_output=True)
    for folder in done.stdout.decode("utf-8", errors="replace").splitlines():
        for inside in ("VC/Tools/Llvm/x64/bin", "VC/Tools/Llvm/bin"):
            program = Path(folder.strip()) / inside / "clang-format.exe"
            if folder.strip() and program.is_file():
                return str(program)
    return None


def run_step(repo, step, files):
    """Runs the command of a check in the repository's folder; its output is shown if it fails.

    Where the check names `files`, the files of the repository that match are added to the command.
    """
    args, note = list(step["run"]), ""
    if "files" in step:
        chosen = [name for name in files if any(fnmatch.fnmatchcase(name, wanted) for wanted in step["files"])]
        if not chosen:
            return [], "no files"
        args, note = args + chosen, counted(len(chosen), "file")
    try:
        real = command(args)
    except Failure as failure:
        return [str(failure)], ""
    try:
        done = call(real, cwd=repo, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Failure as failure:
        return [str(failure)], note
    if done.returncode == 0:
        return [], note
    return done.stdout.decode("utf-8", errors="replace").splitlines() or [f"exit code {done.returncode}"], note


def check(repo, settings, full, skip=()):
    """Runs every step, the built-in ones first, and says how each went. Returns 0 when all passed.

    The steps named in `skip` are left out, each with a line that says so; a name that no step has is
    a Failure, raised before any step runs.
    """
    files = repo_files(repo)
    built_in = [("version", version_step)] if "version" in settings else []
    built_in.append(("licence header", licence_step))
    if "Cargo.toml" in files:
        built_in.append(("common lints", lints_step))
    built_in.append(("private data", private_step))
    steps = [(name, False, lambda step=step: step(repo, settings, files)) for name, step in built_in]
    for listed in settings.get("check", []):
        steps.append((listed["name"], listed.get("full", False), lambda listed=listed: run_step(repo, listed, files)))
    names = [name for name, _, _ in steps]
    unknown = [name for name in dict.fromkeys(skip) if name not in names]
    if unknown:
        asked = ", ".join(f'"{name}"' for name in unknown)
        raise Failure(f"-Skip names no check of this repository: {asked}. The checks are: {', '.join(names)}")

    # Which Python runs the checks: on GitHub several are installed, and the tests must run on the one asked for.
    say(f"Checking {repo.name}" + (" (with -Full)" if full else "") + f", with Python {sys.version.split()[0]}")
    failed, skipped, left_out = [], 0, []
    for name, slow, step in steps:
        if name in skip:
            say(f"  skip  {name} (asked for with -Skip)")
            left_out.append(name)
            continue
        if slow and not full:
            say(f"  skip  {name} (only with -Full)")
            skipped += 1
            continue
        if sys.stdout.isatty():
            print(f"  ....  {name}", end="\r", flush=True)
        started = time.monotonic()
        try:
            problems, note = step()
        except (Failure, OSError, ValueError) as failure:
            problems, note = [str(failure)], ""
        seconds = time.monotonic() - started
        details = ", ".join(part for part in (note, f"{seconds:.0f} s" if seconds >= 1 else "") if part)
        say(f"  {'FAIL' if problems else 'ok  '}  {name}" + (f" ({details})" if details else ""))
        for problem in problems:
            say(f"        {problem}")
        if problems:
            failed.append(name)

    ran = len(steps) - skipped - len(left_out)
    left = f" {len(left_out)} left out as asked: {', '.join(left_out)}." if left_out else ""
    left += f" {skipped} more only with -Full." if skipped else ""
    if failed:
        say(f"\n{len(failed)} of {ran} checks FAILED: {', '.join(failed)}.{left}")
        return 1
    say(f"\nAll {ran} checks passed.{left}")
    return 0


def package_settings(repo):
    """The settings of a repository that makes a release package; it is said plainly when it makes none."""
    settings = load_settings(repo)
    if "package" not in settings:
        raise Failure(f"this repository makes no release package: {SETTINGS} has no [package]")
    return settings


def check_arguments(arguments):
    """What follows "check": (full, the names to skip), or None when it is not --full and --skip NAME."""
    full, skip, rest = False, [], list(arguments)
    while rest:
        word = rest.pop(0)
        if word == "--full" and not full:
            full = True
        elif word == "--skip" and rest:
            skip.append(rest.pop(0))
        else:
            return None
    return full, skip


def main(arguments):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    try:
        asked = check_arguments(arguments[1:]) if arguments[:1] == ["check"] else None
        if asked:
            full, skip = asked
            return check(REPO, load_settings(REPO), full=full, skip=skip)
        if arguments == ["version"]:
            say(read_version(REPO, load_settings(REPO)))
            return 0
        if len(arguments) == 3 and arguments[:2] == ["version", "set"]:
            return set_version(REPO, load_settings(REPO), arguments[2])
        if arguments in (["package"], ["package", "--checked"]):
            settings = package_settings(REPO)
            return part("repo_package").main(REPO, settings, checked=len(arguments) == 2)
        versions = [argument for argument in arguments[1:] if argument != "--dry-run"]
        if arguments[:1] == ["release"] and len(versions) == 1 and len(arguments) <= 3 and versions[0][:1] != "-":
            settings = package_settings(REPO)
            return part("repo_release").main(REPO, settings, versions[0], dry_run="--dry-run" in arguments)
    except (Failure, OSError) as failure:
        say(f"repo.py: {failure}")
        return 2
    say(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
