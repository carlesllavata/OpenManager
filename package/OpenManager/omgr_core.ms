-- OpenManager
-- MaxScript side of the tool: reads the scene and changes it for the Python window.
-- Every function is prefixed omgr_ so nothing collides with other scripts.

global omgr_rendering = false
global omgr_cancel = false
global omgr_notify -- set from Python: called with a #name when the scene changes

-- setups live inside the .max file, on a custom attribute of the root node
global omgr_attrDef = attributes omgr_attr attribID:#(0x4f4d4752, 0x5f446174)
(
	parameters main
	(
		OpenManager_Dat type:#string default:""
	)
)

-- environment maps the setups use: 3ds Max forgets a map nothing in the scene points to (when another setup replaces
-- it in the environment slot, for instance), so they are held here and saved with the file
global omgr_mapsDef = attributes omgr_maps attribID:#(0x4f4d4752, 0x5f4d6170)
(
	parameters main
	(
		OpenManager_Maps type:#textureMapTab tabSizeVariable:true
	)
)

fn omgr_keepMap m =
(
	if (m == undefined) do return false
	if (not (isProperty rootNode #OpenManager_Maps)) do custAttributes.add rootNode omgr_mapsDef
	if ((findItem rootNode.OpenManager_Maps m) == 0) do append rootNode.OpenManager_Maps m
	true
)

-- ---------------------------------------------------------------- JSON text

fn omgr_quote v =
(
	local s = v as string
	s = substituteString s "\\" "\\\\"
	s = substituteString s "\"" "\\\""
	s = substituteString s "\n" "\\n"
	s = substituteString s "\r" "\\r"
	s = substituteString s "\t" "\\t"
	"\"" + s + "\""
)

fn omgr_bool v = (if v == true then "true" else "false")

fn omgr_join items =
(
	local ss = stringStream ""
	for i = 1 to items.count do
	(
		if i > 1 do format "," to:ss
		format "%" items[i] to:ss
	)
	ss as string
)

-- ---------------------------------------------------------------- what the scene holds

fn omgr_engineName =
(
	local s = (classof renderers.current) as string
	if (matchPattern s pattern:"*V_Ray*" or matchPattern s pattern:"*VRay*") then "V-Ray"
	else if (matchPattern s pattern:"*Corona*") then "Corona"
	else if (matchPattern s pattern:"*FStorm*") then "FStorm"
	else if (matchPattern s pattern:"*Arnold*") then "Arnold"
	else s
)

fn omgr_mapFile m =
(
	local f = ""
	try (f = if (hasProperty m #filename) then m.filename else if (hasProperty m #HDRIMapName) then m.HDRIMapName else "") catch()
	if (f == undefined) then "" else (f as string)
)

-- every map below m (m included): an HDRI in a Corona Bitmap, the Color Correct on top of it, a Corona Select...
global omgr_chainInto
fn omgr_chainInto m found =
(
	if (m != undefined and (findItem found m) == 0) do
	(
		append found m
		local n = 0
		try (n = getNumSubTexmaps m) catch()
		for i = 1 to n do
		(
			local sub = undefined
			try (sub = getSubTexmap m i) catch()
			omgr_chainInto sub found
		)
	)
	found
)
fn omgr_chain m = omgr_chainInto m #()

fn omgr_isBitmapClass m = (findItem #("CoronaBitmap", "VRayHDRI", "VRayBitmap", "FStormBitmap", "Bitmaptexture") ((classof m) as string)) > 0

-- 2: an .hdr somewhere in the chain, 1: only an .exr, 0: neither
fn omgr_hdrLevel m =
(
	local best = 0
	for c in (omgr_chain m) where (omgr_isBitmapClass c) do
	(
		local ext = toLower (getFilenameType (omgr_mapFile c))
		if (ext == ".hdr") then best = 2
		else if (ext == ".exr" and best == 0) do best = 1
	)
	best
)

-- the maps that mix the tabs of the Environment card: made and kept by the tool, never offered in its list
-- (PZSM_EnvMix: the name used by the versions before OpenManager)
fn omgr_isMixMap m = (try ((matchPattern m.name pattern:"OM_EnvMix*") or (matchPattern m.name pattern:"PZSM_EnvMix*")) catch false)

fn omgr_addEnvMap found offer m yes =
(
	if (m == undefined or (omgr_isMixMap m)) do return false
	local i = findItem found m
	if (i == 0) then (append found m; append offer yes)
	else if yes do offer[i] = true
)

-- maps sitting in the Material Editors (compact slots and Slate views): not always seen as part of the scene
fn omgr_editorMaps =
(
	local out = #()
	try (for i = 1 to meditMaterials.count do (local m = meditMaterials[i]; if (superclassof m == textureMap) do appendIfUnique out m)) catch()
	try
	(
		for i = 1 to (sme.GetNumViews()) do
		(
			local v = sme.GetView i
			for j = 1 to (v.GetNumNodes()) do
			(
				local r = undefined
				try (r = (v.GetNode j).reference) catch()
				if (r != undefined and superclassof r == textureMap) do appendIfUnique out r
			)
		)
	)
	catch()
	out
)

-- Every texture map the scene uses, found by walking from what holds maps: the materials of the scene, the environment,
-- the Material Editors, the maps OpenManager keeps, and the texture-map settings of the renderer, cameras and lights.
-- One walk instead of getClassInstances per class, which scans the whole scene each time (seconds on big scenes).
global omgr_walk
fn omgr_walk m found seen =
(
	if (m == undefined) do return found
	local id = undefined
	try (id = (getHandleByAnim m) as integer) catch (return found)
	if (HasDictValue seen id) do return found
	PutDictValue seen id true
	local sc = superclassof m
	if (sc == textureMap) then
	(
		append found m
		local n = 0
		try (n = getNumSubTexmaps m) catch()
		for i = 1 to n do (local sub = undefined; try (sub = getSubTexmap m i) catch(); omgr_walk sub found seen)
	)
	else if (sc == material) do
	(
		local n = 0
		try (n = getNumSubMtls m) catch()
		for i = 1 to n do (local sub = undefined; try (sub = getSubMtl m i) catch(); omgr_walk sub found seen)
		n = 0
		try (n = getNumSubTexmaps m) catch()
		for i = 1 to n do (local sub = undefined; try (sub = getSubTexmap m i) catch(); omgr_walk sub found seen)
	)
	found
)

fn omgr_walkProps obj found seen =
(
	if (obj == undefined) do return found
	local names = #()
	try (names = getPropNames obj) catch()
	for p in names do
	(
		local v = undefined
		try (v = getProperty obj p) catch()
		if (v != undefined and (try (superclassof v == textureMap) catch false)) do omgr_walk v found seen
	)
	found
)

fn omgr_allMaps =
(
	local found = #()
	local seen = Dictionary #integer
	for m in sceneMaterials do omgr_walk m found seen
	omgr_walk environmentMap found seen
	for m in (omgr_editorMaps()) do omgr_walk m found seen
	try (for i = 1 to meditMaterials.count do omgr_walk meditMaterials[i] found seen) catch()
	if (isProperty rootNode #OpenManager_Maps) do (for m in rootNode.OpenManager_Maps do omgr_walk m found seen)
	omgr_walkProps renderers.current found seen
	for c in cameras where (superclassof c == camera) do omgr_walkProps c found seen
	for l in lights do omgr_walkProps l found seen
	found
)

-- maps the Environment card knows about, as #(maps, offered). Offered in the list: skies, bitmaps with an .hdr, and
-- colour corrections / selects with such a bitmap linked below. The others (.exr) are kept so a setup using one still works.
fn omgr_envMaps =
(
	local found = #()
	local offer = #()
	local skies = #("CoronaSky", "VRaySky", "FStormSky", "Physical_Sun___Sky_Environment")
	local wanted = #("CoronaBitmap", "VRayHDRI", "VRayBitmap", "FStormBitmap", "Bitmaptexture", "CoronaColorCorrect", "Color_Correction", "FStormColorCorrection", "CoronaSelect")
	for m in (omgr_allMaps()) do
	(
		local cls = (classof m) as string
		if ((findItem skies cls) > 0) then omgr_addEnvMap found offer m true
		else if ((findItem wanted cls) > 0) do
		(
			local lvl = omgr_hdrLevel m
			if (lvl > 0) do omgr_addEnvMap found offer m (lvl == 2)
		)
	)
	if (environmentMap != undefined) do omgr_addEnvMap found offer environmentMap true
	#(found, offer)
)

-- a map by class and name. Maps are looked up many times while setups are applied, so they are kept in a dictionary
-- (filled from omgr_allMaps, emptied when another file is opened) and checked before use.
global omgr_mapCache = undefined
fn omgr_mapOk m cls nm = (try (isValidObj m and m.name == nm and ((classof m) as string) == cls) catch false)
fn omgr_cacheMaps =
(
	omgr_mapCache = Dictionary #string
	for m in (omgr_allMaps()) do
	(
		local key = ((classof m) as string) + "|" + m.name
		if (not (HasDictValue omgr_mapCache key)) do PutDictValue omgr_mapCache key m
	)
	true
)
fn omgr_findMap cls nm =
(
	if (cls == undefined or nm == undefined) do return undefined
	local key = cls + "|" + nm
	if (omgr_mapCache == undefined) do omgr_cacheMaps()
	local m = if (HasDictValue omgr_mapCache key) then (GetDictValue omgr_mapCache key) else undefined
	if (m != undefined and not (omgr_mapOk m cls nm)) do m = undefined
	if (m == undefined) do
	(
		omgr_cacheMaps()
		m = if (HasDictValue omgr_mapCache key) then (GetDictValue omgr_mapCache key) else undefined
		if (m != undefined and not (omgr_mapOk m cls nm)) do m = undefined
	)
	if (m == undefined) do
	(
		-- a map nothing points to (not even OpenManager): the slow way, once
		local c = undefined
		try (c = execute cls) catch()
		if (c != undefined) do try (for x in (getClassInstances c) do (if (m == undefined and x.name == nm) do m = x)) catch()
		if (m != undefined) do PutDictValue omgr_mapCache key m
	)
	m
)

fn omgr_isDome l =
(
	local cls = (classof l) as string
	case cls of
	(
		"Skylight": true
		"VRayLight": (try (l.type == 1) catch false)
		"Arnold_Light": (try (l.shapeType == 6) catch false)
		default: false
	)
)

fn omgr_isSun l =
(
	(findItem #("CoronaSun", "FStormSunLight", "VRaySun", "Sun_Positioner", "DaylightAssemblyHead") ((classof l) as string)) > 0
)

-- the whole scene as one JSON text (one call is much faster than many small ones)
-- name, class, layer and visibility of these objects (geometry and shapes), as a JSON array
fn omgr_objectsInfo handles =
(
	local objs = #()
	for h in handles do
	(
		local o = maxOps.getNodeByHandle h
		if (o != undefined and (superclassof o == GeometryClass or superclassof o == shape)) do
		(
			local ln = ""
			try (ln = o.layer.name) catch()
			append objs ("{\"handle\":" + (o.inode.handle as string) + ",\"name\":" + (omgr_quote o.name) + ",\"class\":" + (omgr_quote (classof o)) + ",\"layer\":" + (omgr_quote ln) + ",\"visible\":" + (omgr_bool (not o.isNodeHidden)) + "}")
		)
	)
	"[" + (omgr_join objs) + "]"
)

-- the whole scene as one JSON text (one call is much faster than many small ones). Objects: only `handles` (the ones
-- the setups use); listing every object of a big scene each time would be slow and is not needed.
fn omgr_scene handles:#() =
(
	local cams = #()
	for c in cameras where (superclassof c == camera) do
	(
		local locked = false
		try (locked = ((getTransformLockFlags c).numberset > 0)) catch()
		append cams ("{\"handle\":" + (c.inode.handle as string) + ",\"name\":" + (omgr_quote c.name) + ",\"class\":" + (omgr_quote (classof c)) + ",\"locked\":" + (omgr_bool locked) + "}")
	)
	local shines = #()
	for l in lights where (superclassof l == light) do
	(
		local cls = (classof l) as string
		local inDaylight = (l.parent != undefined and ((classof l.parent) as string) == "DaylightAssemblyHead")
		if (cls != "Targetobject" and not inDaylight) do
		(
			local kind = if (omgr_isSun l) then "sun" else if (omgr_isDome l) then "dome" else "light"
			append shines ("{\"handle\":" + (l.inode.handle as string) + ",\"name\":" + (omgr_quote l.name) + ",\"class\":" + (omgr_quote cls) + ",\"kind\":\"" + kind + "\"}")
		)
	)
	for h in helpers do
	(
		local cls = (classof h) as string
		if (cls == "DaylightAssemblyHead" or cls == "Sun_Positioner") do
		(
			local sunCls = ""
			try (if (cls == "DaylightAssemblyHead" and h.sun != undefined) do sunCls = (classof h.sun) as string) catch()
			append shines ("{\"handle\":" + (h.inode.handle as string) + ",\"name\":" + (omgr_quote h.name) + ",\"class\":" + (omgr_quote cls) + ",\"sun_class\":" + (omgr_quote sunCls) + ",\"kind\":\"sun\"}")
		)
	)
	local maps = #()
	local envList = omgr_envMaps()
	for i = 1 to envList[1].count do
	(
		local m = envList[1][i]
		local links = #()
		for c in (omgr_chain m) do append links ("{\"name\":" + (omgr_quote c.name) + ",\"class\":" + (omgr_quote (classof c)) + ",\"path\":" + (omgr_quote (omgr_mapFile c)) + "}")
		append maps ("{\"name\":" + (omgr_quote m.name) + ",\"class\":" + (omgr_quote (classof m)) + ",\"path\":" + (omgr_quote (omgr_mapFile m)) + ",\"offer\":" + (omgr_bool envList[2][i]) + ",\"chain\":[" + (omgr_join links) + "]}")
	)
	local lays = #()
	for i = 0 to (LayerManager.count - 1) do
	(
		local ly = LayerManager.getLayer i
		local parentName = ""
		try (local p = ly.getParent(); if (p != undefined) do parentName = p.name) catch()
		append lays ("{\"name\":" + (omgr_quote ly.name) + ",\"visible\":" + (omgr_bool ly.on) + ",\"frozen\":" + (omgr_bool ly.isfrozen) + ",\"render\":" + (omgr_bool ly.renderable) + ",\"parent\":" + (omgr_quote parentName) + "}")
	)
	local total = geometry.count + shapes.count
	local xr = #()
	for i = 1 to (xrefs.getXRefFileCount()) do
	(
		local x = xrefs.getXRefFile i
		append xr ("{\"file\":" + (omgr_quote (filenameFromPath x.filename)) + ",\"path\":" + (omgr_quote x.filename) + ",\"enabled\":" + (omgr_bool (not x.disabled)) + "}")
	)
	local active = "null"
	try (local vc = viewport.getCamera(); if (vc != undefined) do active = vc.inode.handle as string) catch()
	local envName = "null"
	local envCls = "null"
	if (environmentMap != undefined) do (envName = omgr_quote environmentMap.name; envCls = omgr_quote (classof environmentMap))
	"{\"file\":" + (omgr_quote maxFileName) + ",\"folder\":" + (omgr_quote maxFilePath) + ",\"output_dir\":" + (omgr_quote (getDir #renderoutput)) \
		+ ",\"engine\":" + (omgr_quote (omgr_engineName())) + ",\"width\":" + (renderWidth as string) + ",\"height\":" + (renderHeight as string) \
		+ ",\"active_camera\":" + active + ",\"env_name\":" + envName + ",\"env_class\":" + envCls + ",\"object_total\":" + (total as string) \
		+ ",\"cameras\":[" + (omgr_join cams) + "],\"lights\":[" + (omgr_join shines) + "],\"maps\":[" + (omgr_join maps) + "],\"layers\":[" + (omgr_join lays) \
		+ "],\"objects\":" + (omgr_objectsInfo handles) + ",\"xrefs\":[" + (omgr_join xr) + "]}"
)

-- ---------------------------------------------------------------- reading and writing properties

global omgr_setPath
fn omgr_setPath obj parts idx val =
(
	local key = parts[idx] as name
	if (idx == parts.count) then
	(
		setProperty obj key val
	)
	else
	(
		local sub = getProperty obj key
		omgr_setPath sub parts (idx + 1) val
		-- plain values come back as copies and have to be written back
		if (isKindOf sub Point3 or isKindOf sub Point2 or isKindOf sub Color or isKindOf sub Point4) do setProperty obj key sub
	)
)

global omgr_getPath
fn omgr_getPath obj parts idx =
(
	local sub = getProperty obj (parts[idx] as name)
	if (idx == parts.count) then sub else (omgr_getPath sub parts (idx + 1))
)

-- the Daylight's date and time come as plain numbers from their controller, not as sub-objects
fn omgr_cleanProp prop = (if (matchPattern prop pattern:"controller.solar_*.controller.value") then (substituteString prop ".controller.value" "") else prop)

global omgr_set
fn omgr_set obj prop val =
(
	if (obj == undefined) do return false
	-- 3ds Max takes a Daylight for a group head: its settings are its own
	if (isValidNode obj and isGroupHead obj and ((classof obj) as string) != "DaylightAssemblyHead") then
	(
		for c in obj.children do omgr_set c prop val
	)
	else
	(
		local parts = filterString (omgr_cleanProp prop) "."
		local same = false
		try (same = ((omgr_getPath obj parts 1) == val)) catch()
		if (not same) do (try (omgr_setPath obj parts 1 val) catch (format "OpenManager: % . % -> %\n" obj prop (getCurrentException())))
	)
	true
)

-- returns the value, or the text "<none>" when the object doesn't have it
fn omgr_get obj prop =
(
	if (obj == undefined) do return "<none>"
	try
	(
		local v = omgr_getPath obj (filterString (omgr_cleanProp prop) ".") 1
		case (classof v) of
		(
			BooleanClass: v
			Integer: v
			Integer64: (v as integer)
			Float: v
			Double: (v as float)
			String: v
			default: "<none>"
		)
	)
	catch ("<none>")
)

fn omgr_node h = (if h == undefined then undefined else maxOps.getNodeByHandle h)

fn omgr_setNode h prop val = omgr_set (omgr_node h) prop val
fn omgr_getNode h prop = omgr_get (omgr_node h) prop
fn omgr_setLayer nm prop val = omgr_set (LayerManager.getLayerFromName nm) prop val
fn omgr_setMap cls nm prop val = omgr_set (omgr_findMap cls nm) prop val
fn omgr_getMap cls nm prop = omgr_get (omgr_findMap cls nm) prop
fn omgr_setRS prop val = omgr_set renderers.current prop val
fn omgr_getRS prop = omgr_get renderers.current prop

-- ---------------------------------------------------------------- what a setup does

-- the view locked in the Render Setup dialog (padlock on) as a viewport ID, or 0 when the render follows the active view.
-- rendViewID counts from 1, like viewport.activeViewportID.
fn omgr_lockedView = (if (not rendUseActiveView and rendViewID > 0) then rendViewID else 0)

-- puts the camera in the locked view only: the active view and a maximized layout are left as they were
fn omgr_setCameraInView n id =
(
	local prev = viewport.activeViewportID
	if (id == prev) do (viewport.setCamera n; return true)
	local wasMaxed = (viewport.numViews == 1)
	if wasMaxed do max tool maximize
	local ok = false
	try
	(
		for i = 1 to viewport.numViews while not ok do
		(
			viewport.activeViewport = i
			if (viewport.activeViewportID == id) do ok = true
		)
		if ok do viewport.setCamera n
	)
	catch()
	try (viewport.activeViewportID = prev) catch()
	if wasMaxed do max tool maximize
	if (not ok) do viewport.setCamera n -- the locked view is not in this layout any more
	true
)

-- mode 0: the active viewport; 1: only when it shows a perspective, camera or user view; 2: the locked render view
fn omgr_setCamera h locked mode:0 =
(
	local n = omgr_node h
	if (n == undefined) do return false
	local locked_id = if (mode == 2) then (omgr_lockedView()) else 0
	if (locked_id > 0) then omgr_setCameraInView n locked_id
	else
	(
		local doit = true
		if (mode == 1) do doit = (findItem #(#view_persp_user, #view_camera, #view_iso_user) (viewport.getType())) > 0
		if doit do viewport.setCamera n
	)
	local flags = if locked then #all else #none
	try (setTransformLockFlags n flags) catch()
	try (if (n.target != undefined) do setTransformLockFlags n.target flags) catch()
	true
)

fn omgr_setRes w h =
(
	if (renderWidth != w) do renderWidth = w
	if (renderHeight != h) do renderHeight = h
	true
)

fn omgr_switch obj onOff =
(
	local target = obj
	local cls = (classof obj) as string
	if (cls == "DaylightAssemblyHead" and obj.sun != undefined) then target = obj.sun
	else if (cls == "Sun_Positioner" and obj.parent != undefined) then target = obj.parent
	try
	(
		if (hasProperty target #on) then (if target.on != onOff do target.on = onOff)
		else if (hasProperty target #enabled) do (if target.enabled != onOff do target.enabled = onOff)
	)
	catch()
)

-- switch every sun (or dome) off and the chosen ones on; keep: array of handles (empty = none)
fn omgr_setLights domes keep =
(
	local keepNodes = for h in keep where (h != undefined and h >= 0) collect (omgr_node h)
	keepNodes = for n in keepNodes where (isValidNode n) collect n
	for l in lights where (superclassof l == light) do
	(
		local match = if domes then (omgr_isDome l) else (omgr_isSun l)
		-- the sun inside a Daylight that stays on is switched through its Daylight
		if (match and (findItem keepNodes l) == 0 and (l.parent == undefined or (findItem keepNodes l.parent) == 0)) do omgr_switch l false
	)
	if (not domes) do
	(
		for h in helpers where (((classof h) as string) == "DaylightAssemblyHead" and (findItem keepNodes h) == 0) do omgr_switch h false
	)
	for n in keepNodes do omgr_switch n true
	true
)

fn omgr_isFStorm = (omgr_engineName() == "FStorm")

fn omgr_setEnv cls nm sunHandle =
(
	local m = omgr_findMap cls nm
	if (m == undefined) do return false
	omgr_keepMap m
	if (omgr_isFStorm()) then
	(
		renderers.current.environment_texture_on = true
		renderers.current.environment_texture = m
		environmentMap = undefined
	)
	else
	(
		if (cls == "Physical_Sun___Sky_Environment" and sunHandle != undefined and sunHandle >= 0) do
		(
			local sn = omgr_node sunHandle
			if (sn != undefined) do try (m.sun_position_object = sn) catch()
		)
		if (environmentMap != m) do environmentMap = m
		if (not useEnvironmentMap) do useEnvironmentMap = on
	)
	true
)

-- the n-th map that mixes the environment tabs (a Corona Mix set to Add), made the first time
fn omgr_mixMap n =
(
	local nm = "OM_EnvMix_" + (formattedPrint n format:"02d")
	local m = omgr_findMap "CoronaMix" nm
	if (m == undefined) do
	(
		m = CoronaMix()
		m.name = nm
	)
	omgr_keepMap m
	m
)

fn omgr_setIf obj prop v = (if ((getProperty obj prop) != v) do setProperty obj prop v)

-- several environment tabs at once, like a LightMix: items = #(#(class, name, intensity), ...) of the tabs that are on.
-- They are added together through Corona Mix maps (Add), each one multiplied by its intensity.
fn omgr_setEnvMix items =
(
	local maps = #()
	local amounts = #()
	for it in items do
	(
		local m = omgr_findMap it[1] it[2]
		if (m != undefined) do (omgr_keepMap m; append maps m; append amounts (it[3] as float))
	)
	local top = undefined
	if (maps.count == 1 and (abs (amounts[1] - 1.0)) < 0.0001) then top = maps[1]
	else if (maps.count >= 1) do
	(
		for i = 1 to (amax 1 (maps.count - 1)) do
		(
			local mx = omgr_mixMap i
			omgr_setIf mx #mixOperation 0
			omgr_setIf mx #mixAmount 1.0
			omgr_setIf mx #mixInSRgb false
			omgr_setIf mx #texmapBottomOn true
			omgr_setIf mx #texmapBottom (if (i == 1) then maps[1] else top)
			omgr_setIf mx #multiplierBottom (if (i == 1) then amounts[1] else 1.0)
			if (maps.count == 1) then
			(
				omgr_setIf mx #texmapTop undefined
				omgr_setIf mx #texmapTopOn false
				omgr_setIf mx #colorTop (color 0 0 0)
			)
			else
			(
				omgr_setIf mx #texmapTopOn true
				omgr_setIf mx #texmapTop maps[i + 1]
				omgr_setIf mx #multiplierTop amounts[i + 1]
			)
			top = mx
		)
	)
	if (top == undefined) then environmentMap = undefined
	else
	(
		if (environmentMap != top) do environmentMap = top
		if (not useEnvironmentMap) do useEnvironmentMap = on
	)
	true
)

-- a small picture of an HDRI for the quick browser (when there is no .jpg next to it): read by 3ds Max, saved as a .jpg
fn omgr_hdriPreview src dst w h =
(
	local ok = false
	local b = undefined
	local t = undefined
	try
	(
		b = openBitmap src
		if (b != undefined) do
		(
			t = bitmap w h color:black
			copy b t
			t.filename = dst
			save t
			ok = doesFileExist dst
		)
	)
	catch (format "OpenManager: preview of % -> %\n" src (getCurrentException()))
	try (if (t != undefined) do close t) catch()
	try (if (b != undefined) do close b) catch()
	ok
)

fn omgr_envOff =
(
	environmentMap = undefined
	if (omgr_isFStorm()) do
	(
		try (renderers.current.environment_texture_on = false) catch()
		try (renderers.current.environment_texture = undefined) catch()
	)
	true
)

fn omgr_setOutput path =
(
	if (path == "") then
	(
		rendSaveFile = false
		rendOutputFilename = ""
	)
	else
	(
		rendSaveFile = true
		rendOutputFilename = path
		-- render elements of Corona and FStorm follow the main file: name_element.ext
		local eng = omgr_engineName()
		if (eng == "Corona" or eng == "FStorm") do
		(
			local re = maxOps.GetCurRenderElementMgr()
			for i = 0 to (re.NumRenderElements() - 1) do
			(
				local e = re.GetRenderElement i
				local pieces = filterString (getFilenameFile path) "."
				local frameText = pieces[pieces.count]
				if (pieces.count > 1 and (frameText as integer) != undefined) then
				(
					local stem = pieces[1]
					for u = 2 to (pieces.count - 1) do stem += "." + pieces[u]
					re.SetRenderElementFilename i ((getFilenamePath path) + stem + "_" + e.elementname + "." + frameText + (getFilenameType path))
				)
				else
				(
					re.SetRenderElementFilename i ((getFilenamePath path) + (getFilenameFile path) + "_" + e.elementname + (getFilenameType path))
				)
			)
		)
	)
	true
)

fn omgr_makeDir path =
(
	local d = getFilenamePath path
	if (d != "" and not (doesDirectoryExist d)) do makeDir d all:true
	true
)

-- kind: 0 single, 1 range, 2 list
fn omgr_setTime kind single start end nth list setType:true =
(
	case kind of
	(
		0:
		(
			local f = single as time
			if (f < animationRange.start) then animationRange = interval f animationRange.end
			else if (f > animationRange.end) then animationRange = interval animationRange.start f
			sliderTime = f
			if setType do rendTimeType = 1
		)
		1:
		(
			local s = start as time
			local e = end as time
			if (e > s) do animationRange = interval s e
			rendStart = s
			rendEnd = e
			sliderTime = s
			rendNThFrame = amax 1 nth
			if setType do rendTimeType = 3
		)
		2:
		(
			rendPickupFrames = list
			if setType do rendTimeType = 4
		)
	)
	true
)

fn omgr_setXref file onOff =
(
	for i = 1 to (xrefs.getXRefFileCount()) do
	(
		local x = xrefs.getXRefFile i
		if ((filenameFromPath x.filename) == file) do
		(
			if (x.disabled == onOff) do x.disabled = (not onOff)
			if (x.hidden == onOff) do x.hidden = (not onOff)
		)
	)
	true
)

-- before a render: the camera goes to the locked view through omgr_setCamera (mode 2), the active view stays
fn omgr_renderView =
(
	try (renderSceneDialog.close()) catch()
	true
)

-- ---------------------------------------------------------------- saved setups

-- Files saved by the versions before the name OpenManager ("Puzles") keep their setups and maps in attributes with
-- the old names below. They are read like ours, and removed from the file the first time it is saved with this version.
global omgr_oldDat = "PuzlesSM_Dat"
global omgr_oldMaps = "PuzlesSM_Maps"

fn omgr_dropLegacy =
(
	local datKey = omgr_oldDat as name
	local mapsKey = omgr_oldMaps as name
	if (isProperty rootNode mapsKey) do
	(
		try (for m in (getProperty rootNode mapsKey) where (m != undefined) do omgr_keepMap m) catch()
	)
	for i = (custAttributes.count rootNode) to 1 by -1 do
	(
		local ca = custAttributes.get rootNode i
		if (ca != undefined and ((isProperty ca datKey) or (isProperty ca mapsKey))) do custAttributes.delete rootNode i
	)
	true
)

fn omgr_saveSetups data =
(
	if (not (isProperty rootNode #OpenManager_Dat)) do custAttributes.add rootNode omgr_attrDef
	if (rootNode.OpenManager_Dat != data) do
	(
		rootNode.OpenManager_Dat = data
		setSaveRequired true
	)
	if ((isProperty rootNode (omgr_oldDat as name)) or (isProperty rootNode (omgr_oldMaps as name))) do
	(
		omgr_dropLegacy()
		setSaveRequired true
	)
	true
)

fn omgr_readKey key =
(
	if (isProperty rootNode key) then ((getProperty rootNode key) as string) else ""
)

-- ---------------------------------------------------------------- cameras

fn omgr_newCamera =
(
	local cam = undefined
	local eng = omgr_engineName()
	try
	(
		if (eng == "Corona") then cam = (execute "CoronaCam()")
		else if (eng == "V-Ray") then cam = (execute "VRayPhysicalCamera()")
	)
	catch()
	if (cam == undefined) do cam = Physical()
	try (cam.transform = (inverse (getViewTM()))) catch()
	try (cam.name = uniqueName "OM_Camera") catch()
	viewport.setCamera cam
	cam.inode.handle
)

fn omgr_selectedHandles = (for o in selection collect o.inode.handle)

fn omgr_selectHandles hs =
(
	local ns = for h in hs collect (omgr_node h)
	ns = for n in ns where (isValidNode n) collect n
	if (ns.count > 0) then select ns else clearSelection()
	true
)

-- ---------------------------------------------------------------- render

fn omgr_render =
(
	omgr_cancel = false
	omgr_rendering = true
	local failed = undefined
	try
	(
		try (renderSceneDialog.close()) catch()
		SetQuietMode true
		try (clearFrameBuffer()) catch()
		max quick render
	)
	catch
	(
		failed = getCurrentException()
	)
	SetQuietMode false
	omgr_rendering = false
	if (failed != undefined) then failed else (if omgr_cancel then "canceled" else "done")
)

fn omgr_checkAbort =
(
	try (if ((dotNetClass "Autodesk.Max.GlobalInterface").Instance.COREInterface13.CheckForRenderAbort) do omgr_cancel = true) catch()
)

fn omgr_stop =
(
	omgr_cancel = true
	try ((dotNetClass "Autodesk.Max.GlobalInterface").Instance.COREInterface13.AbortRender()) catch()
	try (CoronaRenderer.CoronaFp.stopRender()) catch()
	try (vrayEndProgressiveRender()) catch()
	true
)

-- ---------------------------------------------------------------- more modules

-- viewport background: 1 gradient, 2 solid, 3 environment, 4 custom file
fn omgr_setBackground kind path =
(
	case kind of
	(
		1: (try (viewport.EnableSolidBackgroundColorMode false) catch(); viewport.DispBkgImage = false)
		2: (try (viewport.EnableSolidBackgroundColorMode true) catch(); viewport.DispBkgImage = false)
		3: (backgroundImageFileName = ""; viewport.DispBkgImage = true)
		4:
		(
			if (path != "" and doesFileExist path) do
			(
				backgroundImageFileName = path
				try (setAsBackground (openBitmap path)) catch()
			)
			viewport.DispBkgImage = true
		)
	)
	true
)

fn omgr_atmospherics =
(
	local items = #()
	for i = 1 to numAtmospherics do
	(
		local a = getAtmospheric i
		append items ("{\"name\":" + (omgr_quote a.name) + ",\"class\":" + (omgr_quote (classof a)) + ",\"active\":" + (omgr_bool (isActive a)) + "}")
	)
	"[" + (omgr_join items) + "]"
)

fn omgr_setAtmos nm onOff =
(
	for i = 1 to numAtmospherics do
	(
		local a = getAtmospheric i
		if (a.name == nm and (isActive a) != onOff) do setActive a onOff
	)
	true
)

fn omgr_elements =
(
	local re = maxOps.GetCurRenderElementMgr()
	local items = #()
	for i = 0 to (re.NumRenderElements() - 1) do
	(
		local e = re.GetRenderElement i
		append items ("{\"name\":" + (omgr_quote e.elementName) + ",\"class\":" + (omgr_quote (classof e)) + ",\"enabled\":" + (omgr_bool e.enabled) + "}")
	)
	"[" + (omgr_join items) + "]"
)

fn omgr_setElement nm onOff =
(
	local re = maxOps.GetCurRenderElementMgr()
	for i = 0 to (re.NumRenderElements() - 1) do
	(
		local e = re.GetRenderElement i
		if (e.elementName == nm and e.enabled != onOff) do e.enabled = onOff
	)
	true
)

fn omgr_loadPreset path =
(
	if (path != "" and doesFileExist path) then
	(
		try (renderSceneDialog.close()) catch()
		renderPresets.LoadAll 0 path
	)
	else false
)

fn omgr_savePreset path =
(
	makeDir (getFilenamePath path) all:true
	renderPresets.SaveAll 0 path
)

-- the renderer's plain settings as JSON (for Render Settings - Override)
fn omgr_rsSnapshot =
(
	local r = renderers.current
	local items = #()
	for n in (getPropNames r) do
	(
		local v = undefined
		try (v = getProperty r n) catch()
		local c = classof v
		local txt = case c of
		(
			BooleanClass: (omgr_bool v)
			Integer: (v as string)
			Float: (if (bit.isNAN v) then undefined else (v as string))
			String: (omgr_quote v)
			default: undefined
		)
		if (txt != undefined) do append items ((omgr_quote n) + ":" + txt)
	)
	"{" + (omgr_join items) + "}"
)

fn omgr_runCode code =
(
	if (code != undefined and code != "") do
	(
		try (execute code) catch (format "OpenManager script: %\n" (getCurrentException()))
	)
	true
)

global omgr_preRenderFile = ""
global omgr_postRenderFile = ""
global omgr_preRenderCode = ""
global omgr_postRenderCode = ""
fn omgr_preRender =
(
	if (omgr_preRenderFile != "" and doesFileExist omgr_preRenderFile) do (try (fileIn omgr_preRenderFile) catch (format "OpenManager pre-render script: %\n" (getCurrentException())))
	omgr_runCode omgr_preRenderCode
)
fn omgr_postRender =
(
	if (omgr_postRenderFile != "" and doesFileExist omgr_postRenderFile) do (try (fileIn omgr_postRenderFile) catch (format "OpenManager post-render script: %\n" (getCurrentException())))
	omgr_runCode omgr_postRenderCode
)
fn omgr_setRenderScripts preFile postFile preCode postCode =
(
	omgr_preRenderFile = preFile
	omgr_postRenderFile = postFile
	omgr_preRenderCode = preCode
	omgr_postRenderCode = postCode
	callbacks.removeScripts id:#omgrRender
	if (preFile != "" or preCode != "") do callbacks.addScript #preRender "omgr_preRender()" id:#omgrRender
	if (postFile != "" or postCode != "") do callbacks.addScript #postRender "omgr_postRender()" id:#omgrRender
	true
)

-- Corona post-production (tone mapping, bloom & glare, sharpening, LUT...) through the VFB's own .conf files
fn omgr_postSave path = (try (CoronaRenderer.CoronaFp.savePostSettings path) catch (-1))
fn omgr_postLoad path = (try (CoronaRenderer.CoronaFp.loadPostSettings path) catch (-1))

fn omgr_snapshotViewport path =
(
	makeDir (getFilenamePath path) all:true
	local b = gw.getViewportDib()
	b.filename = path
	save b
	close b
	true
)

fn omgr_snapshotVfb path =
(
	local b = undefined
	try (b = getLastRenderedImage copy:true) catch()
	if (b == undefined) then false else
	(
		makeDir (getFilenamePath path) all:true
		b.filename = path
		save b
		close b
		true
	)
)

fn omgr_isRendering =
(
	local t = 0
	try (t = CoronaRenderer.CoronaFp.getRenderType()) catch()
	t
)

-- every texture map in the scene, as "class|name" lines (for map settings such as camera overrides)
fn omgr_texmaps =
(
	local ss = stringStream ""
	for m in (omgr_allMaps()) do format "%|%\n" ((classof m) as string) m.name to:ss
	ss as string
)

fn omgr_findTexmap cls nm = omgr_findMap cls nm

-- Batch Render (3ds Max's own) from setups: a scene state and a view per setup
fn omgr_batchView camHandle viewName stateName presetPath outPath w h =
(
	local cam = omgr_node camHandle
	if (cam == undefined) do return false
	local i = batchRenderMgr.FindView viewName
	if (i != 0) do batchRenderMgr.DeleteView i
	local v = batchRenderMgr.CreateView cam
	v.name = viewName
	if (stateName != "") do (sceneStateMgr.Delete stateName; sceneStateMgr.CaptureAllParts stateName; v.sceneStateName = stateName)
	if (presetPath != "") do v.presetFile = presetPath
	v.overridePreset = true
	v.width = w
	v.height = h
	if (outPath != "") do v.outputFilename = outPath
	true
)

-- ---------------------------------------------------------------- environment / lights helpers

fn omgr_samePath a b = (toLower (substituteString a "/" "\\")) == (toLower (substituteString b "/" "\\"))

-- the bitmap map of this file: one that is already in the scene, or a new one named after the file
fn omgr_hdriBitmap path =
(
	local eng = omgr_engineName()
	local classes = if (eng == "Corona") then #("CoronaBitmap") else if (eng == "V-Ray") then #("VRayBitmap", "VRayHDRI") else #("Bitmaptexture")
	for n in classes do
	(
		for m in (omgr_allMaps()) where (((classof m) as string) == n and (omgr_samePath (omgr_mapFile m) path)) do return m
	)
	local m = undefined
	try
	(
		if (eng == "Corona") then (m = execute "CoronaBitmap()"; m.filename = path)
		else if (eng == "V-Ray") then (m = execute "VRayBitmap()"; m.HDRIMapName = path)
	)
	catch()
	if (m == undefined) do (m = Bitmaptexture(); m.filename = path)
	m.name = getFilenameFile path
	m
)

-- a colour correction (or select) over an HDRI: a copy of it over the new HDRI, so its settings stay and other setups keep theirs
global omgr_wrapHdri
fn omgr_wrapHdri m bmp =
(
	if (omgr_isBitmapClass m) do return bmp
	local n = 0
	try (n = getNumSubTexmaps m) catch()
	for i = 1 to n do
	(
		local sub = undefined
		try (sub = getSubTexmap m i) catch()
		if (sub != undefined and (omgr_hdrLevel sub) > 0) do
		(
			local nm = (filterString m.name "@")[1] + "@" + bmp.name
			local have = omgr_findMap ((classof m) as string) nm
			if (have != undefined) do return have
			local c = copy m
			setSubTexmap c i (omgr_wrapHdri sub bmp)
			c.name = nm
			return c
		)
	)
	bmp
)

-- double click in the HDRI browser: returns the map the environment uses now
fn omgr_useHdri path curCls curName =
(
	local bmp = omgr_hdriBitmap path
	local cur = if (curCls != "" and curCls != undefined) then (omgr_findMap curCls curName) else undefined
	local m = if (cur != undefined and not (omgr_isBitmapClass cur) and (omgr_hdrLevel cur) > 0) then (omgr_wrapHdri cur bmp) else bmp
	omgr_keepMap m
	"{\"class\":" + (omgr_quote (classof m)) + ",\"name\":" + (omgr_quote m.name) + "}"
)

fn omgr_newHdri path =
(
	local m = omgr_hdriBitmap path
	omgr_keepMap m
	environmentMap = m
	useEnvironmentMap = on
	"{\"class\":" + (omgr_quote (classof m)) + ",\"name\":" + (omgr_quote m.name) + "}"
)

fn omgr_newSky =
(
	local eng = omgr_engineName()
	local m = undefined
	try
	(
		if (eng == "Corona") then m = execute "CoronaSky()"
		else if (eng == "V-Ray") then m = execute "VRaySky()"
	)
	catch()
	if (m == undefined) do m = Physical_Sun___Sky_Environment()
	m.name = uniqueName "OM_Sky_"
	omgr_keepMap m
	environmentMap = m
	useEnvironmentMap = on
	"{\"class\":" + (omgr_quote (classof m)) + ",\"name\":" + (omgr_quote m.name) + "}"
)

fn omgr_showInMedit cls nm =
(
	local m = omgr_findMap cls nm
	if (m == undefined) do return false
	try (meditMaterials[activeMeditSlot] = m) catch()
	try (MatEditor.Open()) catch()
	true
)

-- the layers selected in a Layer / Scene Explorer; else the layers of the selected objects; else the active layer
fn omgr_selectedLayers =
(
	local names = #()
	try
	(
		for i = 1 to (SceneExplorerManager.GetExplorerCount()) do
		(
			local nm0 = SceneExplorerManager.GetExplorerName i
			local ex = if (SceneExplorerManager.ExplorerIsOpen nm0) then (SceneExplorerManager.GetExplorer nm0) else undefined
			if (ex != undefined) do
			(
				for it in (ex.SelectedItems()) where (not (isValidNode it)) do
				(
					local nm = undefined
					try (nm = it.name) catch()
					if (nm != undefined and (LayerManager.getLayerFromName nm) != undefined) do appendIfUnique names nm
				)
			)
		)
	)
	catch()
	if (names.count == 0) do (for o in selection do appendIfUnique names o.layer.name)
	if (names.count == 0) do (try (append names LayerManager.current.name) catch())
	names
)

-- ---------------------------------------------------------------- base state (what a setup changed, to put it back)

-- any value of a property (undefined when there is none); the Python side decides what it can store
fn omgr_getRaw obj prop =
(
	if (obj == undefined) then undefined
	else (try (omgr_getPath obj (filterString (omgr_cleanProp prop) ".") 1) catch undefined)
)
fn omgr_getRawNode h prop = omgr_getRaw (omgr_node h) prop
fn omgr_getRawLayer nm prop = omgr_getRaw (LayerManager.getLayerFromName nm) prop
fn omgr_getRawMap cls nm prop = omgr_getRaw (omgr_findMap cls nm) prop
fn omgr_getRawRS prop = omgr_getRaw renderers.current prop

-- on/off of a sun, dome or Daylight as omgr_switch sees it
fn omgr_getOn h =
(
	local obj = omgr_node h
	if (obj == undefined) do return undefined
	local target = obj
	local cls = (classof obj) as string
	if (cls == "DaylightAssemblyHead" and obj.sun != undefined) then target = obj.sun
	else if (cls == "Sun_Positioner" and obj.parent != undefined) then target = obj.parent
	try
	(
		if (hasProperty target #on) then target.on
		else if (hasProperty target #enabled) then target.enabled
		else undefined
	)
	catch undefined
)
fn omgr_setOn h onOff = (local n = omgr_node h; if (n != undefined) do omgr_switch n onOff; true)

-- is the transform of this camera locked (as the Camera card's padlock sets it)
fn omgr_isLocked h = (local n = omgr_node h; (n != undefined) and (try ((getTransformLockFlags n).numberset > 0) catch false))

-- time output: #(range start, range end, slider, rendTimeType, rendStart, rendEnd, nth frame, frame list), in frames
fn omgr_getTime = #(animationRange.start.frame, animationRange.end.frame, sliderTime.frame, rendTimeType, \
	rendStart.frame, rendEnd.frame, rendNThFrame, rendPickupFrames)
fn omgr_setTimeRaw t =
(
	local s = (t[1] as integer) as time
	local e = (t[2] as integer) as time
	if (e > s) do animationRange = interval s e
	sliderTime = (t[3] as integer) as time
	rendTimeType = t[4] as integer
	rendStart = (t[5] as integer) as time
	rendEnd = (t[6] as integer) as time
	rendNThFrame = amax 1 (t[7] as integer)
	rendPickupFrames = t[8] as string
	true
)

-- render output: #(save file, file name, #(file name of every render element))
fn omgr_getOutputRaw =
(
	local re = maxOps.GetCurRenderElementMgr()
	#(rendSaveFile, rendOutputFilename, for i = 0 to (re.NumRenderElements() - 1) collect ((re.GetRenderElementFilename i) as string))
)
fn omgr_setOutputRaw save nm elems =
(
	rendSaveFile = save
	rendOutputFilename = nm
	local re = maxOps.GetCurRenderElementMgr()
	for i = 0 to (amin (re.NumRenderElements() - 1) (elems.count - 1)) do re.SetRenderElementFilename i elems[i + 1]
	true
)

-- environment slot: #(class, name, use environment map); class "" when the slot is empty
fn omgr_getEnvRaw =
(
	local m = if (omgr_isFStorm()) then (try renderers.current.environment_texture catch undefined) else environmentMap
	if (m == undefined) then #("", "", useEnvironmentMap) else #((classof m) as string, m.name, useEnvironmentMap)
)
fn omgr_setEnvRaw cls nm use =
(
	if (cls == "") then omgr_envOff() else omgr_setEnv cls nm -1
	useEnvironmentMap = use
	true
)

fn omgr_getXref file =
(
	for i = 1 to (xrefs.getXRefFileCount()) do
	(
		local x = xrefs.getXRefFile i
		if ((filenameFromPath x.filename) == file) do return (not x.disabled)
	)
	undefined
)

fn omgr_getAtmos nm =
(
	for i = 1 to numAtmospherics do (local a = getAtmospheric i; if (a.name == nm) do return (isActive a))
	undefined
)

fn omgr_getElement nm =
(
	local re = maxOps.GetCurRenderElementMgr()
	for i = 0 to (re.NumRenderElements() - 1) do (local e = re.GetRenderElement i; if (e.elementName == nm) do return e.enabled)
	undefined
)

-- ---------------------------------------------------------------- scene events

fn omgr_fire what = (if (what == #preopen or what == #file) do omgr_mapCache = undefined; if (omgr_notify != undefined) do (try (omgr_notify what) catch (format "OpenManager: %\n" (getCurrentException()))))

fn omgr_watch onOff =
(
	callbacks.removeScripts id:#omgr
	if onOff do
	(
		callbacks.addScript #filePreOpen "omgr_fire #preopen" id:#omgr
		callbacks.addScript #systemPreReset "omgr_fire #preopen" id:#omgr
		callbacks.addScript #systemPreNew "omgr_fire #preopen" id:#omgr
		callbacks.addScript #filePostOpen "omgr_fire #file" id:#omgr
		callbacks.addScript #systemPostReset "omgr_fire #file" id:#omgr
		callbacks.addScript #systemPostNew "omgr_fire #file" id:#omgr
		callbacks.addScript #filePostMerge "omgr_fire #scene" id:#omgr
		callbacks.addScript #filePreSave "omgr_fire #presave" id:#omgr
		callbacks.addScript #nodeCreated "omgr_fire #scene" id:#omgr
		callbacks.addScript #nodePostDelete "omgr_fire #scene" id:#omgr
		callbacks.addScript #nodeRenamed "omgr_fire #scene" id:#omgr
		callbacks.addScript #layerCreated "omgr_fire #scene" id:#omgr
		callbacks.addScript #layerDeleted "omgr_fire #scene" id:#omgr
		callbacks.addScript #postRendererChange "omgr_fire #scene" id:#omgr
		callbacks.addScript #postRender "omgr_checkAbort()" id:#omgr
		try (callbacks.addScript #viewportChange "omgr_fire #view" id:#omgr) catch()
		callbacks.addScript #preSystemShutdown "omgr_fire #shutdown" id:#omgr
	)
	true
)

ok
