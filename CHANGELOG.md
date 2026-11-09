# Changelog

What each version of OpenManager adds, newest first.

## In development

### 9 November 2026

- **Scripts that come with a file no longer run without asking.** Setups can carry MAXScript (Script Editor card)
  and point at script files (Script File card), and they travel inside the `.max`. Before, opening someone else's
  file and clicking a setup ran its scripts straight away, and its render scripts ran on every render. Now:
  - The first time a setup would run scripts that came with the file, OpenManager **shows you their code** and asks:
    **Run these scripts** or **Don't run them** (the safe choice is the default). The setup is applied either way.
  - Your answer is remembered on your computer (never in the `.max`). If a script changes, you are asked again.
  - **Scripts you write in the Script Editor or files you choose in the Script File card are yours** and always run.
  - Batch Render, Bake Setups and Viewport Preview ask once for all the setups before they start, and the batch
    report says when a setup's scripts were not run.
  - **Settings > Setups > Scripts that came with a file:** ask (default), always run them, or never run them.
- **Undo and Redo for setups.** Applying a setup can now be undone: the new **Undo** and **Redo** buttons in the
  top bar (and **Ctrl+Z** / **Ctrl+Y** while the OpenManager window has the focus) bring back the scene exactly as
  it was before you clicked the setup, viewport camera included, and apply it again. Changes you make in the cards
  of the active setup are undone together with it, and *Put back the scene as it was before the setups* is undoable
  too. Before, nothing a setup did could be undone, not even with 3ds Max's Ctrl+Z.
  - It undoes what happened in the scene, not your edits to the setups themselves.
  - The history holds the last 30 steps and starts again when you open another file or run a batch.
  - Scripts and render presets can't be undone; the button's tooltip says what the next Undo does.
- **Setups no longer leave their changes behind.** A setup only changes what its cards control, so before, whatever
  one setup changed stayed for the next one: with setup A at frame 37 and setup B without a Time Output card, B also
  rendered frame 37, and results depended on the order you clicked. Now OpenManager remembers the value each setup
  replaces and puts it back when the next setup doesn't control it, so every setup starts from the scene as it was
  before any setup: resolution, time output, suns and domes, environment, layers, objects, lights, render settings,
  render output, XRefs, atmospherics, render elements and Corona post-production. It also works in Batch Render, and
  it is saved with the `.max`, so it keeps working after you close and reopen the file.
  - Changes you make by hand to something no setup controls are kept, and become the new starting point.
  - The viewport camera and background, scripts and render presets are not put back.
  - **Right-click in the setup list > Put back the scene as it was before the setups** undoes every setup at once.
  - To keep the old behaviour, untick **Settings > Setups > Put back what the previous setup changed and the new one
    doesn't control**.
- **Batch Render never renders without saving any more.** Before, a setup whose output path wasn't complete
  (a camera named `CAM:Bad`, a missing Extension token...) switched saving off and rendered anyway, and the batch
  still said it had finished. Now:
  - **Names are cleaned.** Characters Windows doesn't allow in file names (`: * ? " < > |`) become `_`, so the
    camera `CAM:Bad` saves as `CAM_Bad.png`. Folder names lose the trailing dots and spaces Windows would drop.
  - **The Render Output card says what is missing** under the red path ("The Camera token has no value (the
    setup has no camera)", "No Extension token"...). Clicking such a setup leaves the scene's own output as it is.
  - **Every setup is checked before the batch starts.** If one would save nothing (incomplete path, or the card
    off and no output in the scene) or its camera is gone, a window lists them and why; you can render the others
    or cancel. It also warns when two setups would save to the same file.
  - **One setup failing doesn't stop the batch:** it is marked as failed and the next one renders.
  - **The file is checked after each render**, and at the end a report lists every setup: saved (and where),
    skipped or failed, and why. It is also printed in the MAXScript Listener.
- **OpenManager is born.** The tool, until now *Puzles · Scene Manager*, is renamed **OpenManager** (version 0.1.0)
  and becomes open source. No account or login: install it and use it.
- **New name all over 3ds Max.** The action is in *Customize User Interface* > **Category: OpenManager**, the
  window is titled OpenManager and MAXScript Listener errors carry that prefix. The settings files become
  `plugcfg\OpenManager.json` (plus `_default.json` and `_notify.txt`), and the folders it creates next to your
  scenes, `OpenManager_thumbs`, `OpenManager_export` and `OpenManager_presets`.
- **New icon:** a stack of cards, light grey on the dark interface and dark grey on the light one.
- **Your earlier setups are still there.** When you open a `.max` with setups from the previous version (Puzles),
  OpenManager reads them as they are; the next time you save the file they move to their new place inside the
  `.max` and the old one is removed. The maps that mixed the Environment tabs are kept. Setups from Pulze Scene
  Manager are still imported as before.
- **The installer takes care of the previous version.** If it finds Puzles · Scene Manager installed, it closes and
  removes it, keeping your settings and the HDRI thumbnail cache.
- **No Redshift.** The supported renderers are **Corona** and **V-Ray**; **FStorm** works, with less testing.
  Redshift lights, suns, skies and bitmaps no longer appear in the cards.
- The uninstaller also deletes the HDRI thumbnail cache.
- The prebuilt installer is no longer kept in the repository: build it with `python tools/build.py`
  (`dist/OpenManager.mzp`).
- **Repository history restarted.** OpenManager starts with a single commit of its own, `OpenManager 0.1.0`; from
  here on every change is recorded in git and in this changelog.
- **Everything in English.** As in Open3DS, the app, the code, the README, this changelog and the GitHub texts are
  in English.
