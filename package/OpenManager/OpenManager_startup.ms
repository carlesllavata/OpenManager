-- SPDX-License-Identifier: GPL-3.0-or-later
-- OpenManager: when a file with setups of Pulze Scene Manager is opened and the window is closed, offer to open it.
-- (Settings > Notification turns this off.)
global omgr_home
global omgr_isOpen
global omgr_settingsDir
global omgr_startupCheck
-- First the folders (openmanager/folders.py): the settings are in %APPDATA%\Open3D\OpenManager. At the first start
-- the ones of the plugcfg folder of the newest 3ds Max are copied there, before anything reads them, and
-- omgr_settingsDir says where they are. The package is in the bundle (omgr_home) or in the user's scripts (.mzp).
try (python.Execute "import os, sys\nfrom pymxs import runtime as rt\nd = rt.omgr_home if isinstance(rt.omgr_home, str) and os.path.isdir(rt.omgr_home) else os.path.join(rt.getDir(rt.Name('userScripts')), 'OpenManager')\nif d not in sys.path: sys.path.insert(0, d)\nfrom openmanager import folders\nfolders.session()")
catch (format "OpenManager: the Open3D folders could not be set up: %\n" (getCurrentException()))
fn omgr_startupCheck =
(
    try
    (
        local flag = if (isKindOf omgr_settingsDir String) then (omgr_settingsDir + "\\OpenManager_notify.txt") else ""
        local wanted = true
        if (flag != "" and doesFileExist flag) do
        (
            local f = openFile flag
            if (f != undefined) do (wanted = ((readLine f) != "0"); close f)
        )
        -- Only a file whose setups are still the ones of Pulze Scene Manager is announced (to convert them). Once the file
        -- has setups of its own nothing is asked: they always win over the old Pulze ones, which are never read again.
        local ours = (isProperty rootNode #OpenManager_Dat) and ((rootNode.OpenManager_Dat as string).count > 60)
        -- setups saved by the versions before the name OpenManager count as ours too
        if (isProperty rootNode #PuzlesSM_Dat) do ours = true
        local pulze = (isProperty rootNode #SceneManager_Dat) and (((getProperty rootNode #SceneManager_Dat) as string).count > 25)
        if (wanted and pulze and not ours and omgr_isOpen != true and not (GetQuietMode()) and not (IsNetServer())) do
        (
            if (queryBox "This file has setups of Pulze Scene Manager.\nOpen OpenManager to use them?" title:"OpenManager") do macros.run "OpenManager" "OpenManager"
        )
    )
    catch()
)
callbacks.removeScripts id:#omgrStartup
callbacks.addScript #filePostOpen "omgr_startupCheck()" id:#omgrStartup
