# OpenManager

Gestor de *setups* (estados de escena) y render por lotes **open source** que vive dentro de **3ds Max 2025+**
(Python + PySide6 que ya trae Max, más una librería MAXScript). Sin programas aparte, sin navegador y **sin cuentas
ni login**: lo instalas y ya puedes usarlo.

> **Estado:** en desarrollo (0.1.0). Ver el [diario de cambios](CHANGELOG.md).

Un **setup** guarda, para un mismo `.max`: cámara, resolución, frames, sol, domo, entorno, capas, objetos, luces,
xrefs, ruta de salida, ajustes de render, post-producción del VFB (Corona) y más. Al clicar un setup se aplica a la
escena; el **Batch Render** renderiza todos los marcados.

**Motores:** Corona y V-Ray. FStorm funciona pero con menos pruebas.

## Instalar (versión de desarrollo)

1. Compila el instalador: `python tools/build.py` (Python 3 normal, sin dependencias). Crea `dist/OpenManager.mzp`.
2. Arrastra el `.mzp` a un visor de 3ds Max.
3. *Customize > Customize User Interface > Toolbars*, **Group: Main UI**, **Category: OpenManager**: arrastra la
   acción **OpenManager** a una barra o un menú.

Para quitarlo: *Scripting > Run Script…* > `uninstall.ms` y reinicia Max. Los setups guardados en los `.max` no se tocan.

- Los setups se guardan **dentro del .max** (atributo `OpenManager_Dat` de `rootNode`).
- Se leen y convierten los setups de **Pulze Scene Manager** y los de las versiones anteriores de esta herramienta
  (cuando se llamaba *Puzles · Scene Manager*). El instalador también retira esa versión anterior si la encuentra y
  conserva sus ajustes.
- Ajustes de la ventana: `plugcfg\OpenManager.json`.

## Módulos

Scene Name, Camera, Resolution, Time Output, Sun, Lights, Hdri Quick Browser, Environment, Dome, Background,
Atmosphere, Layers, Objects, Xref, Variants, Render Output, Render Settings (Custom, Override, Preset),
Render Elements, Post-Production / VFB (Corona), Script File / Editor, Thumbnail, Todo y Notes.

## Estructura

| ruta | qué es |
|---|---|
| `uninstall.ms` | desinstalador |
| `package/install.ms`, `mzp.run`, `OpenManager.mcr` | instalador y botón de Max |
| `package/OpenManager/omgr_core.ms` | funciones MAXScript (prefijo `omgr_`) que leen y cambian la escena |
| `package/OpenManager/OpenManager_startup.ms` | aviso al abrir un `.max` con setups de Pulze |
| `package/OpenManager/openmanager/` | la ventana (Python): `window.py`, tarjetas en `cards.py` / `cards2.py`, `maxlink.py` (setup → cambios en Max), `model.py` (datos, sin Max ni Qt) |
| `tools/` | `build.py` (genera el .mzp y los iconos) y `make_props.py` (tabla del Selector de propiedades) |

## Si algo falla

Copia lo que salga en el **MAXScript Listener** (F11): los errores llevan el prefijo `OpenManager`.

## Límites actuales

- Post-Production / VFB solo con Corona.
- Probado en 3ds Max 2026.3 y 2027 con Corona 14.
