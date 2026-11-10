-- SPDX-License-Identifier: GPL-3.0-or-later
-- OpenManager install housekeeping, shared by the .mzp installer (install.ms) and the start of OpenManager.bundle
-- (OpenManager_bundle.ms). Each step only acts on what it finds, so running it again does nothing.

global omgr_home
global omgr_migrateLegacy
global omgr_removeMzpInstall

-- The version installed before the tool was called OpenManager ("Puzles"): closed and removed, its settings carried
-- over. Setups saved inside .max files by that version are read and converted by the tool itself.
fn omgr_migrateLegacy =
(
	try (python.Execute "import sys\nm = sys.modules.get('puzles_sm')\nif m:\n    m.close()") catch()
	callbacks.removeScripts id:#pzsm
	callbacks.removeScripts id:#pzsmRender
	callbacks.removeScripts id:#pzsmStartup
	local cfg = (getDir #plugcfg) + "\\"
	for ext in #(".json", "_default.json", "_notify.txt") do
	(
		local was = cfg + "Puzles_SceneManager" + ext
		local now = cfg + "OpenManager" + ext
		if (doesFileExist was) do
		(
			if (not (doesFileExist now)) do copyFile was now
			deleteFile was
		)
	)
	local oldFiles = #((getDir #userStartupScripts) + "\\Puzles_SceneManager_startup.ms", (getDir #userMacros) + "\\Puzles_SceneManager.mcr")
	for theme in #("Dark", "Light") do
		for f in (getFiles ((getDir #userIcons) + "\\" + theme + "\\Puzles_SceneManager_*.png")) do append oldFiles f
	for f in oldFiles where (doesFileExist f) do deleteFile f
	local oldDir = (getDir #userScripts) + "\\Puzles"
	if (doesDirectoryExist oldDir) do try ((dotNetClass "System.IO.Directory").Delete oldDir true) catch()
	local oldCache = cfg + "Puzles_SceneManager_hdri"
	local newCache = cfg + "OpenManager_hdri"
	if ((doesDirectoryExist oldCache) and not (doesDirectoryExist newCache)) then try ((dotNetClass "System.IO.Directory").Move oldCache newCache) catch()
	else if (doesDirectoryExist oldCache) do try ((dotNetClass "System.IO.Directory").Delete oldCache true) catch()
	ok
)

-- The per-user install made by OpenManager.mzp (scripts, startup script, macro, icons), removed when OpenManager runs
-- from the bundle. Settings in plugcfg stay. Never touches the folder OpenManager is running from. True = removed something.
fn omgr_removeMzpInstall =
(
	local removed = false
	local dir = (getDir #userScripts) + "\\OpenManager"
	local running = isKindOf omgr_home String and ((pathConfig.normalizePath omgr_home) as name) == ((pathConfig.normalizePath dir) as name)
	if (not running) do
	(
		if (doesDirectoryExist dir) do
			try ((dotNetClass "System.IO.Directory").Delete dir true; removed = true) catch()
		local files = #((getDir #userStartupScripts) + "\\OpenManager_startup.ms", (getDir #userMacros) + "\\OpenManager.mcr")
		for theme in #("Dark", "Light") do
			for f in (getFiles ((getDir #userIcons) + "\\" + theme + "\\OpenManager_*.png")) do append files f
		for f in files where (doesFileExist f) do
			if (deleteFile f) do removed = true
	)
	removed
)
