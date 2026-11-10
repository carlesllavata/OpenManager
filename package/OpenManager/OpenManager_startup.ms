-- SPDX-License-Identifier: GPL-3.0-or-later
-- OpenManager: when a file with setups of Pulze Scene Manager is opened and the window is closed, offer to open it.
-- (Settings > Notification turns this off.)
global omgr_isOpen
global omgr_startupCheck
fn omgr_startupCheck =
(
	try
	(
		local flag = (getDir #plugcfg) + "\\OpenManager_notify.txt"
		local wanted = true
		if (doesFileExist flag) do
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
