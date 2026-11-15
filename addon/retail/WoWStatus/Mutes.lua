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
M.MAX_KNOWN = 40 -- Character keys remembered per muted player.
local db, frame
local revision, cache = 0, nil

-- Saved mutes as {players={[playerID]=item}, characters={[characterKey]=item}},
-- item = {mode="log"|"hide", name=, at=}; a player's item also remembers the
-- character keys seen under that player (characters={key,...}), so the mute
-- holds when their list is forgotten (sharing turned off, or pushed out by newer
-- players). Anything else is dropped on load.
local function keys(list)
    local result = {}
    if type(list) ~= "table" then return result end
    for _, k in ipairs(list) do
        if #result >= M.MAX_KNOWN then break end
        if type(k) == "string" and #k > 0 and #k <= 160 then result[#result + 1] = k end
    end
    return result
end
local function clean(map, player)
    local result, count = {}, 0
    if type(map) ~= "table" then return result, 0 end
    for id, item in pairs(map) do
        if count >= M.MAX then break end
        if type(id) == "string" and #id > 0 and #id <= 160 and type(item) == "table"
            and (item.mode == "log" or item.mode == "hide") then
            local name = S.string(item.name)
            result[id] = {mode=item.mode, name=name and name:sub(1, 120) or nil, at=S.number(item.at),
                characters=player and keys(item.characters) or nil}
            count = count + 1
        end
    end
    return result, count
end
-- The saved mutes, or nil when there are none; only M.set creates them.
local function state()
    local mutes = db and db.mutes
    if type(mutes) ~= "table" or type(mutes.players) ~= "table" or type(mutes.characters) ~= "table"
        or (next(mutes.players) == nil and next(mutes.characters) == nil) then return nil end
    return mutes
end

function M.init(database)
    db = database
    if db.mutes ~= nil then
        local saved = type(db.mutes) == "table" and db.mutes or {}
        local players, a = clean(saved.players, true)
        local characters, b = clean(saved.characters, false)
        db.mutes = a + b > 0 and {players=players, characters=characters} or nil
    end
    revision, cache = revision + 1, nil
end

local function characterKey(name)
    return WoWStatusRoster and WoWStatusRoster.key and WoWStatusRoster.key(name) or nil
end
local function playerID(name)
    return WoWStatusRoster and WoWStatusRoster.playerIdOf and WoWStatusRoster.playerIdOf(name) or nil
end
local function stronger(a, b) return a and STRENGTH[a] >= STRENGTH[b] and a or b end

-- The mode of every muted character key, the strongest of its own setting and
-- its players' (one character can be listed under two player IDs after a
-- reinstall; both count). Rebuilt when mutes change and at most every few
-- seconds as character lists change: it is read for every log entry on each
-- page render, so it must stay cheap.
local CACHE_SECONDS = 5
local function modes()
    local mutes = state()
    if not mutes then return nil end
    local now = time()
    if cache and cache.revision == revision and now - cache.at < CACHE_SECONDS then return cache end
    local result = {}
    for k, item in pairs(mutes.characters) do result[k] = stronger(result[k], item.mode) end
    local roster = type(db.roster) == "table" and type(db.roster.players) == "table" and db.roster.players or {}
    for id, item in pairs(mutes.players) do
        local known, seen = {}, {}
        local player = roster[id]
        -- Keep the player's chosen name for the list, even after their list goes.
        if type(player) == "table" and S.string(player.name) then item.name = player.name:sub(1, 120) end
        for k in pairs(type(player) == "table" and type(player.characters) == "table" and player.characters or {}) do
            if type(k) == "string" and not seen[k] then seen[k] = true; known[#known + 1] = k end
        end
        for _, k in ipairs(item.characters or {}) do
            if not seen[k] then seen[k] = true; known[#known + 1] = k end
        end
        item.characters = keys(known)
        for _, k in ipairs(item.characters) do result[k] = stronger(result[k], item.mode) end
    end
    -- senders: each sender name's answer, so a long log asks once per name.
    cache = {revision=revision, at=now, modes=result, senders={}}
    return cache
end

-- The effective mode for a sender: "show", "log" or "hide". This account's own
-- characters are never muted.
function M.mode(sender)
    local current = modes()
    if not current or type(sender) ~= "string" then return "show" end
    local mode = current.senders[sender]
    if mode then return mode end
    local k = characterKey(sender)
    mode = k and current.modes[k] or "show"
    if mode ~= "show" and WoWStatusPopups and WoWStatusPopups.isSelf and WoWStatusPopups.isSelf(sender) then mode = "show" end
    current.senders[sender] = mode
    return mode
end
function M.popupsMuted(sender) return M.mode(sender) ~= "show" end
function M.hidden(sender) return M.mode(sender) == "hide" end

local function refresh()
    revision, cache = revision + 1, nil
    -- Popups already waiting from a friend muted just now are dropped too.
    if WoWStatusPopups and WoWStatusPopups.dropMuted then WoWStatusPopups.dropMuted() end
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
    if not db or (kind ~= "character" and kind ~= "player") or type(id) ~= "string" or id == ""
        or #id > 160 or not STRENGTH[mode] then return false end
    local mutes = state()
    if not mutes then
        if mode == "show" then return true end
        mutes = {players={}, characters={}}
        db.mutes = mutes
    end
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
        local old = map[id]
        map[id] = {mode=mode, name=name and name:sub(1, 120) or (old and old.name), at=time(),
            characters=kind == "player" and (old and old.characters or {}) or nil}
    end
    if next(mutes.players) == nil and next(mutes.characters) == nil then db.mutes = nil end
    refresh()
    modes() -- Remember a muted player's name and characters right away.
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
function M.count() return #M.list() end

-- The menu choices for a friend's character and, when known, their player.
-- Player mutes whose characters include this one (one character can be listed
-- under two player IDs after a reinstall).
local function playersOf(name)
    local mutes, k, ids = state(), characterKey(name), {}
    if not mutes or not k then return ids end
    modes() -- Brings each player's remembered characters up to date.
    for id, item in pairs(mutes.players) do
        for _, known in ipairs(item.characters or {}) do
            if known == k then ids[#ids + 1] = id; break end
        end
    end
    return ids
end
function M.choices(name)
    local items = {}
    -- While their player is muted, showing one character's popups cannot win
    -- (the stronger setting does): that choice is the player's "show popups".
    local playerMuted = #playersOf(name) > 0
    for _, mode in ipairs(M.MODES) do
        if not (mode == "show" and playerMuted) then
            items[#items + 1] = {label=T(M.LABELS[mode]), value={kind="character", mode=mode}}
        end
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
    if choice.kind == "player" and choice.mode == "show" then
        -- Unmute every player record this character is muted under.
        local ok = true
        for _, id in ipairs(playersOf(name)) do ok = M.set("player", id, "show") and ok end
        return ok
    end
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
local function text(parent, font, x, y, width) return WoWStatusUI.text(parent, font, x, y, width) end
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
