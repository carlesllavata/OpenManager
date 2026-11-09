# OpenManager – notes for Claude

Open-source scene setups / batch render manager for 3ds Max (2025+). The user's environment: 3ds Max 2027,
Python 3.13 (bundled with Max), PySide6, Corona 14 and V-Ray. The repo lives on a NAS share (`Z:` maps to
`\\192.168.2.10\...`). Talk to the user in Spanish. The app, code, comments, commit messages, README and GitHub
texts are in English, as in Open3DS; only `CHANGELOG.md` (the diary) and release notes are in Spanish.

## Scope decisions
- Name: OpenManager. No accounts, licensing or login: install and use.
- Renderers: Corona and V-Ray first-class; FStorm best effort; no Redshift.
- Pulze Scene Manager setups are imported (`SceneManager_Dat`). Setups of the previous version of this tool
  (`PuzlesSM_Dat` / `PuzlesSM_Maps`, mix maps `PZSM_EnvMix_*`) are read and moved to `OpenManager_Dat` /
  `OpenManager_Maps` on save. Keep those legacy keys working.
- The tool's history before OpenManager is not credited to anyone: no author names of earlier versions in the repo.

## Layout
- `package/` – what the `.mzp` contains: `install.ms`, `mzp.run`, `OpenManager.mcr` (category/macro "OpenManager"),
  `OpenManager/omgr_core.ms` (MAXScript, every global prefixed `omgr_`, callback ids `#omgr`, `#omgrRender`,
  `#omgrStartup`), `OpenManager/OpenManager_startup.ms`, `OpenManager/openmanager/` (Python package).
- Installed to `getDir #userScripts\OpenManager\`; settings in `plugcfg\OpenManager*.json`.
- Version lives in `openmanager/window.py` (`VERSION`) **and** `package/mzp.run`; keep them equal.
- `openmanager/model.py` and `grid.py` have no Max/Qt imports: keep them testable outside Max.
- `tools/build.py` draws the icons and writes `dist/OpenManager.mzp`; `tools/make_props.py` regenerates `props.json`.
- Custom attribute IDs: data `#(0x4f4d4752, 0x5f446174)`, maps `#(0x4f4d4752, 0x5f4d6170)`. Never reuse the old
  Puzles IDs (`0x7a3e5c11/12`): redefining a stored scripted attribute with other parameters loses its data.
- `CHANGELOG.md` – the user's version diary, **in Spanish**, newest first, written for users (what changed for them,
  not code details). Add an entry for every change that is committed.

## Commands
Max's Python: `C:\Program Files\Autodesk\3ds Max 2027\Python\python.exe` (always run with `-I`).
- Build: `python -I tools\build.py`
- Live Max: the Open3DS dev bridge (`Z:\02_ASSETS\06_SOFTWARE\03_OPEN3DS\dev\bridge.py file.py`) runs Python in the
  user's Max; load this checkout with `sys.path.insert(0, r"...\package\OpenManager")`, set
  `sys.dont_write_bytecode = True`, and remove the module and path again at the end. Tests must only run on an empty,
  unsaved scene (the user's open scene is real work) and must not leave modal dialogs (they hang the bridge).
- Do not run `install.ms` in the user's Max without asking: it installs a startup script and macro in their profile.

## Known issues (audit of 2026-11-09, not fixed yet)
- Batch renders without saving when the output path is invalid (e.g. a camera named `CAM:Bad`).
- Setups only set what they control, so state leaks from one setup to the next.
- Snippet/pre-render MAXScript stored in a `.max` runs on a single click.
- Applying a setup is not undoable.
- `omgr_texmaps` takes ~36 s with 10k objects; the scene is re-read on every mouse enter; Objects card caps at 5000.
- Objects/layers are tracked by handle/name only.

## Git
- Branch `main`, remote `origin` = https://github.com/carlesllavata/OpenManager (private for now).
- The repo is on a NAS, so it is listed in the global `safe.directory`.
