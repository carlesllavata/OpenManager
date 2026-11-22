# OpenManager

Scene setups and batch render inside 3ds Max 2025 and later: a setup keeps the camera, lights, layers,
render settings and more of a `.max` file, and a click applies it. Python (PySide6, pymxs) and MAXScript.

This file holds facts about this repo only, each one checkable in the code. Update it in the same commit
as a change that makes it old.

## Layout

- `package/OpenManager/openmanager/`: the Python package. `window.py`: the window. `cards.py`, `cards2.py`:
  the cards. `maxlink.py`: the link to 3ds Max. `model.py`: the setups and the checks on what a file
  brings. `grid.py`: the card grid. `folders.py`: where OpenManager keeps its files, and the copy of the old
  ones. `open3d_settings.py`: what every Open3D app shares (the language and the folders), a copy of a common
  file. `model.py`, `grid.py`, `folders.py` and `open3d_settings.py` import neither 3ds Max nor Qt when they load.
- `package/OpenManager/omgr_core.ms`: the MAXScript functions that read and change the scene.
- `bundle/OpenManager_bundle.ms`: what the bundle runs when 3ds Max starts. `package/OpenManager.mcr`: the
  action that opens the window. The `.mzp` is retired (D-046): `omgr_setup.ms` removes a copy it left.
- `tools/build.py`: the build. `tools/make_props.py` writes `props.json`, the properties the cards set.

## Build and check

- Build: `python -I tools/build.py` writes `dist/OpenManager.bundle`.
- Checks: `tools\check.ps1` runs them all; it needs Python 3.11 or newer and the ruff `ruff.toml` names.
  First the steps built into `tools/repo.py`: the version agrees in `window.py` and the README, every
  source has its licence line, no file holds a path of somebody's computer. Then those of `tools/repo.toml`:
  `ruff format --check .`, `ruff check .` and `python -I tests/run.py` (271 tests; `tests/fake_max.py`
  stands in for 3ds Max and points the folders at a temporary one). Without PySide6 the tests of
  `test_window.py` and `test_dialogs.py` are skipped.
- `tools\check.ps1 -Full` also runs the tests with the Python of 3ds Max, which has PySide6: none is skipped.
- Only `ruff check .` fails today: 35 findings on the 28 broad `except Exception` blocks of the package.
- CI: `.github/workflows/check.yml` runs `tools\check.ps1 -Skip "ruff check"`, without `-Full`, on every
  push and pull request to `main`, on GitHub's Windows runner, once with Python 3.11 and once with 3.13.
  It leaves out `ruff check` because of those blocks; the `-Skip` goes once they are put right.
- `.editorconfig`, `.gitattributes`, `ruff.toml`, `LICENSE`, `tools/check.ps1`, `tools/repo.py`,
  `tools/repo_package.py`, `tools/repo_release.py` and `tools/repo_msi.py` are the same in every Open3D
  repo, and `openmanager/open3d_settings.py` in every repo that has it. Do not change them here.

## Version and release

- The version is `VERSION` in `openmanager/window.py` and nowhere else by hand, except the `(vX.Y.Z)`
  status line of the README and the CHANGELOG. `python -I tools/repo.py version set X.Y.Z` writes it
  into `window.py` and the README; the build refuses to go on if the README disagrees.
- Changes a user can notice go into `CHANGELOG.md` under `## In development`, in the same commit.
- The build writes the bundle's `PackageContents.xml`. `PRODUCT_CODE` and `UPGRADE_CODE` never change.
- `python -I tools/repo.py package` makes the release package as the `[package]` table of
  `tools/repo.toml` says: it needs the version's `## X.Y.Z` section in `CHANGELOG.md`, runs the quick
  checks and `tools/build.py`, and writes `dist/openmanager-<version>-windows-x64-3dsmax.zip`, with
  `dist/OpenManager.bundle` at its root (never `__pycache__`) and `LICENSE` inside the bundle, and
  `dist/SHA256SUMS.txt`. It refuses a bundle whose `AppVersion` is not the version. While `ruff check .`
  fails it stops at the checks; `--checked` skips them.
- `python -I tools/repo.py release X.Y.Z` turns `## In development` into `## X.Y.Z — <date>`, sets the
  version, commits `Release X.Y.Z`, packages, tags `vX.Y.Z` and prints the pushes to approve; run again
  once they are done, it makes the GitHub release as a draft, with the zip and `SHA256SUMS.txt`. It never
  pushes. `--dry-run` tries it all and writes only to `dist/`. It runs the quick checks with no way to
  skip them, so it stops there while `ruff check .` fails.
- The Open3D launcher installs `OpenManager.bundle`; by hand it is copied into ApplicationPlugins. The bundle
  removes an install of the retired `.mzp` when it starts.

## Rules of this code

- Every MAXScript global starts with `omgr_`. A script that uses globals from another file declares them
  `global` before its `( )` block, where an unknown name would become a local.
- The `.ms` and `.mcr` files start with a UTF-8 BOM and are indented with 4 spaces.
- Setups are stored inside the `.max` file: JSON in the `OpenManager_Dat` attribute of `rootNode`, whose id
  never changes. The old keys (`PuzlesSM_Dat`, `PuzlesSM_Maps`, Pulze's `SceneManager_Dat`) are still read.
- Its files (`folders.py`): the settings, the trusted scripts among them, in `%APPDATA%\Open3D\OpenManager`
  (`OpenManager.json`, `OpenManager_default.json`, `OpenManager_notify.txt`), one set for every 3ds Max; the
  HDRI previews (`OpenManager_hdri`) and what a scene not saved yet makes in `%LOCALAPPDATA%\Open3D\OpenManager`.
  `OPEN3D_SETTINGS_DIR` and `OPEN3D_DATA_DIR` move them. `folders.session()`, run by `OpenManager_startup.ms`
  when 3ds Max starts and by the window, copies into a missing new folder the settings and HDRI previews of
  the newest 3ds Max with OpenManager settings in a `plugcfg` under `%LOCALAPPDATA%\Autodesk\3dsMax` (or the
  running one's), and leaves the old folders as they were; a failed copy leaves that session on the old
  folder. MAXScript finds the settings in `omgr_settingsDir`. `OPENMANAGER_TEST_OLD_FOLDERS` is for tests.
- A change is a tuple that starts with its kind: `maxlink._run_one` applies it, `model.action_key` says
  what it controls and `maxlink.capture` reads the value to put back. A new kind needs its part in each.
- 3ds Max's undo is off while changes are applied (`maxlink.run`); the window keeps its own undo records.
- A class name that arrives in a setup is validated (`model.is_class_name`) and looked up, never evaluated.
- A setup or the stored base state sets only the properties the cards set (`model.prop_refusal`) and never
  one that holds code. A renderer setting may be any plain name, but not a path into another object.
- Scripts and render presets that came with a file run or load only once trusted (`window.script_allowed`):
  after a yes to the review question, where Enter refuses, or when the setting says always.
- `maxlink.load_preset` is the one place that loads a preset; it leaves Render Setup's scripts as they were.
- `tests/test_code_sites.py` lists every place where text becomes code; a new one fails it.
- The interface is in English only.

## Traps

- 3ds Max 2027 ignores a bundle without `SeriesMax`; the build writes 2099.
- 3ds Max forgets a map nothing points to, so the setups' environment maps are kept in `OpenManager_Maps`.
- Qt makes a button the default of a dialog only if told so once it is inside it (`ScriptReviewDialog`).
