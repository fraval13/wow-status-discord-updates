-- A character's profile, opened by clicking their card on the Characters page:
-- portrait and facts, their statistics, level-ups, recent activity and recent
-- gear from the log, with Show activity and (for friends online) Invite to group.
-- Also the Join / Decline popup for invitations friends send.
WoWStatusProfile = {}
local F, S = WoWStatusProfile, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local view, invite

local function key(name) return WoWStatusRoster.key(name) end

-- The log entries of one character, newest first.
local function entriesOf(name)
    local k, list = key(name), {}
    for _, e in ipairs(WoWStatusJournal.entries()) do
        if k and key(e.sender) == k and WoWStatusJournal.visible(e) and e.kind ~= "recap" then list[#list + 1] = e end
    end
    table.sort(list, function(a, b) return (a.at or 0) > (b.at or 0) end)
    return list
end

local function when(at)
    local text = S.number(at) and WoWStatusHistory.oslo(at) or ""
    return text:sub(1, 16)
end

-- What the profile shows: {title, facts={...}, levels={...}, recent={...}, gear={...}}.
function F.data(row)
    local UI = WoWStatusUI
    local entries = entriesOf(row.name)
    local facts = {}
    local function fact(label, value) if value ~= nil and value ~= false then facts[#facts + 1] = {T(label), value} end end
    local xp = S.number(row.xp)
    fact("Level", S.number(row.level) and (row.level .. (xp and (" (" .. math.floor(xp / 10) .. "%)") or "")))
    fact("Deaths", S.number(row.deaths))
    fact("Monsters killed", S.number(row.kills))
    local quests
    for _, e in ipairs(entries) do
        local n = e.kind == "quest" and tonumber(tostring(e.text or ""):match("^Completed (%d+) quests!$"))
        if n and (not quests or n > quests) then quests = n end
    end
    fact("Quests", quests)
    fact("Gold", S.number(row.gold) and UI.money(row.gold))
    fact("Gold earned", S.number(row.earned) and UI.money(row.earned, true))
    fact("Played", S.number(row.played) and UI.duration(row.played))
    fact("Honorable kills", S.number(row.honor_kills) and row.honor_kills > 0 and row.honor_kills)
    fact("Dungeons cleared", S.number(row.dungeons) and row.dungeons > 0 and row.dungeons)
    fact("Mounts", S.number(row.mounts) and row.mounts > 0 and row.mounts)
    local levels, recent, gear = {}, {}, {}
    for _, e in ipairs(entries) do
        if e.kind == "level" and S.number(e.level) and #levels < 8 then
            levels[#levels + 1] = TF("Level %d", e.level) .. "  |cff9d9d9d" .. when(e.at) .. "|r"
        end
        if e.kind == "loot" and #gear < 6 then
            gear[#gear + 1] = WoWStatusPresentation.colourItem(e, T(e.text):gsub("|", "||")) .. "  |cff9d9d9d" .. when(e.at):sub(1, 10) .. "|r"
        end
        if #recent < 8 then
            recent[#recent + 1] = WoWStatusJournal.deathText(e):gsub("|", "||") .. "  |cff9d9d9d" .. when(e.at) .. "|r"
        end
    end
    return {facts=facts, levels=levels, recent=recent, gear=gear}
end

local function list(box, lines, empty)
    box.text:SetText(#lines > 0 and table.concat(lines, "\n") or ("|cff808080" .. T(empty) .. "|r"))
end

local function build(page)
    local UI = WoWStatusUI
    view = CreateFrame("Frame", "WoWStatusProfileView", page)
    view:SetAllPoints(page); view:SetFrameLevel((page.GetFrameLevel and page:GetFrameLevel() or 1) + 20)
    view:EnableMouse(true)
    local backdrop = view:CreateTexture(nil, "BACKGROUND"); backdrop:SetAllPoints()
    backdrop:SetColorTexture(.05, .04, .03, .97); view.backdrop = backdrop
    if WoWStatusTheme and WoWStatusTheme.attachBackground then WoWStatusTheme.attachBackground(backdrop) end
    -- Header
    local head = UI.box(view, 710, 88); head:SetPoint("TOPLEFT", 24, -4); view.head = head
    head.portrait = head:CreateTexture(nil, "ARTWORK"); head.portrait:SetPoint("TOPLEFT", 12, -12); head.portrait:SetSize(60, 60)
    head.badge = UI.levelBadge(head, 28); head.badge:SetPoint("TOPLEFT", 50, -50)
    head.name = UI.text(head, "GameFontNormalHuge", 88, -12, 330)
    head.info = UI.text(head, "GameFontHighlight", 88, -42, 330)
    head.status = UI.text(head, "GameFontHighlightSmall", 88, -64, 330)
    local function button(label, x, y, width, onClick)
        local widget = CreateFrame("Button", nil, head, "UIPanelButtonTemplate")
        widget:SetPoint("TOPLEFT", x, y); widget:SetSize(width, 26); widget:SetText(T(label))
        widget:SetScript("OnClick", onClick)
        return widget
    end
    view.back = button("Back", 594, -10, 104, function() view:Hide() end)
    view.activity = button("Show activity", 434, -10, 154, function()
        if view.row then WoWStatusJournal.showCharacter(view.row.name) end
    end)
    view.invite = button("Invite to group", 434, -48, 154, function(self)
        local row = view.row
        local items = {}
        for id, member in pairs(WoWStatusGroups.selected(WoWStatusPopups.character())) do
            if not (row.groupIds and row.groupIds[id]) then items[#items + 1] = {label=(member.label or id):gsub("|", "||"), value=id} end
        end
        table.sort(items, function(a, b) return S.lowerASCII(a.label) < S.lowerASCII(b.label) end)
        if #items == 0 then view.message:SetText(T("They are already in all your groups.")); return end
        UI.menu(self, items, function(id)
            local _, message = WoWStatusRoster.invite(row.name, id)
            view.message:SetText(T(message))
        end)
    end)
    view.message = UI.text(head, "GameFontNormalSmall", 434, -76, 264, "RIGHT")
    -- Statistics
    local stats = UI.box(view, 710, 118); stats:SetPoint("TOPLEFT", 24, -98); view.stats = stats
    UI.header(stats, T("Statistics"), 12, -8, 686)
    stats.cells = {}
    for i = 1, 10 do
        local column, rowIndex = (i - 1) % 3, math.floor((i - 1) / 3)
        stats.cells[i] = UI.text(stats, "GameFontHighlight", 12 + column * 232, -32 - rowIndex * 20, 226)
    end
    -- Level-ups, recent activity and recent gear
    local function column(title, x, width)
        local box = UI.box(view, width, 286); box:SetPoint("TOPLEFT", x, -222)
        UI.header(box, T(title), 10, -8, width - 20)
        box.text = UI.text(box, "GameFontHighlightSmall", 10, -32, width - 20)
        if box.text.SetSpacing then box.text:SetSpacing(4) end
        return box
    end
    view.levels = column("Level-ups", 24, 180)
    view.recent = column("Recent activity", 210, 300)
    view.gear = column("Recent gear", 516, 218)
    if UISpecialFrames then table.insert(UISpecialFrames, "WoWStatusProfileView") end
end

-- Open the profile of a row from the Characters page (entry is its player heading).
function F.show(row, entry)
    local page = WoWStatusCharactersPage
    if type(row) ~= "table" or not page then return false end
    if not view then build(page) end
    local UI = WoWStatusUI
    view.row, view.entry = row, entry
    local head = view.head
    WoWStatusRoster.portrait(head.portrait, row.name, row.race, row.sex)
    head.badge:SetLevel(row.level); head.badge:SetShown(row.level ~= nil)
    local short = (row.name:match("^[^-]+") or row.name):gsub("|", "||")
    local colour = UI.classColour(row.class)
    head.name:SetText(colour and (colour .. short .. "|r") or short)
    local class = row.class and T(row.class:sub(1, 1) .. row.class:sub(2):lower()) or T("Never met")
    local player = entry and entry.name and (" · " .. tostring(entry.name):gsub("|", "||")) or ""
    head.info:SetText((row.race and (WoWStatusRoster.shownRace(row.race) .. " ") or "") .. class .. player)
    local groups = row.groups and #row.groups > 0 and ("   |cff9d9d9d" .. T("Groups:") .. "|r " .. table.concat(row.groups, ", "):gsub("|", "||")) or ""
    head.status:SetText(T(row.status or "") .. groups)
    local friend = not (entry and entry.self)
    view.invite:SetShown(friend)
    if view.invite.SetEnabled then view.invite:SetEnabled(row.status == "online") end
    view.message:SetText(friend and row.status ~= "online" and T("Invites need them online.") or "")
    local data = F.data(row)
    for i, cell in ipairs(view.stats.cells) do
        local item = data.facts[i]
        cell:SetText(item and ("|cffd0b070" .. item[1] .. ":|r " .. tostring(item[2])) or "")
    end
    list(view.levels, data.levels, "No level-ups in the log yet.")
    list(view.recent, data.recent, "No activity in the log yet.")
    list(view.gear, data.gear, "No new gear yet.")
    view:Show()
    return true
end
function F.hide() if view then view:Hide() end end

-- An invitation from a friend: "Mira (Frank) invites you to join Secret Garden."
function F.invited(from, name)
    local UI = WoWStatusUI
    if not invite then
        invite = UI.box(UIParent, 420, 130)
        invite:SetPoint("TOP", 0, -160); invite:SetFrameStrata("DIALOG"); invite:EnableMouse(true)
        _G.WoWStatusInvite = invite
        invite.text = UI.text(invite, "GameFontHighlight", 20, -18, 380, "CENTER")
        invite.join = CreateFrame("Button", nil, invite, "UIPanelButtonTemplate")
        invite.join:SetPoint("TOPLEFT", 60, -84); invite.join:SetSize(140, 28)
        invite.decline = CreateFrame("Button", nil, invite, "UIPanelButtonTemplate")
        invite.decline:SetPoint("TOPLEFT", 220, -84); invite.decline:SetSize(140, 28)
        invite.join:SetScript("OnClick", function()
            invite:Hide()
            local _, message = WoWStatusGroups.join(invite.group)
            if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("|cff66ccffWoW Status:|r " .. T(message)) end
        end)
        invite.decline:SetScript("OnClick", function() invite:Hide() end)
    end
    if invite:IsShown() then return false end -- One at a time.
    invite.group = name
    invite.text:SetText(tostring(from):gsub("|", "||") .. " " .. T("invites you to join the group")
        .. "\n|cffffd100" .. tostring(name):gsub("|", "||") .. "|r")
    invite.join:SetText(T("Join")); invite.decline:SetText(T("Decline"))
    invite:Show()
    return true
end
