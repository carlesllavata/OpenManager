-- OpenManager installer (runs when the .mzp is dropped on 3ds Max)
-- Declared before the block is compiled: inside ( ) an unknown name becomes a local (omgr_home is set by the bundle,
-- omgr_migrateLegacy by omgr_setup.ms, which is only read when this runs).
global omgr_home, omgr_migrateLegacy
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
	else if (isKindOf omgr_home String and doesDirectoryExist omgr_home) then
	(
		-- OpenManager.bundle is installed (it sets omgr_home at start): a second copy in the profile would clash with it
		messageBox ("OpenManager is already installed as a bundle:\n" + omgr_home + "\n\nThe .mzp is not needed: update OpenManager with the Open3D launcher.") title:title
	)
	else
	(
		-- an open window is closed first so its files can be replaced
		try (python.Execute "import sys\nm = sys.modules.get('openmanager')\nif m:\n    m.close()\n    for k in [k for k in list(sys.modules) if k == 'openmanager' or k.startswith('openmanager.')]:\n        del sys.modules[k]") catch()

		-- the version installed before the tool was called OpenManager ("Puzles"): removed, its settings carried over
		-- (omgr_setup.ms, shared with the bundle, which does the same when 3ds Max starts)
		fileIn (src + "OpenManager\\omgr_setup.ms")
		omgr_migrateLegacy()

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
