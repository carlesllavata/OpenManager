# Changelog

What each version of OpenManager adds, newest first.

## In development

- **Errors are no longer hidden.** In many places OpenManager caught any error and went on without a word. Now
  each place catches only what can be expected there, from 3ds Max, from a file or from the JSON in it, and
  anything else reaches the MAXScript Listener. Where one error must not stop the rest (what a button runs, a
  batch render, the autosave, each change a setup makes), OpenManager still goes on, and writes the error there.
  A value 3ds Max refuses in the tone-mapping chain of a camera is now told in the Listener too, as it already was
  for the Post-Production / VFB card.
- **Load Output Preset leaves the Output card as it was when the file isn't a preset.** A file whose Output
  tokens were not what OpenManager writes said "Invalid preset", but the active setup had already taken what the
  file held, and its Output card was left broken. Now the file is checked first.
- **Your settings move to the Open3D folders, one set for every 3ds Max,** with the other Open3D apps: the settings
  (the window, your default settings, the scripts you trust, the Pulze notification) to `%APPDATA%\Open3D\OpenManager`,
  the HDRI previews to `%LOCALAPPDATA%\Open3D\OpenManager`. Until now each 3ds Max version kept its own in its
  `plugcfg` folder. The first time 3ds Max starts with this version, whichever version it is, OpenManager copies the
  settings of the newest 3ds Max that has some, and its HDRI previews, so nothing has to be set up again; the old
  files are left as they were, and those of the other versions stay where they are. If the copy fails, OpenManager
  says so and uses the old ones for that session, and tries again the next time. The thumbnails, exports and render
  presets of a scene that is not saved yet go there too, instead of `plugcfg`.
- **No more `.mzp`.** OpenManager is installed only as a plug-in bundle: with the Open3D launcher, or by copying
  `OpenManager.bundle` into `%APPDATA%\Autodesk\ApplicationPlugins` with 3ds Max closed. If you installed the `.mzp`
  before, the bundle still removes that copy the first time it starts, and your settings stay.
- **Class names that come with a file are never run.** A setup names some things by their 3ds Max class: the
  tone-mapping operators of the Post-Production / VFB card and of a Corona camera, and the maps its settings use.
  Setups travel inside the `.max`, and those names were run as MAXScript when a setup was applied, so a file from
  someone else could run anything with one click, past the question OpenManager asks about scripts. Now a name is
  only looked up among the classes 3ds Max has. One that is not a tone-mapping operator or a texture map class is
  left out, and OpenManager says so: a message in the window, and the name in the MAXScript Listener. Your own
  setups work exactly as before, Corona and V-Ray classes included.
- **A file can't hide a script where OpenManager keeps what to put back.** The values a setup replaced are stored
  in the `.max` with the setups, and put back without being shown. A script written there by hand ran when any
  setup was clicked, batch rendered or baked, with no question asked. Now only values to put back are read from
  there, and OpenManager says when it ignored anything else.
- **Batch Render, Bake Setups and Viewport Preview were checked:** scripts that came with a file go through the
  same question there as when you click a setup. Tests now cover it.
- **A file only sets what the cards set.** Every change a setup makes names the property it sets. A file from
  someone else could name any property there, or a path through other objects to one: the script of a script
  controller that is in the scene, for instance, which 3ds Max then runs. Now a change read from a file is only
  applied when it names a setting the cards of OpenManager set (any plain setting of the renderer for Render
  Settings - Override), never a path into another object and never a property that holds code. What is left out
  is told like the class names: a message in the window, the detail in the MAXScript Listener. Your own setups
  work as before, the ones converted from Pulze too.
- **A render preset that came with a file is not loaded without asking.** The Render Settings - Preset card loads
  a `.rps` file, which replaces the render settings of the scene, from a path kept in the setup. A setup from
  someone else loaded whatever file its path named, as soon as it was clicked or rendered. Now the preset is
  shown with its path in the same question as the scripts, and is only loaded once you agree. A preset you type,
  choose or save in the card is yours and loads as before. The setting, now called *Scripts and render presets
  that came with a file* (ask, always, never), covers both, for a click on a setup, Batch Render, Bake Setups and
  Viewport Preview.
- **A render preset does not bring the scripts of Render Setup.** A `.rps` file also keeps the pre-render and
  post-render scripts of Render Setup (*Common > Scripts*: the two files and their switches), so a preset you
  agreed to load could still set a script that 3ds Max runs at the next render. When OpenManager loads a preset,
  it now leaves those scripts as they were, whatever the preset holds and also when the load fails: for a click
  on a setup, Batch Render, Bake Setups, Viewport Preview, and for a preset you chose yourself. The question about
  presets says so. The scripts of the setup's own Script cards are another thing and run as before.
