-- SPDX-License-Identifier: GPL-3.0-or-later
-- OpenManager
-- Customize User Interface > Group: Main UI > Category: OpenManager > OpenManager
-- OpenManager.bundle sets omgr_home when 3ds Max starts. A copy in userScripts is what the retired .mzp left, until the
-- bundle removes it.
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
            messageBox "OpenManager is not installed.\nInstall it again with the Open3D launcher." title:"OpenManager"
        )
        else
        (
            python.Execute ("import sys\nd = r'" + dir + "'\nif d not in sys.path: sys.path.insert(0, d)\nimport openmanager\nopenmanager.toggle()")
        )
    )
)
