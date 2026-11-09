# Diario de cambios

Lo que va añadiendo cada versión de OpenManager, de la más reciente a la más antigua.

## En desarrollo

### 9 de noviembre de 2026

- **Nace OpenManager.** La herramienta, hasta ahora *Puzles · Scene Manager*, pasa a llamarse **OpenManager**
  (versión 0.1.0) y será open source. No necesita cuenta ni login: se instala y se usa.
- **Nombre nuevo en todo 3ds Max.** La acción está en *Customize User Interface* > **Category: OpenManager**, la
  ventana se titula OpenManager y los errores del MAXScript Listener llevan ese prefijo. Los archivos de ajustes
  pasan a ser `plugcfg\OpenManager.json` (y `_default.json`, `_notify.txt`), y las carpetas que crea junto a tus
  escenas, `OpenManager_thumbs`, `OpenManager_export` y `OpenManager_presets`.
- **Icono nuevo:** una pila de tarjetas, en gris claro sobre la interfaz oscura y en gris oscuro sobre la clara.
- **Tus setups de antes siguen ahí.** Al abrir un `.max` con setups de la versión anterior (Puzles), OpenManager los
  lee tal cual; la próxima vez que guardes el archivo pasan a su nuevo sitio dentro del `.max` y el antiguo se borra.
  Los mapas que mezclaban las pestañas del Environment se conservan. Los setups de Pulze Scene Manager se siguen
  importando como antes.
- **El instalador se encarga de la versión anterior.** Si encuentra Puzles · Scene Manager instalado, lo cierra y lo
  retira, y se queda con tus ajustes y la caché de miniaturas de HDRI.
- **Sin Redshift.** Los motores soportados son **Corona** y **V-Ray**; **FStorm** funciona, pero con menos pruebas.
  Las luces, soles, cielos y bitmaps de Redshift ya no aparecen en las tarjetas.
- El desinstalador también borra la caché de miniaturas de HDRI.
- El instalador ya compilado deja de estar en el repositorio: se genera con `python tools/build.py`
  (`dist/OpenManager.mzp`).
- **Historial del repositorio reiniciado.** OpenManager empieza con un único commit propio, `OpenManager 0.1.0`; a
  partir de aquí cada cambio queda en git y en este diario.
- **El repositorio, en inglés.** Como en Open3DS, la app, el código, el README y los textos de GitHub están en
  inglés; este diario sigue en español.
