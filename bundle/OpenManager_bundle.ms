-- SPDX-License-Identifier: GPL-3.0-or-later
-- OpenManager.bundle start: the bundle's post-start-up script (3ds Max 2025 and later).
-- Points the OpenManager action at this bundle, cleans up older installs (the "Puzles" version and the per-user .mzp
-- install) and adds the file-open check of OpenManager_startup.ms.
-- Declared here, before the block is compiled: inside ( ) an unknown name becomes a local, so the functions fileIn
-- defines below would be undefined locals when called.
global omgr_home, omgr_migrateLegacy, omgr_removeMzpInstall
(
	local here = getFilenamePath (getThisScriptFilename())
	omgr_home = pathConfig.normalizePath (here + "..\\OpenManager")
	try
	(
		fileIn (omgr_home + "\\omgr_setup.ms")
		omgr_migrateLegacy()
		-- 3ds Max loads usermacros before the bundles' macroscripts, so the bundle's OpenManager macro already won
		if (omgr_removeMzpInstall()) do
			format "OpenManager: the older .mzp install was removed; OpenManager now runs from %\n" omgr_home
	)
	catch (format "OpenManager: clean-up of older installs failed: %\n" (getCurrentException()))
	fileIn (omgr_home + "\\OpenManager_startup.ms")
)
