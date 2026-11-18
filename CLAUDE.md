# OpenManager

Scene setups and batch render inside 3ds Max 2025 and later: a setup keeps the camera, lights, layers,
render settings and more of a `.max` file, and a click applies it. Python (PySide6, pymxs) and MAXScript.

This file holds facts about this repo only, each one checkable in the code. Update it in the same commit
as a change that makes it old.

## Layout

- `package/OpenManager/openmanager/`: the Python package. `window.py`: the window. `cards.py`, `cards2.py`:
  the cards. `maxlink.py`: the link to 3ds Max. `model.py`: the setups and the checks on what a file
  brings. `grid.py`: the card grid. `model.py` and `grid.py` import neither 3ds Max nor Qt.
- `package/OpenManager/omgr_core.ms`: the MAXScript functions that read and change the scene.
- `bundle/OpenManager_bundle.ms`: what the bundle runs when 3ds Max starts. `package/OpenManager.mcr`: the
  action that opens the window. `package/install.ms` and `uninstall.ms`: the `.mzp` install and its removal.
- `tools/build.py`: the build. `tools/make_props.py` writes `props.json`, the properties the cards set.

## Build and check

- Build: `python -I tools/build.py` writes `dist/OpenManager.bundle` and `dist/OpenManager.mzp`.
- Checks:
  - `python -I tests/run.py` (207 tests; `tests/fake_max.py` stands in for 3ds Max). Without PySide6, which
    the Python of 3ds Max has, the tests of `test_window.py` and `test_dialogs.py` are skipped.
  - `ruff format --check .` and `ruff check .`
- `ruff check .` fails today, on the 58 broad `except Exception` blocks of the package (77 findings).
- `.editorconfig`, `.gitattributes` and `ruff.toml` are the same in every Open3D repo. Do not change them.

## Version and release

- The version is `VERSION` in `openmanager/window.py` and nowhere else by hand, except the `(vX.Y.Z)`
  status line of the README and the CHANGELOG. The build refuses to go on if the README disagrees.
- Changes a user can notice go into `CHANGELOG.md` under `## In development`, in the same commit.
- The build writes the bundle's `PackageContents.xml`. `PRODUCT_CODE` and `UPGRADE_CODE` never change.
- The Open3D launcher installs `OpenManager.bundle`; the `.mzp` is the install by hand. `install.ms`
  refuses to install over the bundle, and the bundle removes an `.mzp` install when it starts.

## Rules of this code

- Every MAXScript global starts with `omgr_`. A script that uses globals from another file declares them
  `global` before its `( )` block, where an unknown name would become a local.
- The `.ms` and `.mcr` files start with a UTF-8 BOM and are indented with 4 spaces.
- Setups are stored inside the `.max` file: JSON in the `OpenManager_Dat` attribute of `rootNode`, whose id
  never changes. The old keys (`PuzlesSM_Dat`, `PuzlesSM_Maps`, Pulze's `SceneManager_Dat`) are still read.
- The settings of the person, the trusted scripts among them, are in 3ds Max's `plugcfg` folder.
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

- A `version` line in `mzp.run` must be a plain number: otherwise 3ds Max refuses the `.mzp` without a word.
- 3ds Max 2027 ignores a bundle without `SeriesMax`; the build writes 2099.
- 3ds Max forgets a map nothing points to, so the setups' environment maps are kept in `OpenManager_Maps`.
- Qt makes a button the default of a dialog only if told so once it is inside it (`ScriptReviewDialog`).
