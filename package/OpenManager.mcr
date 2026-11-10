-- OpenManager
-- Customize User Interface > Group: Main UI > Category: OpenManager > OpenManager
-- Used by both installs: OpenManager.bundle sets omgr_home when 3ds Max starts; the .mzp installs to userScripts.
global omgr_home

macroScript OpenManager
	category:"OpenManager"
	internalCategory:"OpenManager"
	buttonText:"OpenManager"
	toolTip:"OpenManager: scene setups and batch render"
	iconName:"OpenManager"
(
	on isChecked return (omgr_isOpen == true)

	on execute do
	(
		local dir = if (isKindOf omgr_home String and doesDirectoryExist omgr_home) then omgr_home else ((getDir #userScripts) + "\\OpenManager")
		if (not (doesDirectoryExist dir)) then
		(
			messageBox "OpenManager is not installed.\nInstall it again with the Open3D launcher, or drag OpenManager.mzp into 3ds Max." title:"OpenManager"
		)
		else
		(
			python.Execute ("import sys\nd = r'" + dir + "'\nif d not in sys.path: sys.path.insert(0, d)\nimport openmanager\nopenmanager.toggle()")
		)
	)
)
