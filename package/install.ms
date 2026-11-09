-- OpenManager installer (runs when the .mzp is dropped on 3ds Max)
(
	local title = "OpenManager"
	local src = getFilenamePath (getSourceFileName())

	local omInstCopyTree
	fn omInstCopyTree fromDir toDir =
	(
		makeDir toDir all:true
		for f in (getFiles (fromDir + "*")) do
		(
			local target = toDir + (filenameFromPath f)
			if (doesFileExist target) do deleteFile target
			copyFile f target
		)
		for d in (getDirectories (fromDir + "*")) do
		(
			local leaf = pathConfig.stripPathToLeaf (trimRight d "\\/")
			if (leaf != "__pycache__") do omInstCopyTree d (toDir + leaf + "\\")
		)
	)

	if ((maxVersion())[1] < 27000) then
	(
		messageBox "OpenManager needs 3ds Max 2025 or newer (Python 3 + PySide6)." title:title
	)
	else
	(
		-- an open window is closed first so its files can be replaced
		try (python.Execute "import sys\nm = sys.modules.get('openmanager')\nif m:\n    m.close()\n    for k in [k for k in list(sys.modules) if k == 'openmanager' or k.startswith('openmanager.')]:\n        del sys.modules[k]") catch()

		-- the version installed before the tool was called OpenManager ("Puzles"): closed and removed, its settings
		-- carried over. Setups saved inside .max files by that version are read and converted by the tool itself.
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

		local dst = (getDir #userScripts) + "\\OpenManager\\"
		omInstCopyTree (src + "OpenManager\\") dst

		-- small startup script: offers to open the window when a file with Pulze setups is opened
		local su = (getDir #userStartupScripts) + "\\OpenManager_startup.ms"
		if (doesFileExist su) do deleteFile su
		copyFile (dst + "OpenManager_startup.ms") su
		try (fileIn su) catch()

		-- icons for the light and the dark theme
		for theme in #("Dark", "Light") do
		(
			local idir = (getDir #userIcons) + "\\" + theme + "\\"
			makeDir idir all:true
			for f in (getFiles (src + "icons\\" + theme + "\\*.png")) do
			(
				local target = idir + (filenameFromPath f)
				if (doesFileExist target) do deleteFile target
				copyFile f target
			)
		)

		-- the macro: copied so 3ds Max loads it on every start, and run now so it is there straight away
		local mcr = (getDir #userMacros) + "\\OpenManager.mcr"
		if (doesFileExist mcr) do deleteFile mcr
		copyFile (src + "OpenManager.mcr") mcr
		fileIn mcr
		try (colorMan.reInitIcons()) catch()

		local msg = "OpenManager is installed.\n\n"
		msg += "Customize > Customize User Interface\n"
		msg += "Group: Main UI   Category: OpenManager\n"
		msg += "Action: OpenManager\n\n"
		msg += "Drag it to a toolbar or a menu. Open it now?"
		if (queryBox msg title:title) do macros.run "OpenManager" "OpenManager"
	)
)
