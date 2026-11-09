# OpenManager – notes for Claude

Open-source scene setups / batch render manager for 3ds Max (2025+). The user's environment: 3ds Max 2027,
Python 3.13 (bundled with Max), PySide6, Corona 14 and V-Ray. The repo lives on a NAS share (`Z:` maps to
`\\192.168.2.10\...`). Talk to the user in Spanish; everything in the repo and on GitHub is in English, as in
Open3DS: app, code, comments, commit messages, README, `CHANGELOG.md` and release notes.

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
- `CHANGELOG.md` – the user's version diary, **in English** (it was Spanish until 9 November 2026), newest first, written for users (what changed for them,
  not code details). Add an entry for every change that is committed.

## Commands
Max's Python: `C:\Program Files\Autodesk\3ds Max 2027\Python\python.exe` (always run with `-I`).
- Build: `python -I tools\build.py`
- Live Max: the Open3DS dev bridge (`Z:\02_ASSETS\06_SOFTWARE\03_OPEN3DS\dev\bridge.py file.py`) runs Python in the
  user's Max; load this checkout with `sys.path.insert(0, r"...\package\OpenManager")`, set
  `sys.dont_write_bytecode = True`, and remove the module and path again at the end. Tests must only run on an empty,
  unsaved scene (the user's open scene is real work) and must not leave modal dialogs (they hang the bridge).
- Do not run `install.ms` in the user's Max without asking: it installs a startup script and macro in their profile.

## Batch render rules
- Never render a frame that isn't saved: `window.start_render` checks every setup with `model.check_jobs`
  (incomplete path, nothing saved, missing camera, two setups on one file), shows `dialogs.BatchCheckDialog` when
  something is wrong, renders only the clean ones, checks the written file with `model.find_written`, and ends with
  `dialogs.BatchReportDialog` (non-modal; rows also kept in `window.last_report`). One failure doesn't stop the batch.
- An incomplete output path leaves the scene's render output untouched (`actions_for` passes `None`).
- Token values go through `model.clean_name`. Tests without Max: `python -I tests\run.py`.
- Live tests drive the batch with `w.check_render(jobs)` + `w._begin_render(runnable, skipped)`: `start_render`
  opens a modal dialog when a setup has problems, which would hang the bridge.

## Base state (no leaks between setups)
- Every way of applying a setup (`_apply`, batch `_next_job`, `_run_over_setups`) runs `window.base_restore(acts)`
  first and prepends its result. `model.base_step` keeps `window.base` = {action_key: change that puts the value
  back} for exactly the keys the applied setup controls; `maxlink.capture(action)` reads the value about to be
  replaced. Keys come from `model.action_key` (None = never put back: camera, background, code, preset,
  renderscripts, mkdir, renderview). Restore-only change kinds: `timeraw`, `lightson`, `envraw`, `outputraw`.
- `window.base` is saved in the setups text (`"base"`, `model.base_to_json`), so a file saved with a setup applied
  still knows what to put back. Setting `max.restore_base` (default on) turns it off.
- A new change kind that a setup can make needs an `action_key`, a `capture` branch and, if needed, a restore kind.

## Undo / redo
- 3ds Max's undo stays off while a setup is applied (`maxlink.run` uses `pymxs.undo(False)`): it can't take back
  globals like `renderWidth` or `rendOutputFilename`, and a partial Ctrl+Z would desync the base state.
- Instead `window.activate` / `restore_scene` open a record (`begin_undo`/`end_undo`); `_apply` calls
  `undo_capture(fresh)` before running, which fills it via `model.undo_capture` + `maxlink.capture` (first value
  wins; `model.undo_key` adds the viewport camera, restored with `camraw`). Edits of the active setup extend the
  last record. `undo()` runs the record and restores `base`/`active_id`; `redo()` re-activates. History is cleared
  on file load and when a batch starts. Restore kinds carry their key (`lightson` has "sun"/"dome" as a[1]).

## Scripts in setups
- `window.actions_for` drops untrusted scripts with `model.filter_scripts(acts, window.script_allowed)` (the "code"
  changes and the fields of "renderscripts"); `window._refused` keeps what was left out. Trusted = key
  (`model.script_key`: sha256 of the code, or the normalized path of a file) in `settings["trusted_scripts"]`
  (plugcfg, never the .max), or code typed in the Script Editor this session (`window.typed_code`), or Settings
  `max.scripts` = "always". Paths typed/chosen in the Script File card are trusted at once.
- `window.review_scripts(setups)` runs before activate, re-click, batch and `_run_over_setups`, and shows
  `dialogs.ScriptReviewDialog` through `window.ask_scripts(rows)` (live tests replace `ask_scripts` with a stub: the
  dialog is modal). "Don't run them" is remembered for the session in `window._denied`.

## Performance rules (big scenes)
- Never use `getClassInstances` per class to find maps: it scans the whole scene each call. `omgr_allMaps()` walks
  from `sceneMaterials`, the environment, the Material Editors, `OpenManager_Maps` and texture-map props of the
  renderer, cameras and lights (visited set: `Dictionary #integer` of `getHandleByAnim`). `omgr_findMap` uses the
  `omgr_mapCache` dictionary (validated on use, rebuilt on a miss, cleared by `omgr_fire` on #preopen/#file); the
  getClassInstances fallback only runs for a map nothing points to.
- `omgr_scene handles:` lists only the objects the setups use (`window.object_handles()`); the selection is read
  with `omgr_objectsInfo` (`window.selected_objects`). `object_total` = geometry.count + shapes.count.
- Reference (10k boxes, 200 materials, Max 2027): scene read ~170 ms, map list ~160 ms, cached map lookup ~0 ms.

## References to nodes and layers
- Node references (`model.node_refs`: camera, suns, dome, Objects entries) are dicts {handle, name, uid}; the
  Lights card keeps plain handles plus `s["lights"]["uids"]` {str(handle): uid} and props keyed `26|handle|prop`
  (`model.rekey_light` moves them). Layer references (`model.layer_refs`): Layers entries {name, uid}, Variants
  `layers` + parallel `uids`.
- The uid is a GUID in app data slot 1330465865 of the node / `layer.layerAsRefTarg` (survives save, rename and
  merge; `copy` does not copy it). `window.stamp_uids()` runs in `save_setups` for references without one
  (`omgr_stampNodes` re-IDs a node whose ID another node shares).
- `window.resolve_all(setups, strict)` (file load, every scene re-read, activate, import with strict=True): one
  `omgr_resolveNodes` call → `model.apply_resolved`. Node at the stored handle with the same uid (or no uid yet) →
  kept; else by uid; else the only node with that name. -1 = missing (reference kept, it may come back), -2 = the
  handle is another node (reference stops using it; strict drops such lights). Layers follow `omgr_layerUids`.

## Known issues (audit of 2026-11-09, not fixed yet)
- The Script File card offers `.py` files, but render scripts run through `fileIn` (MAXScript only).
- The scene is still re-read (~170 ms on 10k objects) each time the mouse enters the window, throttled to 0.8 s.

## Git
- Branch `main`, remote `origin` = https://github.com/carlesllavata/OpenManager (private for now).
- The repo is on a NAS, so it is listed in the global `safe.directory`.
