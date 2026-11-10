# OpenManager

An open-source scene setups and batch render manager that lives inside **3ds Max 2025 and later**
(the Python + PySide6 that ships with Max, plus a MAXScript library). No separate program, no browser and
**no account or login**: install it and start using it.

> Status: early (v0.2.1). See the [changelog](CHANGELOG.md).

A **setup** stores, for one `.max` file: camera, resolution, frames, sun, dome, environment, layers, objects,
lights, XRefs, output path, render settings, Corona VFB post-production and more. Click a setup and it is applied
to the scene; **Batch Render** renders every ticked setup, one after the other.

**Renderers:** Corona and V-Ray. FStorm works too, with less testing.

## Install (development build)

Build it: `python tools/build.py` (plain Python 3, no dependencies). It writes two packages to `dist/`:

- **`OpenManager.bundle`**, the Autodesk plug-in bundle that the Open3D launcher installs. By hand: with 3ds Max
  closed, copy the folder into `%APPDATA%\Autodesk\ApplicationPlugins\` and start Max. It works in every Max from
  2025 on. If OpenManager was installed with the `.mzp` before, the bundle removes that copy the first time it starts
  (your settings stay). To remove the bundle, delete its folder with Max closed.
- **`OpenManager.mzp`**, for a manual install: drag it onto a 3ds Max viewport. To remove it: *Scripting > Run
  Script…* > `uninstall.ms`, then restart Max. It won't install over the bundle.

Then *Customize > Customize User Interface > Toolbars*, **Group: Main UI**, **Category: OpenManager**: drag the
**OpenManager** action to a toolbar or a menu. Setups saved inside `.max` files are never touched by installing or
removing.

- Setups are saved **inside the .max file** (the `OpenManager_Dat` attribute of `rootNode`).
- Setups made with **Pulze Scene Manager** and with the previous version of this tool (*Puzles · Scene Manager*)
  are read and converted. Both installs also remove that previous version if they find it, keeping its settings.
- Window settings: `plugcfg\OpenManager.json`.

## Modules

Scene Name, Camera, Resolution, Time Output, Sun, Lights, HDRI Quick Browser, Environment, Dome, Background,
Atmosphere, Layers, Objects, XRef, Variants, Render Output, Render Settings (Custom, Override, Preset),
Render Elements, Post-Production / VFB (Corona), Script File / Editor, Thumbnail, Todo and Notes.

## Layout

| path | what it is |
|---|---|
| `uninstall.ms` | uninstaller |
| `package/install.ms`, `mzp.run`, `OpenManager.mcr` | .mzp installer and the 3ds Max action |
| `bundle/OpenManager_bundle.ms` | what the bundle runs when 3ds Max starts |
| `package/OpenManager/omgr_setup.ms` | clean-up of older installs, shared by the bundle and the .mzp |
| `package/OpenManager/omgr_core.ms` | MAXScript functions (prefix `omgr_`) that read and change the scene |
| `package/OpenManager/OpenManager_startup.ms` | offers to open the window when a `.max` with Pulze setups is opened |
| `package/OpenManager/openmanager/` | the window (Python): `window.py`, cards in `cards.py` / `cards2.py`, `maxlink.py` (setup → changes in Max), `model.py` (data, no Max or Qt) |
| `tools/` | `build.py` (builds the bundle, the .mzp and the icons) and `make_props.py` (the Property Selector table) |

## If something goes wrong

Copy what appears in the **MAXScript Listener** (F11): errors are prefixed with `OpenManager`.

## Current limits

- Post-Production / VFB works with Corona only.
- Tested on 3ds Max 2026.3 and 2027 with Corona 14.

## License

Copyright (C) 2026 Carles Llavata and OpenManager contributors.

OpenManager is free software: you can redistribute it and/or modify it under the terms of the GNU General
Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even
the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE) for the full
text of the GNU General Public License v3 (SPDX: `GPL-3.0-or-later`).
