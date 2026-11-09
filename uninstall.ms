-- OpenManager: removes everything the .mzp installed (run it from Scripting > Run Script).
-- The setups stored inside .max files are left as they are.
(
	try (python.Execute "import sys\nm = sys.modules.get('openmanager')\nif m:\n    m.close()") catch()
	callbacks.removeScripts id:#omgr
	callbacks.removeScripts id:#omgrRender
	callbacks.removeScripts id:#omgrStartup

	local omUnDelTree
	fn omUnDelTree dir =
	(
		for f in (getFiles (dir + "*")) do deleteFile f
		for d in (getDirectories (dir + "*")) do omUnDelTree d
		try ((dotNetClass "System.IO.Directory").Delete (trimRight dir "\\/") true) catch()
	)

	omUnDelTree ((getDir #userScripts) + "\\OpenManager\\")
	local gone = #(
		(getDir #userMacros) + "\\OpenManager.mcr",
		(getDir #userStartupScripts) + "\\OpenManager_startup.ms",
		(getDir #plugcfg) + "\\OpenManager.json",
		(getDir #plugcfg) + "\\OpenManager_default.json",
		(getDir #plugcfg) + "\\OpenManager_notify.txt"
	)
	for theme in #("Dark", "Light") do
		for f in (getFiles ((getDir #userIcons) + "\\" + theme + "\\OpenManager_*.png")) do append gone f
	for f in gone where (doesFileExist f) do deleteFile f
	try ((dotNetClass "System.IO.Directory").Delete ((getDir #plugcfg) + "\\OpenManager_hdri") true) catch()
	messageBox "OpenManager was removed.\nRestart 3ds Max to drop it from the menus and toolbars." title:"OpenManager"
)
