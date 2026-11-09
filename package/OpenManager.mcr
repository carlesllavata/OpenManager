-- OpenManager
-- Customize User Interface > Group: Main UI > Category: OpenManager > OpenManager

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
		local dir = (getDir #userScripts) + "\\OpenManager"
		if (not (doesDirectoryExist dir)) then
		(
			messageBox "OpenManager is not installed.\nDrag OpenManager.mzp into 3ds Max again." title:"OpenManager"
		)
		else
		(
			python.Execute ("import sys\nd = r'" + dir + "'\nif d not in sys.path: sys.path.insert(0, d)\nimport openmanager\nopenmanager.toggle()")
		)
	)
)
