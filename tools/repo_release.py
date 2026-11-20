# SPDX-License-Identifier: GPL-3.0-or-later
"""The release of an OPEN3D repository: python -I tools/repo.py release X.Y.Z [--dry-run].

A part of the common tool: tools/repo.py loads it. It does everything that stays on this computer and
stops; it never pushes, and on GitHub it only makes a draft, which the owner publishes. Run again once
origin has the commit and the tag, it goes on from there:

1. It stops on changes that are not committed, on a branch that is not main, and on a tag vX.Y.Z that
   is not an annotated tag on this commit, here or on origin (read with git ls-remote).
2. If the version is not X.Y.Z yet, or CHANGELOG.md still has "## In development": it writes the
   version ("version set"), turns "## In development" into "## X.Y.Z — <today>", dated the way the
   CHANGELOG's last heading is, and commits "Release X.Y.Z". Without that section it stops.
3. The package (tools/repo_package.py), from that commit.
4. The annotated tag vX.Y.Z on that commit.
5. It prints the pushes to approve, `git push origin main` and `git push origin vX.Y.Z`, and stops.
6. Run again with both on origin: the package again, from the tagged commit, and a draft of the
   release vX.Y.Z of origin's GitHub repository, titled "<name> X.Y.Z", with that version's section of
   CHANGELOG.md as its notes and the zip, the MSI of a program that has one, and SHA256SUMS.txt as its
   files. A draft that is already there gets the files again; a published release stops it, untouched.

--dry-run writes nothing outside dist/ and runs nothing that writes to Git or GitHub. What the commit
would change is made in a copy of the repository inside dist/, and the package of that copy is left in
dist/: the checks run on the repository itself.
"""

import collections
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

repo = sys.modules["open3d_repo"]  # tools/repo.py, which loads this file
packager = repo.part("repo_package")

