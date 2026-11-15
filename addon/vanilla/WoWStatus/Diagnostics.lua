-- Diagnostics (#153): the addon's own Lua errors, kept so a player can copy them
-- into a bug report, plus the numbers a report always needs. Loaded first, so an
-- error in any later file is caught too.
--
-- The game's error handler is chained, never replaced: every error still reaches
-- whatever the player already uses (the game's own error frame, BugSack and so
-- on). BugGrabber stops other addons from setting a handler; with it, errors come
-- from its "BugGrabber_BugGrabbed" callback instead. Only errors from WoW Status
-- files are kept: the last MAX_ERRORS, a repeat counted on its first copy, in
-- WoWStatusDB.diagnostics so they survive a /reload and a crash. Group names and
-- character names are taken out before anything is stored or shown, and nothing
-- is ever sent anywhere. The report stays English, as diagnostics do.
WoWStatusDiagnostics = {}
local D = WoWStatusDiagnostics
local MAX_ERRORS, MAX_MESSAGE, MAX_STACK, MAX_STACK_LINES = 10, 600, 2400, 24
D.MAX_ERRORS = MAX_ERRORS
-- Errors raised before SavedVariables are readable: the game loads them only
-- after every file of the addon has run.
local pending = {}
local lastEntry, busy, previous, installed = nil, nil, false, nil, false
local registered, page

local function account()
    if type(WoWStatusDB) ~= "table" then return nil end
    if type(WoWStatusDB.diagnostics) ~= "table" then WoWStatusDB.diagnostics = {} end
    local data = WoWStatusDB.diagnostics
    if type(data.errors) ~= "table" then data.errors = {} end
    return data
end
local function now()
    local ok, value = pcall(time)
    return ok and type(value) == "number" and value or 0
end
local function stamp(at)
    if type(at) ~= "number" or at <= 0 then return "?" end
    local ok, text = pcall(function() return date("!%Y-%m-%d %H:%M:%S", at) end)
    return ok and type(text) == "string" and (text .. " UTC") or "?"
end
local function cut(text, limit)
    if #text <= limit then return text end
    return text:sub(1, limit - 3) .. "..."
end

-- Whether a path names a file of this addon (or its voice pack). Paths look like
-- "Interface/AddOns/WoWStatus/Popups.lua", "Interface\AddOns\WoWStatus\..." or,
-- shortened by BugGrabber, "WoWStatus/Popups.lua".
local function ownPath(text)
    return text:find("^@?WoWStatus[/\\]") ~= nil or text:find("[^A-Za-z0-9_]WoWStatus[/\\]") ~= nil
        or text:find("^@?WoWStatus_Voices[/\\]") ~= nil or text:find("[^A-Za-z0-9_]WoWStatus_Voices[/\\]") ~= nil
end
D.ownPath = ownPath
-- Folders whose frames say nothing about which addon caused an error: the game's
-- own code and the error collectors.
local NEUTRAL = {Interface=true, FrameXML=true, SharedXML=true, AddOns=true,
    ["!BugGrabber"]=true, BugGrabber=true, BugSack=true}
-- The addon folder of the first stack frame that is not the game's own code.
local function firstAddon(stack)
    for line in stack:gmatch("[^\n]+") do
        -- "path.lua:12:", or bracketed: [string "@path.lua"]:12: and [path.lua]:12:
        local path = line:match("([^ \t%[%]\"']+)%.lua[\"%]]*:%d")
        if path then
            path = path:gsub("^@", "")
            local folder = path:match("[Aa][Dd][Dd][Oo][Nn][Ss][/\\]([^/\\]+)") or path:match("^([^/\\]+)[/\\]")
            if folder and not NEUTRAL[folder] and not folder:find("^Blizzard_") then return folder end
        end
    end
end
-- An error is ours when its message names one of our files, or when the first
-- addon frame in its stack is ours (a bad argument we passed to the game's code).
function D.ours(message, stack)
    if type(message) ~= "string" then return false end
    if ownPath(message) then return true end
    local folder = type(stack) == "string" and firstAddon(stack)
    return folder == "WoWStatus" or folder == "WoWStatus_Voices"
end

-- The stack, bounded. own: it comes from our handler, whose frames lead it and
-- say nothing; only those leading frames go (an error in this file's page code
-- keeps its frames).
local function cleanStack(stack, own)
    if type(stack) ~= "string" then return "" end
    local lines, leading = {}, own
    for line in stack:gmatch("[^\n]+") do
        if leading and line:find("WoWStatus[/\\]Diagnostics%.lua") then
        elseif #lines < MAX_STACK_LINES then
            leading = false
            lines[#lines + 1] = line
        end
    end
    return table.concat(lines, "\n")
end

-- Redaction --------------------------------------------------------------
-- Bytes that continue a word: ASCII letters and digits, and every byte of a
-- UTF-8 character (names like "Åsa"). Comparisons use ASCII lowercase only
-- (see WoWStatusSafe on locale-dependent string functions).
local function wordByte(byte)
    return byte ~= nil and (byte >= 128 or (byte >= 48 and byte <= 57) or (byte >= 65 and byte <= 90)
        or (byte >= 97 and byte <= 122))
end
-- A match that is part of a file path ("WoWStatus/Groups.lua") is left alone,
-- so a friend called Groups does not hide which file failed.
local function inPath(text, s, e)
    local before, after = text:sub(s - 1, s - 1), text:sub(e + 1, e + 4)
    return before == "/" or before == "\\" or after == ".lua" or after:sub(1, 1) == "/"
end
-- Replace every whole-word occurrence of word with mark. Group names compare in
-- any ASCII case (as group IDs do); character names exactly, so a friend called
-- Value never turns "a nil value" into "a nil <name>".
local function replaceWord(text, word, mark, anyCase)
    local lower = WoWStatusSafe.lowerASCII
    local folded, needle = text, word
    if anyCase then folded, needle = lower(text), lower(word) end
    local out, init, from = {}, 1, 1
    while true do
        local s, e = folded:find(needle, init, true)
        if not s then break end
        if not wordByte(folded:byte(s - 1)) and not wordByte(folded:byte(e + 1)) and not inPath(text, s, e) then
            out[#out + 1] = text:sub(from, s - 1); out[#out + 1] = mark
            from = e + 1
        end
        init = e + 1
    end
    if from == 1 then return text end
    out[#out + 1] = text:sub(from)
    return table.concat(out)
end
-- Every group name, group ID, group channel, character name and private ID this
-- account knows, each with the mark that replaces it, longest first.
local function secrets()
    local list, seen = {}, {}
    local db, S, G = WoWStatusDB, WoWStatusSafe, WoWStatusGroups
    if type(db) ~= "table" or type(S) ~= "table" then return list end
    local function add(value, mark)
        if type(value) ~= "string" then return end
        value = S.trim(value)
        if value == "" or #value > 120 or seen[value] then return end
        seen[value] = true
        list[#list + 1] = {value, mark, mark ~= "<name>"}
    end
    local function group(id, label)
        add(label, "<group>")
        if type(id) == "string" then
            add(id, "<group>")
            if type(G) == "table" and G.channel then add(G.channel(id), "<group channel>") end
        end
    end
    local function name(value)
        if type(value) ~= "string" then return end
        add(value, "<name>")
        add(value:match("^([^-]+)%-"), "<name>")
    end
    for id, label in pairs(type(db.account_groups) == "table" and db.account_groups or {}) do group(id, label) end
    for id in pairs(type(db.listed_groups) == "table" and db.listed_groups or {}) do group(id) end
    local popups = type(db.popups) == "table" and db.popups or {}
    for channel in pairs(type(popups.joined_channels) == "table" and popups.joined_channels or {}) do
        add(channel, "<group channel>")
    end
    add(popups.channel, "<group channel>")
    add(db.player_name, "<name>")
    for _, character in pairs(type(db.characters) == "table" and db.characters or {}) do
        if type(character) == "table" then
            for id, member in pairs(type(character.group_ids) == "table" and character.group_ids or {}) do
                group(id, type(member) == "table" and member.label or nil)
            end
            local identity = type(character.identity) == "table" and character.identity or {}
            name(identity.name)
            add(character.player_name, "<name>")
            add(character.claim_secret, "<secret>")
        end
    end
    local journal = type(db.journal) == "table" and type(db.journal.entries) == "table" and db.journal.entries or {}
    for _, entry in ipairs(journal) do
        if type(entry) == "table" then name(entry.sender); name(entry.relay); name(entry.via) end
    end
    local roster = type(db.roster) == "table" and db.roster or {}
    add(roster.id, "<secret>")
    for pid, player in pairs(type(roster.players) == "table" and roster.players or {}) do
        add(pid, "<secret>")
        if type(player) == "table" then
            add(player.name, "<name>")
            for _, character in pairs(type(player.characters) == "table" and player.characters or {}) do
                if type(character) == "table" then name(character.name) end
            end
        end
    end
    for _, record in pairs(type(roster.equipment_cache) == "table" and roster.equipment_cache or {}) do
        if type(record) == "table" then name(record.name) end
    end
    table.sort(list, function(a, b) return #a[1] > #b[1] end)
    return list
end
-- During an error storm the list is built at most every few seconds.
local cachedSecrets, cachedAt = nil, nil
local function recentSecrets()
    local at = now()
    if not cachedSecrets or not cachedAt or math.abs(at - cachedAt) >= 5 then
        cachedSecrets, cachedAt = secrets(), at
    end
    return cachedSecrets
end
-- text with every known secret replaced by a mark such as "<group>".
function D.redact(text, list)
    if type(text) ~= "string" or text == "" then return text end
    for _, secret in ipairs(list or secrets()) do text = replaceWord(text, secret[1], secret[2], secret[3]) end
    return text
end

-- Capture ------------------------------------------------------------------
local function errors()
    local data = account()
    return data and data.errors or pending
end
-- Move errors caught before SavedVariables loaded into them.
local function flush()
    local data = account()
    if not data or #pending == 0 then return end
    local list, hidden = data.errors, secrets()
    for i = #pending, 1, -1 do
        local entry = pending[i]
        -- Names were unknown when it was caught: hide them before it is stored.
        entry.message = cut(D.redact(entry.message, hidden), MAX_MESSAGE)
        entry.stack = cut(D.redact(entry.stack, hidden), MAX_STACK)
        local merged = false
        for _, saved in ipairs(list) do
            if type(saved) == "table" and saved.message == entry.message then
                saved.count = (tonumber(saved.count) or 1) + (entry.count or 1)
                saved.last_at = math.max(tonumber(saved.last_at) or 0, entry.last_at or 0)
                saved.unseen = true
                if lastEntry == entry then lastEntry = saved end
                merged = true
                break
            end
        end
        if not merged then table.insert(list, 1, entry) end
    end
    while #list > MAX_ERRORS do table.remove(list) end
    pending = {}
end
D.flush = flush

local function edition()
    local A = WoWStatusAdapter
    if type(A) ~= "table" then return "unknown" end
    return tostring(A.display_name or "unknown") .. " (" .. tostring(A.client_id or "?") .. ")"
end
local function addonVersion()
    local P = WoWStatusPopups
    if type(P) == "table" and type(P.runtimeVersion) == "string" then return P.runtimeVersion end
    local lookup = type(C_AddOns) == "table" and C_AddOns.GetAddOnMetadata or rawget(_G, "GetAddOnMetadata")
    local ok, value = pcall(lookup, "WoWStatus", "Version")
    return ok and type(value) == "string" and value or "unknown"
end
local function clientBuild()
    if type(GetBuildInfo) ~= "function" then return "unknown" end
    local ok, version, build, _, interface = pcall(GetBuildInfo)
    if not ok then return "unknown" end
    return tostring(version or "?") .. " build " .. tostring(build or "?") .. " (interface " .. tostring(interface or "?") .. ")"
end
local function openPage()
    local M = WoWStatusMainWindow
    local ok, key = pcall(function() return M and M.active and M.active() end)
    return ok and type(key) == "string" and key or "none"
end

-- Raw messages seen lately, each with its entry (false: not ours). An error
-- raised every frame (an OnUpdate script) arrives sixty times a second, maybe
-- taking turns with another: a repeat only counts.
local recent, recentCount, RECENT_MAX = {}, 0, 32
local function remember(message, entry)
    if recent[message] == nil then
        if recentCount >= RECENT_MAX then recent, recentCount = {}, 0 end
        recentCount = recentCount + 1
    end
    recent[message] = entry or false
end
-- Record one error. Returns the entry, or nil when it was not ours. own: the
-- stack comes from our handler (its leading frames are dropped).
function D.capture(message, stack, own)
    if type(message) ~= "string" then message = tostring(message) end
    local known = recent[message]
    if known == false then return nil end
    if known then
        -- Still listed (not cleared, evicted or merged): it only counts.
        local list = errors()
        for i, saved in ipairs(list) do
            if saved == known then
                if i > 1 then table.remove(list, i); table.insert(list, 1, known) end
                known.count = (tonumber(known.count) or 1) + 1
                known.last_at, known.unseen = now(), true
                return known
            end
        end
    end
    stack = cleanStack(stack, own)
    if not D.ours(message, stack) then remember(message, false); return nil end
    flush()
    local list, hidden, at = errors(), account() and recentSecrets() or {}, now()
    local text = cut(D.redact(message, hidden), MAX_MESSAGE)
    for i, saved in ipairs(list) do
        if type(saved) == "table" and saved.message == text then
            table.remove(list, i); table.insert(list, 1, saved)
            saved.count = (tonumber(saved.count) or 1) + 1
            saved.last_at, saved.unseen = at, true
            lastEntry = saved
            remember(message, saved)
            return saved
        end
    end
    -- Before SavedVariables load nothing is known to hide; flush() redacts then.
    local entry = {message=text, stack=cut(D.redact(stack, hidden), MAX_STACK), count=1, at=at, last_at=at, unseen=true,
        version=addonVersion(), edition=edition(), build=clientBuild(), page=openPage()}
    table.insert(list, 1, entry)
    while #list > MAX_ERRORS do table.remove(list) end
    lastEntry = entry
    remember(message, entry)
    return entry
end

-- The chained handler: record, then hand the error on unchanged.
local function handler(message, ...)
    if not busy then
        busy = true
        local stack = type(debugstack) == "function" and debugstack(2, MAX_STACK_LINES, 0) or nil
        pcall(D.capture, message, stack, true)
        busy = false
    end
    if previous then return previous(message, ...) end
end
D.handler = handler
-- Chain once, at load. Re-chaining later could loop through a handler that
-- already calls ours.
local function install()
    if installed or type(seterrorhandler) ~= "function" or type(geterrorhandler) ~= "function" then return end
    installed = true
    previous = geterrorhandler()
    pcall(seterrorhandler, handler)
end
install()
-- Whether our handler is the game's current one. False with BugGrabber, which
-- makes seterrorhandler do nothing for other addons, and when an addon loaded
-- later put its own handler on top (it may still pass errors on to ours).
function D.chained()
    return type(geterrorhandler) == "function" and geterrorhandler() == handler
end
local listening = false
local function listenToBugGrabber()
    if listening or D.chained() then return end
    local grabber = rawget(_G, "BugGrabber")
    if type(grabber) ~= "table" or type(grabber.RegisterCallback) ~= "function" then return end
    local ok = pcall(grabber.RegisterCallback, D, "BugGrabber_BugGrabbed", function(_, err)
        if type(err) == "table" then pcall(D.capture, err.message, err.stack) end
    end)
    listening = ok
end
-- !BugGrabber always loads before us: listen at once, so errors in our later
-- files are caught too.
listenToBugGrabber()

-- Counts and report ----------------------------------------------------------
local function count(map)
    local n = 0
    for _ in pairs(type(map) == "table" and map or {}) do n = n + 1 end
    return n
end
-- The numbers a bug report always needs. Never a name: groups only as a count.
function D.facts()
    local db = type(WoWStatusDB) == "table" and WoWStatusDB or {}
    local facts = {version=addonVersion(), edition=edition(), build=clientBuild(), own=0, received=0, gear=0}
    if type(UpdateAddOnMemoryUsage) == "function" and type(GetAddOnMemoryUsage) == "function"
        and not (type(InCombatLockdown) == "function" and InCombatLockdown()) then
        pcall(UpdateAddOnMemoryUsage)
        local ok, kb = pcall(GetAddOnMemoryUsage, "WoWStatus")
        if ok and type(kb) == "number" then facts.memory = kb end
    end
    local journal = type(db.journal) == "table" and type(db.journal.entries) == "table" and db.journal.entries or {}
    for _, entry in ipairs(journal) do
        if type(entry) == "table" then
            if entry.owner then facts.own = facts.own + 1 else facts.received = facts.received + 1 end
        end
    end
    local roster = type(db.roster) == "table" and db.roster or {}
    for _, record in pairs(type(roster.equipment_cache) == "table" and roster.equipment_cache or {}) do
        if type(record) == "table" and record.snapshot then facts.gear = facts.gear + 1 end
    end
    local groups = type(db.account_groups) == "table" and db.account_groups or {}
    facts.groups = count(groups)
    facts.channel = false
    local P = WoWStatusPopups
    if type(P) == "table" and type(P.joinedChannel) == "function" then
        for id in pairs(groups) do
            local ok, joined = pcall(P.joinedChannel, id)
            if ok and joined then facts.channel = true end
        end
    end
    return facts
end

function D.errors() flush(); return errors() end
function D.unseen()
    local n = 0
    for _, entry in ipairs(D.errors()) do if type(entry) == "table" and entry.unseen then n = n + 1 end end
    return n
end
function D.markSeen()
    for _, entry in ipairs(D.errors()) do if type(entry) == "table" then entry.unseen = nil end end
end
function D.clear()
    pending, lastEntry, recent, recentCount = {}, nil, {}, 0
    local data = account()
    if data then data.errors = {} end
end

local function field(value) return type(value) == "string" and value ~= "" and value or "?" end
-- The whole report as plain English text, redacted once more against the
-- current groups and names in case they changed since an error was stored.
function D.report()
    local facts, list, hidden = D.facts(), D.errors(), secrets()
    local lines = {
        "WoW Status diagnostics",
        "Addon: " .. facts.version .. " - " .. facts.edition,
        "Client: " .. facts.build,
        "Memory: " .. (facts.memory and string.format("%.0f KB", facts.memory) or "unknown"),
        "Saved log: " .. facts.own .. " own entries, " .. facts.received .. " received",
        "Cached gear snapshots: " .. facts.gear,
        "Groups joined: " .. facts.groups .. " - group channel joined: " .. (facts.channel and "yes" or "no"),
        "Error capture: " .. (D.chained() and "chained" or listening and "via BugGrabber"
            or installed and "another addon's handler is on top" or "unavailable"),
        "Generated: " .. stamp(now()),
        "",
    }
    local shown = 0
    for _, entry in ipairs(list) do
        if type(entry) == "table" and type(entry.message) == "string" then
            shown = shown + 1
            local times = tonumber(entry.count) or 1
            lines[#lines + 1] = "#" .. shown .. " - " .. times .. (times == 1 and " time" or " times")
                .. " - first " .. stamp(entry.at) .. " - last " .. stamp(entry.last_at or entry.at)
            lines[#lines + 1] = "Version " .. field(entry.version) .. " - " .. field(entry.edition)
                .. " - client " .. field(entry.build) .. " - page " .. field(entry.page)
            lines[#lines + 1] = D.redact(entry.message, hidden)
            if type(entry.stack) == "string" and entry.stack ~= "" then
                lines[#lines + 1] = "Stack:"
                lines[#lines + 1] = D.redact(entry.stack, hidden)
            end
            lines[#lines + 1] = ""
        end
    end
    if shown == 0 then lines[#lines + 1] = "No errors recorded." end
    return table.concat(lines, "\n")
end

-- The page --------------------------------------------------------------------
local function render()
    if not page then return end
    local T, F = WoWStatusLocale.T, WoWStatusLocale.F
    local unseen = D.unseen()
    page.status:SetText(unseen == 1 and T("1 error recorded since you last looked.")
        or unseen > 1 and F("%d errors recorded since you last looked.", unseen)
        or T("No new errors since you last looked."))
    -- "|" starts an escape in an edit box; doubled it shows as itself.
    page.report = D.report()
    page.box:SetText((page.report:gsub("|", "||")))
    if page.box.SetCursorPosition then page.box:SetCursorPosition(0) end
    if page.scroll.SetVerticalScroll then page.scroll:SetVerticalScroll(0) end
    if page.clear.SetEnabled then page.clear:SetEnabled(#D.errors() > 0) end
    D.markSeen()
end
D.render = render

local function build(parent)
    local T = WoWStatusLocale.T
    page = CreateFrame("Frame", "WoWStatusDiagnosticsPage", parent); page:SetAllPoints(parent)
    page.heading = page:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    page.heading:SetPoint("TOPLEFT", 24, -12); page.heading:SetText(T("Diagnostics"))
    page.status = page:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    page.status:SetPoint("TOPLEFT", 24, -40); page.status:SetWidth(730); page.status:SetJustifyH("LEFT")
    page.hint = page:CreateFontString(nil, "OVERLAY", "GameFontDisable")
    page.hint:SetPoint("TOPLEFT", 24, -62); page.hint:SetWidth(730); page.hint:SetJustifyH("LEFT")
    page.hint:SetText(T("Copy this report into a bug report on GitHub or Discord. Nothing is sent automatically."))
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -88); page.scroll:SetSize(706, 392)
    -- Read-only but selectable: typing is undone, so the text stays whole for copying.
    page.box = CreateFrame("EditBox", nil, page.scroll)
    page.box:SetMultiLine(true); page.box:SetAutoFocus(false); page.box:SetFontObject("GameFontHighlightSmall")
    page.box:SetWidth(690); page.box:SetHeight(392)
    page.box:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    page.box:SetScript("OnTextChanged", function(self, user)
        if user and page.report then self:SetText((page.report:gsub("|", "||"))) end
    end)
    page.scroll:SetScrollChild(page.box)
    page.select = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.select:SetPoint("TOPLEFT", 24, -494); page.select:SetSize(160, 26); page.select:SetText(T("Select all"))
    page.select:SetScript("OnClick", function()
        page.box:SetFocus()
        if page.box.HighlightText then page.box:HighlightText() end
    end)
    page.clear = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.clear:SetPoint("TOPLEFT", 196, -494); page.clear:SetSize(160, 26); page.clear:SetText(T("Clear errors"))
    page.clear:SetScript("OnClick", function() D.clear(); render() end)
    return page
end

-- The page has no tab (the tab row is full): /wstatus errors and the Options
-- button open it. Registered once the main window's file has loaded.
local function register()
    if registered or type(WoWStatusMainWindow) ~= "table" then return end
    registered = WoWStatusMainWindow.register("diagnostics", "Diagnostics", build, render, {tab=false}) and true
end
function D.show()
    register()
    if WoWStatusMainWindow then return WoWStatusMainWindow.show("diagnostics") end
end
function D.page() return page end

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("PLAYER_LOGOUT")
events:SetScript("OnEvent", function(_, event, name)
    if event == "ADDON_LOADED" and name ~= "WoWStatus" then return end
    register()
    listenToBugGrabber()
    flush()
end)
