-- Character list grouped by player, with portraits (#59).
-- Each account has a random player ID and uses the existing player name
-- (Options > Groups). At login, and when a new group member comes online, the
-- account's characters that have logged in with the addon are whispered to
-- the group's members on the WoWStatusChr prefix:
--   C <group> <playerID> <playerName|-> <Name-Realm> <RACE> <sex> <CLASS> <level>
--   X <group> <playerID>        (stop sharing: forget this player's list)
-- Receivers accept only known members of a joined group and strictly
-- validated fields. Nothing is sent when sharing the list is turned off.
WoWStatusRoster = {}
local R, S = WoWStatusRoster, WoWStatusSafe
local PREFIX = "WoWStatusChr"
local MAX_PLAYERS, MAX_CHARACTERS = 64, 20
local CLASSES = {WARRIOR=true, PALADIN=true, HUNTER=true, ROGUE=true, PRIEST=true, DEATHKNIGHT=true, SHAMAN=true,
    MAGE=true, WARLOCK=true, MONK=true, DRUID=true, DEMONHUNTER=true, EVOKER=true}
local db, current, page
local outgoing, sentTo, lastSend, lastScan = {}, {}, 0, 0

local function key(name) return WoWStatusPopups.senderKey(name) end

local function state()
    db.roster = type(db.roster) == "table" and db.roster or {}
    db.roster.players = type(db.roster.players) == "table" and db.roster.players or {}
    if type(db.roster.id) ~= "string" or not db.roster.id:match("^[0-9a-f]+$") or #db.roster.id ~= 16 then
        local digits = {}
        for i = 1, 16 do digits[i] = string.format("%x", math.random(0, 15)) end
        db.roster.id = table.concat(digits)
    end
    if db.roster.share == nil then db.roster.share = true end
    return db.roster
end

-- Public facts about the logged-in character, saved for the list.
function R.observe(character)
    if not character then return end
    local _, race = S.call(UnitRace, "player")
    local _, class = S.call(UnitClass, "player")
    character.roster_info = {race=S.string(race), sex=S.number(S.call(UnitSex, "player")), class=S.string(class),
        level=WoWStatusAdapter.level(), at=time()}
end

local function playerName()
    local name = S.string(db.player_name)
    if name and #name >= 1 and #name <= 24 and not name:find(S.CONTROL_OR_PIPE) and not name:find(S.SPACE) then return name end
    return nil
end

-- This account's listed characters on this client, as message bodies.
local function ownLines(group)
    local roster, lines = state(), {}
    for _, c in pairs(db.characters or {}) do
        local info = c.roster_info
        if type(info) == "table" and c.identity and c.identity.client == WoWStatusAdapter.client_id and not c.hide_from_list
            and info.race and (info.sex == 2 or info.sex == 3) and CLASSES[info.class] and S.number(info.level) then
            local name = c.identity.name .. "-" .. S.stripSpace(c.identity.realm)
            table.insert(lines, table.concat({"C", group, roster.id, playerName() or "-", name, info.race, info.sex, info.class, info.level}, " "))
        end
    end
    table.sort(lines)
    return lines
end

local function enqueue(group, target)
    local peerKey = key(target)
    if not peerKey then return end
    sentTo[group] = sentTo[group] or {}
    if sentTo[group][peerKey] then return end
    sentTo[group][peerKey] = true
    if not state().share then return end
    for _, line in ipairs(ownLines(group)) do table.insert(outgoing, {target=target, text=line}) end
end

-- Send to group members not yet told this session (also after a change).
function R.scan()
    if not db or not current then return end
    for group in pairs(WoWStatusGroups.selected(current)) do
        for _, peer in ipairs(WoWStatusPopups.peers(group)) do enqueue(group, peer) end
    end
end

-- After a privacy change: tell everyone again (or tell them to forget us).
function R.changed()
    if not db or not current then return end
    local roster = state()
    outgoing, sentTo = {}, {}
    if not roster.share then
        for group in pairs(WoWStatusGroups.selected(current)) do
            for _, peer in ipairs(WoWStatusPopups.peers(group)) do
                table.insert(outgoing, {target=peer, text="X " .. group .. " " .. roster.id})
            end
        end
    end
    R.scan()
end

function R.setSharing(enabled)
    state().share = enabled == true
    R.changed()
end

function R.setHidden(character, hidden)
    character.hide_from_list = hidden == true or nil
    R.changed()
end

function R.tick()
    if not db or not current then return end
    local now = GetTime and GetTime() or time()
    if now - lastScan >= 30 then lastScan = now; R.scan() end
    if #outgoing == 0 or now - lastSend < .5 or WoWStatusAdapter.chatRestricted() then return end
    local item = table.remove(outgoing, 1)
    local send = C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
    if send then lastSend = now; pcall(send, PREFIX, item.text, "WHISPER", item.target) end
end

local function valid(words, max)
    local name, race, sex, class, level = words[5], words[6], tonumber(words[7]), words[8], tonumber(words[9])
    if not name or #name > 64 or name:find(S.CONTROL_OR_PIPE) or not name:match("^[^%-]+%-[^%-]+$") then return nil end
    if not race or not race:match("^[A-Za-z][A-Za-z]+$") or #race > 24 then return nil end
    if sex ~= 2 and sex ~= 3 or not CLASSES[class] then return nil end
    if not level or level ~= math.floor(level) or level < 1 or level > max then return nil end
    return {name=name, race=race, sex=sex, class=class, level=level}
end

function R.receive(message, sender, distribution)
    if not db or not current or distribution ~= "WHISPER" or type(message) ~= "string" or #message > 250 then return false end
    local words = {}
    for word in message:gmatch(S.NONSPACE .. "+") do words[#words + 1] = word end
    local op, group, pid = words[1], words[2], words[3]
    if not group or not WoWStatusGroups.contains(current, group) then return false end
    if not WoWStatusPopups.isPeer(group, key(sender)) then
        WoWStatusPopups.peers(group) -- Refresh the member list once before rejecting.
        if not WoWStatusPopups.isPeer(group, key(sender)) then return false end
    end
    if not pid or #pid ~= 16 or not pid:match("^[0-9a-f]+$") or pid == state().id then return false end
    local players = state().players
    if op == "X" and #words == 3 then players[pid] = nil; R.render(); return true end
    if op ~= "C" or #words ~= 9 then return false end
    local name = words[4]
    if #name > 24 or name:find(S.CONTROL_OR_PIPE) then return false end
    local character = valid(words, WoWStatusAdapter.max_level or 60)
    if not character then return false end
    local player = players[pid]
    if not player then
        local count, oldest, oldestAt = 0, nil, math.huge
        for id, p in pairs(players) do count = count + 1; if (p.at or 0) < oldestAt then oldest, oldestAt = id, p.at or 0 end end
        if count >= MAX_PLAYERS and oldest then players[oldest] = nil end
        player = {characters={}}
        players[pid] = player
    end
    player.name, player.at = name ~= "-" and name or nil, time()
    local characterKey = key(character.name)
    if not characterKey then return false end
    if not player.characters[characterKey] then
        local count, oldest, oldestAt = 0, nil, math.huge
        for k, c in pairs(player.characters) do count = count + 1; if (c.at or 0) < oldestAt then oldest, oldestAt = k, c.at or 0 end end
        if count >= MAX_CHARACTERS and oldest then player.characters[oldest] = nil end
    end
    character.at = time()
    player.characters[characterKey] = character
    R.render()
    return true
end

-- Portrait, best available first: live unit, then race/sex face, then silhouette.
local UNITS = {"target", "mouseover", "focus", "party1", "party2", "party3", "party4"}
function R.portrait(texture, name, race, sex)
    local wanted = key(name)
    for _, unit in ipairs(UNITS) do
        local unitName, realm = S.call(UnitName, unit)
        unitName, realm = S.string(unitName), S.string(realm)
        if unitName and wanted and key(unitName .. "-" .. (realm and realm ~= "" and realm or S.stripSpace(WoWStatusAdapter.realmName() or ""))) == wanted
            and SetPortraitTexture then
            if pcall(SetPortraitTexture, texture, unit) then return "live" end
        end
    end
    if race and (sex == 2 or sex == 3) then
        if texture:SetTexture("Interface\\CharacterFrame\\TemporaryPortrait-" .. (sex == 3 and "Female" or "Male") .. "-" .. race) ~= false then
            return "met"
        end
    end
    if texture:SetTexture("Interface\\CharacterFrame\\TempPortrait") == false then
        texture:SetTexture("Interface\\Icons\\INV_Misc_QuestionMark")
    end
    return "unknown"
end

local function ago(at)
    local seconds = math.max(0, time() - (at or time()))
    if seconds < 3600 then return math.floor(seconds / 60) .. "m ago" end
    if seconds < 86400 then return math.floor(seconds / 3600) .. "h ago" end
    return math.floor(seconds / 86400) .. "d ago"
end

-- Groups for the Characters page: {title, rows={{name, race, sex, class, level, status, latest}}}.
function R.groups()
    local online, latest, lastSeen = {}, {}, {}
    for group in pairs(WoWStatusGroups.selected(current)) do
        for _, peer in ipairs(WoWStatusPopups.peers(group)) do local k = key(peer); if k then online[k] = true end end
    end
    for _, e in ipairs(WoWStatusJournal.entries()) do
        local k = key(e.sender)
        if k and not latest[k] and e.kind ~= "recap" then latest[k] = e.text end
        if k and (not lastSeen[k] or e.at > lastSeen[k]) then lastSeen[k] = e.at end
    end
    local merged, order, known = {}, {}, {}
    local function add(title, character, self)
        local groupKey = S.lowerASCII(title)
        local entry = merged[groupKey]
        if not entry then entry = {title=title, rows={}}; merged[groupKey] = entry; table.insert(order, entry) end
        local k = key(character.name)
        if not k or known[k] then return end
        known[k] = true
        local status = self and (k == key(current.identity.name .. "-" .. S.stripSpace(current.identity.realm)) and "online" or "offline")
            or (online[k] and "online") or ("last seen " .. ago(math.max(lastSeen[k] or 0, character.at or 0)))
        table.insert(entry.rows, {name=character.name, race=character.race, sex=character.sex, class=character.class,
            level=character.level, status=status, latest=latest[k]})
    end
    for _, c in pairs(db.characters or {}) do
        local info = c.roster_info
        if type(info) == "table" and c.identity and c.identity.client == WoWStatusAdapter.client_id then
            add((playerName() or "You") .. " (you)", {name=c.identity.name .. "-" .. S.stripSpace(c.identity.realm),
                race=info.race, sex=info.sex, class=info.class, level=info.level, at=info.at}, true)
        end
    end
    for _, player in pairs(state().players) do
        for _, character in pairs(player.characters) do add(player.name or "Unnamed player", character) end
    end
    -- Senders in the log that never announced a list.
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if not e.owner and e.sender and key(e.sender) and not known[key(e.sender)] then
            add("Not announced", {name=e.sender, at=e.at})
        end
    end
    for _, entry in ipairs(order) do
        entry.title = entry.title .. " (" .. #entry.rows .. (#entry.rows == 1 and " character)" or " characters)")
        table.sort(entry.rows, function(a, b) return (a.level or 0) > (b.level or 0) end)
    end
    return order
end

local function row(index)
    local line = CreateFrame("Frame", nil, page.list)
    line:SetSize(680, 30)
    line.portrait = line:CreateTexture(nil, "ARTWORK"); line.portrait:SetPoint("TOPLEFT", 16, -2); line.portrait:SetSize(26, 26)
    line.text = line:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    line.text:SetPoint("TOPLEFT", 50, -8); line.text:SetWidth(620); line.text:SetJustifyH("LEFT")
    page.lines[index] = line
    return line
end

function R.render()
    if not page or not page.IsShown or not page:IsShown() then return end
    local index = 0
    for _, group in ipairs(R.groups()) do
        index = index + 1
        local header = page.lines[index] or row(index)
        header:ClearAllPoints(); header:SetPoint("TOPLEFT", 0, -(index - 1) * 32)
        header.portrait:Hide(); header.text:SetPoint("TOPLEFT", 0, -8)
        header.text:SetText("|cffffd100" .. group.title:gsub("|", "||") .. "|r"); header.kind = "header"; header:Show()
        for _, character in ipairs(group.rows) do
            if index >= 200 then break end
            index = index + 1
            local line = page.lines[index] or row(index)
            line:ClearAllPoints(); line:SetPoint("TOPLEFT", 0, -(index - 1) * 32)
            line.text:SetPoint("TOPLEFT", 50, -8); line.portrait:Show()
            line.portraitKind = R.portrait(line.portrait, character.name, character.race, character.sex)
            local colour = RAID_CLASS_COLORS and character.class and RAID_CLASS_COLORS[character.class]
            local name = (character.name:match("^[^-]+") or character.name):gsub("|", "||")
            if colour and colour.colorStr then name = "|c" .. colour.colorStr .. name .. "|r" end
            local class = character.class and (character.class:sub(1, 1) .. character.class:sub(2):lower()) or "?"
            local level = character.level and (class .. " " .. character.level) or "never met"
            line.text:SetText(name .. "   " .. level .. "   " .. character.status
                .. (character.latest and ("   · " .. character.latest:gsub("|", "||")) or ""))
            line.kind, line.character = "character", character
            line:Show()
        end
    end
    for i = index + 1, #page.lines do page.lines[i]:Hide() end
    page.list:SetHeight(math.max(1, index) * 32)
    page.empty:SetShown(index == 0)
    page.count = index
end

local function build(parent)
    page = CreateFrame("Frame", "WoWStatusCharactersPage", parent); page:SetAllPoints(parent)
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -4); page.scroll:SetSize(710, 470)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 32); page.lines = {}
    page.scroll:SetScrollChild(page.list)
    page.empty = page:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    page.empty:SetPoint("TOPLEFT", 24, -12); page.empty:SetText("No characters yet.")
    page.share = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate")
    page.share:SetPoint("TOPLEFT", 24, -486); page.share:SetSize(32, 32)
    local shareLabel = page.share:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    shareLabel:SetPoint("TOPLEFT", 38, -8); shareLabel:SetText("Share my character list")
    page.share:SetScript("OnClick", function(self) R.setSharing(self:GetChecked() and true or false) end)
    page.hide = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate")
    page.hide:SetPoint("TOPLEFT", 330, -486); page.hide:SetSize(32, 32)
    local hideLabel = page.hide:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    hideLabel:SetPoint("TOPLEFT", 38, -8); hideLabel:SetText("Hide this character from the list")
    page.hide:SetScript("OnClick", function(self) R.setHidden(current, self:GetChecked() and true or false) end)
    return page
end

WoWStatusMainWindow.register("characters", "Characters", build, function()
    if not page then return end
    page.share:SetChecked(state().share)
    page.hide:SetChecked(current and current.hide_from_list == true)
    R.render()
end)

function R.init(database, character)
    db, current = database, character
    state()
    R.observe(character)
    outgoing, sentTo, lastScan = {}, {}, 0
    local register = C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix or RegisterAddonMessagePrefix
    if register then pcall(register, PREFIX) end
end

local frame = CreateFrame("Frame")
for _, event in ipairs({"CHAT_MSG_ADDON", "PLAYER_LEVEL_UP"}) do pcall(frame.RegisterEvent, frame, event) end
frame:SetScript("OnEvent", function(_, event, prefix, message, distribution, sender)
    if event == "PLAYER_LEVEL_UP" then
        if current and current.roster_info then current.roster_info.level = S.number(prefix) or current.roster_info.level end
        return
    end
    if S.string(prefix) == PREFIX then R.receive(S.string(message), S.string(sender), S.string(distribution)) end
end)
local elapsed = 0
frame:SetScript("OnUpdate", function(_, delta) elapsed = elapsed + delta; if elapsed >= .25 then elapsed = 0; R.tick() end end)