REMOTE = "origin"
BRANCH = "main"
CHANGELOG = packager.CHANGELOG
IN_DEVELOPMENT = re.compile(r"^## In development\b[^\r\n]*", re.MULTILINE)
VERSION_HEADING = re.compile(r"^## \d+\.\d+\.\d+\b([^\r\n]*)", re.MULTILINE)
MONTHS = "January February March April May June July August September October November December".split()
# The ways a heading of the CHANGELOG dates its version: 2026-11-16, or 16 November 2026.
DATES = (
    (r"\d{4}-\d{2}-\d{2}", lambda day: day.isoformat()),
    (r"\d{1,2} [A-Z][a-z]+ \d{4}", lambda day: f"{day.day} {MONTHS[day.month - 1]} {day.year}"),
)
GITHUB = re.compile(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/*$", re.IGNORECASE)

# A tag as this folder has it. `kind` is "tag" only for an annotated tag; a lightweight one is the commit.
Tag = collections.namedtuple("Tag", "object kind commit")


def fail(text):
    raise repo.Failure(text)


# ------------------------------------------------------------------------------------------- git


def git(folder, *args):
    """What git prints; it stops when git fails."""
    done = repo.call(["git", *args], cwd=folder, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        fail(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def local_tag(folder, tag):
    """The tag of this folder as a Tag, or None when it has none."""
    fields = git(folder, "for-each-ref", "--format=%(objectname) %(objecttype) %(*objectname)", "refs/tags/" + tag)
    fields = fields.split()
    return Tag(fields[0], fields[1], fields[2] if len(fields) > 2 else fields[0]) if fields else None


def remote_refs(folder, tag):
    """What origin has as main and as the tag, as {ref: object}. It only reads."""
    refs = {}
    for line in git(folder, "ls-remote", REMOTE, "refs/heads/" + BRANCH, "refs/tags/" + tag).splitlines():
        sha, _, ref = line.partition("\t")
        if ref:
            refs[ref.strip()] = sha.strip()
    return refs


def has_commit(folder, there, commit):
    """Whether origin's main (at `there`) has the commit: it is there, or a later commit this folder knows."""
    if not there:
        return False
    asked = ["git", "merge-base", "--is-ancestor", commit, there]
    return there == commit or repo.call(asked, cwd=folder, capture_output=True).returncode == 0


def check_tags(tag, local, there, head):
    """Stops unless the tag is missing everywhere, or is the same annotated tag on this commit."""
    if local and local.kind != "tag":
        fail(f"the tag {tag} is here and is not an annotated tag: this tool never replaces a tag")
    if local and local.commit != head:
        fail(
            f"the tag {tag} is here on {local.commit[:8]}, not on this commit ({head[:8]}): this tool never moves a tag"
        )
    if there and not local:
        fail(f"{REMOTE} has a tag {tag} and this folder has none: fetch it and look at it first")
    if there and there != local.object:
        fail(f"{REMOTE} has a tag {tag} that is not the one here")


# ------------------------------------------------------------------------------------- CHANGELOG


def section_body(text, start):
    """The text from `start` to the next heading of a version."""
    following = re.search(r"^## ", text[start:], re.MULTILINE)
    return text[start : start + following.start()] if following else text[start:]


def dated(after, today):
    """What follows the version in its heading: the last heading's separator and date, with today's date."""
    if after is None:
        return " — " + DATES[1][1](today)
    for form, write in DATES:
        found = re.fullmatch(rf"(\W*){form}(\W*)", after)
        if found:
            return found.group(1) + write(today) + found.group(2)
    return "" if not after.strip() else " — " + DATES[1][1](today)


def released_changelog(text, version, today):
    """The CHANGELOG with "## In development" turned into the heading of the version."""
    found = IN_DEVELOPMENT.search(text)
    if not found:
        fail(f'{CHANGELOG} has no "## In development" section: write under it what changed in {version} first')
    if packager.heading(version).search(text):
        fail(f'{CHANGELOG} already has a "## {version}" section and still has "## In development"')
    if not section_body(text, found.end()).strip():
        fail(f'the "## In development" section of {CHANGELOG} is empty: write in it what changed in {version}')
    last = VERSION_HEADING.search(text)
    heading = f"## {version}" + dated(last.group(1) if last else None, today)
    return text[: found.start()] + heading + text[found.end() :]


def notes(text, version):
    """The section of the version, without its heading: the notes of the release."""
    found = packager.heading(version).search(text)
    body = section_body(text, found.end()).strip() if found else ""
    if not body:
        fail(f'{CHANGELOG} has nothing under "## {version}" to say in the release')
    return body.replace("\r\n", "\n")


def needs_commit(folder, settings, version, today):
    """Whether the version or the CHANGELOG still has to become the release's. It stops, before anything is
    written, when the CHANGELOG has nothing to release."""
    text = repo.read_text(folder / CHANGELOG)
    if repo.read_version(folder, settings) != version or IN_DEVELOPMENT.search(text):
        released_changelog(text, version, today)
        return True
    if not packager.heading(version).search(text):
        fail(f'{CHANGELOG} has neither a "## {version}" nor a "## In development" section')
    return False


def write_release(folder, settings, version, today):
    """Writes the version and the release's CHANGELOG into the folder: the repository, or a copy of it."""
    path = folder / CHANGELOG
    released_changelog(repo.read_text(path), version, today)  # it stops here, before anything is written
    if repo.read_version(folder, settings) != version:
        repo.set_version(folder, settings, version)
    path.write_bytes(released_changelog(repo.read_text(path), version, today).encode("utf-8"))
    repo.say(f"  wrote {CHANGELOG}")


def commit_release(folder, version):
    """Commits, file by file, what write_release changed. Returns the commit."""
    changed = [name for name in git(folder, "diff", "--name-only", "-z").split("\0") if name]
    git(folder, "add", "--", *changed)
    git(folder, "commit", "--quiet", "-m", f"Release {version}")
    return git(folder, "rev-parse", "HEAD")


def package_in_a_copy(folder, settings, version, today):
    """The dry run of the commit: the release's version and CHANGELOG in a copy of the repository, inside
    dist/, and the package of that copy, which stays in dist/. The checks run on the repository itself,
    and cargo builds the copy where it builds the repository, so it does not start from nothing."""
    files = repo.repo_files(folder)
    if repo.check(folder, settings, full=False) != 0:
        fail("the checks failed: put them right first (tools\\check.ps1 shows them again)")
    cargo = any(args[0] == "cargo" for args in packager.table(settings).get("build", []))
    target = packager.cargo_target(folder) if cargo else None
    dist = folder / packager.DIST
    dist.mkdir(exist_ok=True)
    copy = Path(tempfile.mkdtemp(prefix=f"release-{version}-", dir=dist))
    try:
        for name in files:
            (copy / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder / name, copy / name)
        repo.say(f"  [dry run] what the commit would change, in a copy: {copy.relative_to(folder).as_posix()}")
        write_release(copy, settings, version, today)
        return packager.make_package(copy, settings, checked=True, files=files, out=dist, also=[folder], target=target)
    finally:
        shutil.rmtree(copy, ignore_errors=True)


# ---------------------------------------------------------------------------------------- GitHub


def gh_program():
    found = shutil.which("gh")
    installed = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHubCLI" / "bin" / "gh.exe"
    if found or installed.is_file():
        return found or str(installed)
    fail("gh, GitHub's command line, was not found: https://cli.github.com")


def github_repo(folder):
    """The GitHub repository origin is, as owner/name."""
    url = git(folder, "remote", "get-url", REMOTE)
    found = GITHUB.search(url)
    if not found:
        fail(f"{REMOTE} is not a repository on GitHub ({url}): there is no GitHub release to make")
    return f"{found.group(1)}/{found.group(2)}"


def release_state(gh, github, tag):
    """The release of the tag as {"isDraft": ..., "url": ...}, or None when there is none. It only reads.

    GitHub is asked first for the release of the tag, which it only gives when it is published. Only
    without one does `gh release view` look for a draft: asked alone, it could answer with a draft that
    shares its tag with a published release."""
    done = repo.call(
        [gh, "api", f"repos/{github}/releases/tags/{tag}", "--jq", ".html_url"], capture_output=True, text=True
    )
    if done.returncode == 0:
        return {"isDraft": False, "url": done.stdout.strip()}
    if "HTTP 404" in (done.stderr or ""):
        done = repo.call(
            [gh, "release", "view", tag, "--repo", github, "--json", "isDraft,url"], capture_output=True, text=True
        )
        if done.returncode == 0:
            return json.loads(done.stdout)
        if "release not found" in (done.stderr or ""):
            return None
    fail(f"the release {tag} of {github} could not be read: {(done.stderr or '').strip()}")


def release_step(github, tag, state):
    """ "create" a draft where there is no release, "upload" the files again to a draft; a published one stops it."""
    if state is None:
        return "create"
    if state.get("isDraft") is True:
        return "upload"
    fail(f"the release {tag} of {github} is published: this tool never changes a published release")


def draft_release(gh, github, tag, title, text, files, step):
    """The draft release of the tag with the files in it. Returns its link."""
    url = None
    if step == "create":
        with tempfile.TemporaryDirectory(prefix="open3d-notes-") as folder:
            notes_file = Path(folder) / "notes.md"
            notes_file.write_text(text + "\n", encoding="utf-8")
            create = [gh, "release", "create", tag, "--repo", github, "--draft", "--verify-tag", "--title", title]
            done = repo.call([*create, "--notes-file", str(notes_file)], capture_output=True, text=True)
        if done.returncode != 0:
            fail(f"gh release create failed: {done.stderr.strip()}")
        url = done.stdout.strip()
        repo.say(f"  the draft release {tag} is made on {github}")
    upload = [gh, "release", "upload", tag, *[str(file) for file in files], "--repo", github, "--clobber"]
    done = repo.call(upload, capture_output=True, text=True)
    if done.returncode != 0:
        fail(f"gh release upload failed: {done.stderr.strip()}")
    return url


# --------------------------------------------------------------------------------------- release


def pushes_needed(branch_there, tag, tag_there):
    """The pushes the owner runs, one by one: the branch, and the tag by its name, never --tags."""
    pushes = [] if branch_there else [f"git push {REMOTE} {BRANCH}"]
    return pushes + ([] if tag_there else [f"git push {REMOTE} {tag}"])


def release(folder, settings, version, dry_run=False, today=None):
    """Does the next steps of the release that this computer can do; see the heading of this file."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"'{version}' is not a version: it is three numbers, like 1.2.3")
    name, tag = packager.table(settings)["name"], "v" + version
    repo.say(f"Release {name} {version}" + (" (dry run: nothing is committed, tagged or uploaded)" if dry_run else ""))

    # 1. What there is, here and on origin.
    changes = git(folder, "status", "--porcelain")
    if changes:
        fail(f"there are changes that are not committed; commit them or put them aside first:\n{changes}")
    on_branch = repo.call(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=folder, capture_output=True, text=True
    )
    if on_branch.returncode != 0 or on_branch.stdout.strip() != BRANCH:
        fail(f"a release is made on {BRANCH}, and this folder is on {on_branch.stdout.strip() or 'no branch'}")
    head = git(folder, "rev-parse", "HEAD")
    local = local_tag(folder, tag)
    remote = remote_refs(folder, tag)
    there = remote.get("refs/tags/" + tag)
    check_tags(tag, local, there, head)

    new_commit, packaged = False, False
    if local is None:
        # 2 to 4: the commit "Release X.Y.Z", the package and the tag.
        today = today or datetime.date.today()
        if needs_commit(folder, settings, version, today):
            if dry_run:
                new_commit = True
                package_in_a_copy(folder, settings, version, today)
            else:
                write_release(folder, settings, version, today)
                head = commit_release(folder, version)
                repo.say(f'  committed "Release {version}" ({head[:8]})')
        if not new_commit:
            packager.make_package(folder, settings)
        packaged = True
        if dry_run:
            on = f'the commit "Release {version}"' if new_commit else head[:8]
            repo.say(f"  [dry run] the annotated tag {tag} would go on {on}")
        else:
            git(folder, "tag", "-a", tag, "-m", f"{name} {version}")
            repo.say(f"  the annotated tag {tag} is on {head[:8]}")
    elif repo.read_version(folder, settings) != version:
        fail(f"the tag {tag} is on this commit, whose version is {repo.read_version(folder, settings)}")
    else:
        repo.say(f"  the tag {tag} is already on this commit ({head[:8]})")

    # 5. What origin still lacks: the owner pushes it.
    branch_there = not new_commit and has_commit(folder, remote.get("refs/heads/" + BRANCH), head)
    pushes = pushes_needed(branch_there, tag, bool(there))
    if pushes:
        if dry_run:
            repo.say("Dry run: nothing was committed or tagged. A real run would stop here for these pushes:")
        else:
            built = f", and its package is in {packager.DIST}/" if packaged else ""
            repo.say(f"Ready here: {name} {version} is tagged {tag} on {head[:8]}{built}.")
            repo.say(f"Nothing was pushed: this tool never pushes. With the owner's OK, run in {folder}:")
        repo.say("\n".join("    " + push for push in pushes))
        repo.say(
            f'and then "python -I tools/repo.py release {version}" again: it makes the draft of the GitHub release.'
        )
        return 0

    # 6. The draft of the GitHub release, from the tagged commit.
    github = github_repo(folder)
    archive = packager.make_package(folder, settings)
    files = packager.release_files(packager.table(settings), version, archive.parent)
    gh = gh_program()
    state = release_state(gh, github, tag)
    step = release_step(github, tag, state)
    text = notes(repo.read_text(folder / CHANGELOG), version)
    if dry_run:
        what = "make the draft release" if step == "create" else "put the files again into the draft release"
        repo.say(f"Dry run: nothing was uploaded. A real run would {what} {tag} of {github}, with")
        repo.say("\n".join(f"    {file.name}" for file in files))
        return 0
    url = draft_release(gh, github, tag, f"{name} {version}", text, files, step) or (state or {}).get("url")
    repo.say(f"  {' and '.join(file.name for file in files)} are in the draft release {tag} of {github}")
    repo.say("It is a DRAFT: nobody sees it until the owner publishes it on GitHub.")
    repo.say(f"  {url or f'https://github.com/{github}/releases'}")
    return 0


def main(folder, settings, version, dry_run=False):
    return release(folder, settings, version, dry_run)
