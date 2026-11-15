-- Mute one friend (#169), per character or for all of a player's characters.
-- "Log only" keeps their updates in the activity log, records and leaderboard
-- and skips only the notification. "Hide completely" also leaves them out of
-- every page that shows or counts the log (WoWStatusJournal.visible), and out of
-- the leaderboard. The log itself keeps every entry, so unmuting brings it all
-- back. Purely local and account-wide: nothing about a mute is ever sent, and
-- delivery confirmations, list sharing and log relays work exactly as before,
-- so the muted friend can never tell.
WoWStatusMutes = {}
local M, S = WoWStatusMutes, WoWStatusSafe
local T = WoWStatusLocale.T
M.MODES = {"show", "log", "hide"}
M.LABELS = {show="Show popups", log="Log only", hide="Hide completely"}
-- How much each mode mutes: the stronger of a character's and its player's wins.
local STRENGTH = {show=0, log=1, hide=2}
M.MAX = 200 -- Saved mutes per kind (characters, players).
local db, frame
local revision, cache = 0, nil

-- Saved mutes as {players={[playerID]=item}, characters={[characterKey]=item}},
-- item = {mode="log"|"hide", name=, at=}. Anything else is dropped on load.
local function clean(map)
    local result, count = {}, 0
    if type(map) ~= "table" then return result end
    for id, item in pairs(map) do
        if count >= M.MAX then break end
        if type(id) == "string" and #id > 0 and #id <= 160 and type(item) == "table"
            and (item.mode == "log" or item.mode == "hide") then
            local name = S.string(item.name)
            result[id] = {mode=item.mode, name=name and name:sub(1, 120) or nil, at=S.number(item.at)}
            count = count + 1
        end
    end
    return result
end
local function state()
    if not db then return nil end
    if type(db.mutes) ~= "table" then db.mutes = {} end
    local mutes = db.mutes
    if type(mutes.players) ~= "table" then mutes.players = {} end
    if type(mutes.characters) ~= "table" then mutes.characters = {} end
    return mutes
end

function M.init(database)
    db = database
    if type(db.mutes) == "table" then
        db.mutes = {players=clean(db.mutes.players), characters=clean(db.mutes.characters)}
    end
    revision, cache = revision + 1, nil
end

local function characterKey(name)
    return WoWStatusRoster and WoWStatusRoster.key and WoWStatusRoster.key(name) or nil
end
local function playerID(name)
    return WoWStatusRoster and WoWStatusRoster.playerIdOf and WoWStatusRoster.playerIdOf(name) or nil
end
local function stronger(a, b) return STRENGTH[b] > STRENGTH[a] and b or a end

-- The effective mode for a sender: "show", "log" or "hide". This account's own
-- characters are never muted.
function M.mode(sender)
    local mutes = state()
    if not mutes or (next(mutes.characters) == nil and next(mutes.players) == nil) then return "show" end
    if WoWStatusPopups and WoWStatusPopups.isSelf and WoWStatusPopups.isSelf(sender) then return "show" end
    local mode, k = "show", characterKey(sender)
    local item = k and mutes.characters[k]
    if item then mode = stronger(mode, item.mode) end
    local id = next(mutes.players) ~= nil and playerID(sender)
    item = id and mutes.players[id]
    if item then mode = stronger(mode, item.mode) end
    return mode
end
-- What one entry of the list says about a character or player, "show" if none.
function M.get(kind, id)
    local mutes = state()
    local map = mutes and (kind == "player" and mutes.players or mutes.characters)
    local item = map and type(id) == "string" and map[id]
    return item and item.mode or "show"
end
function M.popupsMuted(sender) return M.mode(sender) ~= "show" end

-- Character keys hidden right now: rebuilt when mutes change, and at most every
-- few seconds as players' character lists change. Checked for every log entry
-- on each page render, so it must stay cheap.
local CACHE_SECONDS = 5
function M.hidden(sender)
    local mutes = state()
    if not mutes then return false end
    local now = time()
    if not cache or cache.revision ~= revision or now - cache.at >= CACHE_SECONDS then
        cache = {revision=revision, at=now, keys={}, any=false}
        for k, item in pairs(mutes.characters) do
            if item.mode == "hide" then cache.keys[k] = true; cache.any = true end
        end
        local roster = db.roster and type(db.roster.players) == "table" and db.roster.players or {}
        for id, item in pairs(mutes.players) do
            local player = item.mode == "hide" and roster[id]
            if type(player) == "table" and type(player.characters) == "table" then
                for k in pairs(player.characters) do cache.keys[k] = true; cache.any = true end
            end
        end
    end
    if not cache.any then return false end
    local k = characterKey(sender)
    return k ~= nil and cache.keys[k] == true
end

local function refresh()
    revision, cache = revision + 1, nil
    if WoWStatusRoster and WoWStatusRoster.render then WoWStatusRoster.render() end
    if WoWStatusJournal and WoWStatusJournal.redraw then WoWStatusJournal.redraw() end
    if WoWStatusMainWindow and WoWStatusMainWindow.refresh then
        for _, page in ipairs({"overview", "records", "leaderboard"}) do WoWStatusMainWindow.refresh(page) end
    end
    if WoWStatusProfile and WoWStatusProfile.refreshMute then WoWStatusProfile.refreshMute() end
    if frame and frame:IsShown() then M.render() end
end

-- Set a mute: kind "character" (id = WoWStatusRoster.key) or "player" (their
-- random player ID); mode "show" removes it. Returns true when saved.
function M.set(kind, id, mode, name)
    local mutes = state()
    if not mutes or (kind ~= "character" and kind ~= "player") or type(id) ~= "string" or id == ""
        or #id > 160 or not STRENGTH[mode] then return false end
    local map = kind == "player" and mutes.players or mutes.characters
    if mode == "show" then
        map[id] = nil
    else
        if not map[id] then
            local count = 0
            for _ in pairs(map) do count = count + 1 end
            if count >= M.MAX then return false end
        end
        name = S.string(name)
        map[id] = {mode=mode, name=name and name:sub(1, 120) or (map[id] and map[id].name), at=time()}
    end
    refresh()
    return true
end
-- Mute a sender's character by name.
function M.setCharacter(name, mode)
    local k = characterKey(name)
    return k ~= nil and M.set("character", k, mode, name)
end

-- Every mute, players first, then by name: {kind, id, mode, name}.
function M.list()
    local mutes, list = state(), {}
    if not mutes then return list end
    local roster = db.roster and type(db.roster.players) == "table" and db.roster.players or {}
    for id, item in pairs(mutes.players) do
        local player = roster[id]
        local name = type(player) == "table" and S.string(player.name) or item.name or T("Unnamed player")
        list[#list + 1] = {kind="player", id=id, mode=item.mode, name=name}
    end
    for id, item in pairs(mutes.characters) do
        list[#list + 1] = {kind="character", id=id, mode=item.mode, name=item.name or id}
    end
    table.sort(list, function(a, b)
        if a.kind ~= b.kind then return a.kind == "player" end
        if S.lowerASCII(a.name) ~= S.lowerASCII(b.name) then return S.lowerASCII(a.name) < S.lowerASCII(b.name) end
        return a.id < b.id
    end)
    return list
end
function M.count()
    local mutes, count = state(), 0
    if not mutes then return 0 end
    for _ in pairs(mutes.players) do count = count + 1 end
    for _ in pairs(mutes.characters) do count = count + 1 end
    return count
end

-- The menu choices for a friend's character and, when known, their player.
function M.choices(name)
    local items = {}
    for _, mode in ipairs(M.MODES) do
        items[#items + 1] = {label=T(M.LABELS[mode]), value={kind="character", mode=mode}}
    end
    local id = playerID(name)
    local player = id and WoWStatusRoster.playerOf and WoWStatusRoster.playerOf(name)
    if id then
        local who = player and player:gsub("|", "||") or T("this player")
        for _, mode in ipairs(M.MODES) do
            items[#items + 1] = {label=T("All characters of") .. " " .. who .. ": " .. T(M.LABELS[mode]):lower(),
                value={kind="player", id=id, mode=mode, name=player}}
        end
    end
    return items
end
function M.pick(name, choice)
    if type(choice) ~= "table" then return false end
    if choice.kind == "player" then return M.set("player", choice.id, choice.mode, choice.name) end
    return M.setCharacter(name, choice.mode)
end

-- The list of muted friends: a small window named WoWStatusMutedFriends (B closes it),
-- one row per mute with a mode button and Unmute, in a ScrollFrame.
local ROW = 34
local function button(parent, label, x, y, width, onClick)
    local widget = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    widget:SetPoint("TOPLEFT", x, y); widget:SetSize(width, 26); widget:SetText(T(label))
    widget:SetScript("OnClick", onClick)
    return widget
end
local function text(parent, font, x, y, width)
    local f = parent:CreateFontString(nil, "OVERLAY", font)
    f:SetPoint("TOPLEFT", x, y); f:SetWidth(width); f:SetJustifyH("LEFT")
    return f
end
local function build()
    frame = CreateFrame("Frame", "WoWStatusMutedFriends", UIParent)
    frame:SetSize(560, 420); frame:SetPoint("CENTER"); frame:SetFrameStrata("FULLSCREEN_DIALOG")
    frame:EnableMouse(true)
    local background = frame:CreateTexture(nil, "BACKGROUND")
    background:SetAllPoints(); background:SetColorTexture(.025, .035, .055, .96)
    if WoWStatusTheme and WoWStatusTheme.attachBackground then WoWStatusTheme.attachBackground(background) end
    frame.title = text(frame, "GameFontHighlightLarge", 24, -20, 500)
    frame.title:SetText(T("Muted friends"))
    frame.help = text(frame, "GameFontHighlightSmall", 24, -50, 510)
    frame.help:SetText(T("Muted friends stay in your groups. Log only keeps their updates in the log without popups; Hide completely also leaves them out of the log, records and leaderboard. Nothing is sent and they are never told."))
    frame.scroll = CreateFrame("ScrollFrame", nil, frame, "UIPanelScrollFrameTemplate")
    frame.scroll:SetPoint("TOPLEFT", 24, -104); frame.scroll:SetSize(500, 260)
    frame.list = CreateFrame("Frame", nil, frame.scroll); frame.list:SetSize(480, 1)
    frame.scroll:SetScrollChild(frame.list)
    frame.empty = text(frame, "GameFontDisable", 24, -110, 500)
    frame.empty:SetText(T("Nobody is muted. Mute a friend from their profile on the Characters page."))
    frame.rows = {}
    frame.close = button(frame, "Close", 404, -380, 130, function() frame:Hide() end)
    if UISpecialFrames then table.insert(UISpecialFrames, "WoWStatusMutedFriends") end
end
local function row(index)
    local r = CreateFrame("Frame", nil, frame.list)
    r:SetSize(480, ROW); r:SetPoint("TOPLEFT", 0, -(index - 1) * ROW)
    r.name = text(r, "GameFontHighlight", 0, -8, 230)
    r.mode = button(r, "", 236, -2, 140, function(self)
        local item = self:GetParent().item
        if not item then return end
        local items = {}
        for _, mode in ipairs(M.MODES) do
            if mode ~= "show" then items[#items + 1] = {label=T(M.LABELS[mode]), value=mode} end
        end
        if WoWStatusUI and WoWStatusUI.menu then
            WoWStatusUI.menu(self, items, function(mode) M.set(item.kind, item.id, mode) end)
        else
            M.set(item.kind, item.id, item.mode == "log" and "hide" or "log")
        end
    end)
    r.unmute = button(r, "Unmute", 382, -2, 96, function(self)
        local item = self:GetParent().item
        if item then M.set(item.kind, item.id, "show") end
    end)
    frame.rows[index] = r
    return r
end
function M.render()
    if not frame then return end
    local list = M.list()
    for i, item in ipairs(list) do
        local r = frame.rows[i] or row(i)
        r.item = item
        local name = item.name:gsub("|", "||")
        r.name:SetText(item.kind == "player" and (name .. " (" .. T("all characters") .. ")") or (name:match("^[^-]+") or name))
        r.mode:SetText(T(M.LABELS[item.mode]))
        r:Show()
    end
    for i = #list + 1, #frame.rows do frame.rows[i]:Hide(); frame.rows[i].item = nil end
    frame.list:SetHeight(math.max(1, #list * ROW))
    frame.empty:SetShown(#list == 0)
end
function M.show()
    if not frame then build() end
    M.render()
    frame:Show()
    return frame
end