- **Clean-up.** The code now follows the common OPEN3D format and checks (ruff for Python, spaces instead of tabs
  in MAXScript). OpenManager works exactly as before.
- **Enter no longer approves scripts or presets that came with a file.** In the question OpenManager asks before
  it runs a script or loads a render preset that came with a file, Enter was meant to press the button that says
  no, but it pressed the one that approves. Now Enter refuses wherever the focus is, on the approving button too;
  approving takes a click, or Space on that button. Escape and the X of the window refuse, as before.

## 0.3.0 — 11 November 2026

OpenManager joins the Open3D Launcher: install and update it from there, as a 3ds Max plug-in.

- **Clean-up.** Code nothing used any more was removed (an unused Corona post-production save and a few
  helpers). OpenManager works exactly as before.
- **OpenManager is free software under the GNU GPL v3 or later.** You can use it, share it and change it
  freely; if you share a changed version, it has to stay under the same license with its source. The full text
  is in `LICENSE`.
- **Install and update OpenManager with the [Open3D Launcher](https://github.com/carlesllavata/Open3D/releases/latest).**
  It installs OpenManager as a 3ds Max plug-in bundle: one folder in `ApplicationPlugins`, nothing copied into your 3ds Max profile, and it works in every 3ds Max
  from 2025 on at once. The OpenManager action, its icons and the offer to open Pulze setups work exactly as before.
- **Switching from the .mzp is automatic.** The first time the bundle starts, it removes the copy the `.mzp`
  installed, so OpenManager is never loaded twice. Your settings stay. The `.mzp` is still there for a manual
  install, but it won't install on top of the bundle.
- The bundle also removes the version from before the name OpenManager, the same way the `.mzp` installer does.
- **README brought up to date:** the Open3D suite, installing with the launcher, and the Script File card running
  MAXScript files only for now.

## 0.2.1 — 10 November 2026

- **The installer works again.** Dragging `OpenManager.mzp` onto 3ds Max 0.2.0 did nothing: no message, nothing in
  *Customize User Interface*. 3ds Max refused the package because of how its version number was written, and it
  doesn't say so. Fixed, and the build now checks for it so it can't happen again.

## 0.2.0 — 9 November 2026

The first release of OpenManager: the tool gets its new name, and the problems found when it was reviewed are fixed.
Batch Render never renders without saving, setups no longer leave their changes behind and can be undone, scripts
that come with a file ask before they run, big scenes are much faster, and setups keep their objects and layers
through renames and merges.

- **Setups keep their objects and layers through renames and merges.** Every camera, sun, dome, light, object and
  layer a setup uses now gets an ID of its own, stored with it in the scene, so OpenManager finds it again:
  - **Renamed layers** stay in the Layers and Variants cards (before, a renamed layer was simply lost).
  - **Renamed objects** keep working, and their new name shows in the cards.
  - **Merged nodes**, which get new handles in the file they are merged into, are found by their ID, so setups you
    import (.smp) into a file where the scene was merged apply to the right nodes, light settings included.
  - **Another object that took the old handle is never touched by mistake:** before, an imported setup could hide
    or change whatever object happened to have the same handle in the new file.
  - A deleted object stays in its setups and is found again if it comes back (Undo, or merged again).
  - Older setups get their IDs the next time the file is saved; until then they work as before, and an object
    re-created with the same name is still found by its name.
- **Much faster on big scenes.** Measured on a scene with 10,000 objects and 200 materials:
  - The map list of texture-map settings (camera overrides…) took **41 seconds**, with 3ds Max frozen; now
    **0.2 s**. OpenManager now finds maps by walking from the materials, the environment, the Material Editors and
    the texture-map settings of the renderer, cameras and lights, instead of scanning the whole scene once per map
    type.
  - Reading the scene (when the window opens, when you come back to it with the mouse…) went from 0.7 s to 0.17 s.
  - Applying a setup looks maps up from a cache (40 ms per map before, instant now).
- **No more 5,000-object limit in the Objects card.** The scene read used to list only the first 5,000 objects, so
  "add selected" ignored objects beyond them. Now it only reads the objects your setups use, plus the selection
  when you add it, so any object of any scene can be added.
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
- **OpenManager is born.** The tool, until now *Puzles · Scene Manager*, is renamed **OpenManager**
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
