# OpenManager

An open-source scene setups and batch render manager that lives inside **3ds Max 2025 and later**
(the Python + PySide6 that ships with Max, plus a MAXScript library). No separate program, no browser and
**no account or login**: install it and start using it.

OpenManager is part of [Open3D](https://github.com/carlesllavata/Open3D), a suite of open-source tools for
3D work.

> Status: early (v0.3.0).
> What each version adds: [CHANGELOG.md](CHANGELOG.md).

A **setup** stores, for one `.max` file: camera, resolution, frames, sun, dome, environment, layers, objects,
lights, XRefs, output path, render settings, Corona VFB post-production and more. Click a setup and it is applied
to the scene; **Batch Render** renders every ticked setup, one after the other.

**Renderers:** Corona and V-Ray. FStorm works too, with less testing.

## Install

The easy way: install the [Open3D Launcher](https://github.com/carlesllavata/Open3D/releases/latest) and click
**Install** next to OpenManager, with 3ds Max closed. It puts OpenManager in `%APPDATA%\Autodesk\ApplicationPlugins`
as a plug-in bundle (every 3ds Max from 2025 on loads it), tells you when a new version is out and updates it. To
uninstall, choose **Uninstall…** in OpenManager's menu in the launcher.

By hand, each [release](https://github.com/carlesllavata/OpenManager/releases/latest) has the bundle as a zip. To
build it from source: `python tools/build.py` (plain Python 3, no dependencies) writes it to `dist/`.

- **`OpenManager.bundle`** is the Autodesk plug-in bundle that the Open3D launcher installs. By hand: with 3ds Max
  closed, copy the folder into `%APPDATA%\Autodesk\ApplicationPlugins\` and start Max. It works in every Max from
  2025 on. To remove it, delete its folder with Max closed.
- **The `.mzp` is retired:** versions up to 0.3.0 also came as `OpenManager.mzp`. If OpenManager was installed with
  it, the bundle removes that copy the first time it starts (your settings stay).

Then *Customize > Customize User Interface > Toolbars*, **Group: Main UI**, **Category: OpenManager**: drag the
**OpenManager** action to a toolbar or a menu. Setups saved inside `.max` files are never touched by installing or
removing.

- Setups are saved **inside the .max file** (the `OpenManager_Dat` attribute of `rootNode`).
- Setups made with **Pulze Scene Manager** and with the previous version of this tool (*Puzles · Scene Manager*)
  are read and converted. The bundle also removes that previous version if it finds it, keeping its settings.
- Settings: `%APPDATA%\Open3D\OpenManager`, one set for every 3ds Max. The HDRI previews it makes, and the
  thumbnails, exports and presets of a scene not saved yet, go to `%LOCALAPPDATA%\Open3D\OpenManager`. Version
  0.3.0 and earlier kept the settings in the `plugcfg` folder of each 3ds Max: the first start of a newer version
  copies those of the newest 3ds Max that has some, and its HDRI previews, and leaves the old ones as they were.

## Modules

Scene Name, Camera, Resolution, Time Output, Sun, Lights, HDRI Quick Browser, Environment, Dome, Background,
Atmosphere, Layers, Objects, XRef, Variants, Render Output, Render Settings (Custom, Override, Preset),
Render Elements, Post-Production / VFB (Corona), Script File / Editor, Thumbnail, Todo and Notes.

## Layout

| path | what it is |
|---|---|
| `package/OpenManager.mcr` | the 3ds Max action |
| `bundle/OpenManager_bundle.ms` | what the bundle runs when 3ds Max starts |
| `package/OpenManager/omgr_setup.ms` | clean-up of older installs (the previous version and the retired .mzp) |
| `package/OpenManager/omgr_core.ms` | MAXScript functions (prefix `omgr_`) that read and change the scene |
| `package/OpenManager/OpenManager_startup.ms` | offers to open the window when a `.max` with Pulze setups is opened |
| `package/OpenManager/openmanager/` | the window (Python): `window.py`, cards in `cards.py` / `cards2.py`, `maxlink.py` (setup → changes in Max), `model.py` (data, no Max or Qt), `folders.py` (where its files go) |
| `tools/` | `build.py` (builds the bundle and the icons) and `make_props.py` (the Property Selector table) |

## If something goes wrong

Copy what appears in the **MAXScript Listener** (F11): errors are prefixed with `OpenManager`.

## Current limits

- Post-Production / VFB works with Corona only.
- The Script File card runs MAXScript (`.ms`) files only; it also offers `.py` files, but those don't run yet.
- Tested on 3ds Max 2026.3 and 2027 with Corona 14.

## License

Copyright (C) 2026 Carles Llavata and OpenManager contributors.

OpenManager is free software: you can redistribute it and/or modify it under the terms of the GNU General
Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even
the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE) for the full
text of the GNU General Public License v3 (SPDX: `GPL-3.0-or-later`).
