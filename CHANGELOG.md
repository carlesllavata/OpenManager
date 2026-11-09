# Changelog

What each version of OpenManager adds, newest first.

## In development

### 9 November 2026

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
