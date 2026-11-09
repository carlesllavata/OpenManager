# OpenManager

An open-source scene setups and batch render manager that lives inside **3ds Max 2025 and later**
(the Python + PySide6 that ships with Max, plus a MAXScript library). No separate program, no browser and
**no account or login**: install it and start using it.

> Status: early (v0.1.0). See the [changelog](CHANGELOG.md).

A **setup** stores, for one `.max` file: camera, resolution, frames, sun, dome, environment, layers, objects,
lights, XRefs, output path, render settings, Corona VFB post-production and more. Click a setup and it is applied
to the scene; **Batch Render** renders every ticked setup, one after the other.

**Renderers:** Corona and V-Ray. FStorm works too, with less testing.

## Install (development build)

1. Build the installer: `python tools/build.py` (plain Python 3, no dependencies). It writes `dist/OpenManager.mzp`.
2. Drag the `.mzp` onto a 3ds Max viewport.
3. *Customize > Customize User Interface > Toolbars*, **Group: Main UI**, **Category: OpenManager**: drag the
   **OpenManager** action to a toolbar or a menu.

To remove it: *Scripting > Run Script…* > `uninstall.ms`, then restart Max. Setups saved inside `.max` files are
left untouched.

- Setups are saved **inside the .max file** (the `OpenManager_Dat` attribute of `rootNode`).
- Setups made with **Pulze Scene Manager** and with the previous version of this tool (*Puzles · Scene Manager*)
  are read and converted. The installer also removes that previous version if it finds it, keeping its settings.
- Window settings: `plugcfg\OpenManager.json`.

## Modules

Scene Name, Camera, Resolution, Time Output, Sun, Lights, HDRI Quick Browser, Environment, Dome, Background,
Atmosphere, Layers, Objects, XRef, Variants, Render Output, Render Settings (Custom, Override, Preset),
Render Elements, Post-Production / VFB (Corona), Script File / Editor, Thumbnail, Todo and Notes.

## Layout

| path | what it is |
|---|---|
| `uninstall.ms` | uninstaller |
| `package/install.ms`, `mzp.run`, `OpenManager.mcr` | installer and the 3ds Max action |
| `package/OpenManager/omgr_core.ms` | MAXScript functions (prefix `omgr_`) that read and change the scene |
| `package/OpenManager/OpenManager_startup.ms` | offers to open the window when a `.max` with Pulze setups is opened |
| `package/OpenManager/openmanager/` | the window (Python): `window.py`, cards in `cards.py` / `cards2.py`, `maxlink.py` (setup → changes in Max), `model.py` (data, no Max or Qt) |
| `tools/` | `build.py` (builds the .mzp and the icons) and `make_props.py` (the Property Selector table) |

## If something goes wrong

Copy what appears in the **MAXScript Listener** (F11): errors are prefixed with `OpenManager`.

## Current limits

- Post-Production / VFB works with Corona only.
- Tested on 3ds Max 2026.3 and 2027 with Corona 14.
