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
    local quests = S.number(row.quests)
    for _, e in ipairs(not row.quests_source and entries or {}) do
        local n = e.kind == "quest" and tonumber(tostring(e.text or ""):match("^Completed (%d+) quests!$"))
        if n and (not quests or n > quests) then quests = n end
    end
    fact(row.quests_source == "tracked_since" and "Quests (tracked)" or "Quests", quests)
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

local function equipmentSlot(parent, spec, x, y, width)
    local UI, T = WoWStatusUI, WoWStatusLocale.T
    local button = CreateFrame("Button", nil, parent)
    button:SetPoint("TOPLEFT", x, y); button:SetSize(width, 40)
    button.slot, button.label = spec[1], spec[2]
    button.icon = button:CreateTexture(nil, "ARTWORK"); button.icon:SetSize(36, 36); button.icon:SetPoint("TOPLEFT", 0, -2)
    local _, emptyIcon = S.call(GetInventorySlotInfo, spec[3])
    button.emptyIcon = S.value(emptyIcon) or "Interface\\Icons\\INV_Misc_QuestionMark"
    button.title = UI.text(button, "GameFontNormalSmall", 42, -2, width - 42)
    button.title:SetText(T(spec[2]))
    button.name = UI.text(button, "GameFontHighlightSmall", 42, -17, width - 42)
    if button.name.SetWordWrap then button.name:SetWordWrap(false) end
    button:SetScript("OnEnter", function(self)
        if not GameTooltip then return end
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        if self.item and GameTooltip.SetHyperlink then
            local ok = pcall(GameTooltip.SetHyperlink, GameTooltip, self.item)
            if not ok then GameTooltip:Hide(); return end
        elseif GameTooltip.SetText then GameTooltip:SetText(T(self.label) .. ": " .. T(self.emptyText or "Not available")) end
        GameTooltip:Show()
    end)
    button:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    return button
end

local function buildEquipment(body)
    local UI, E = WoWStatusUI, WoWStatusEquipment
    local box = UI.box(body, 710, 548); box:SetPoint("TOPLEFT", 0, -422); view.equipment = box
    UI.header(box, T("Equipped gear"), 12, -10, 550)
    box.updated = UI.text(box, "GameFontHighlightSmall", 12, -35, 550)
    box.refresh = CreateFrame("Button", nil, box, "UIPanelButtonTemplate")
    box.refresh:SetPoint("TOPRIGHT", -12, -10); box.refresh:SetSize(120, 24); box.refresh:SetText(T("Refresh gear"))
    box.refresh:SetScript("OnClick", function()
        if view.row then WoWStatusRoster.requestEquipment(view.row.name); F.refreshEquipment() end
    end)
    box.slots = {}
    for i, spec in ipairs(E.SLOTS) do
        local x, y, width = 14, -66 - ((i - 1) % 8) * 44, 198
        if i > 8 and i <= 16 then x = 498 end
        if i > 16 then x, y, width = 14 + (i - 17) * 172, -438, 166 end
        if WoWStatusAdapter.client_id == "retail" and i > 16 then x = 182 + (i - 17) * 172 end
        local slot = equipmentSlot(box, spec, x, y, width)
        slot:SetShown(not (WoWStatusAdapter.client_id == "retail" and (spec[1] == 0 or spec[1] == 18)))
        box.slots[spec[1]] = slot
    end
    box.portrait = box:CreateTexture(nil, "ARTWORK")
    box.portrait:SetPoint("TOPLEFT", 250, -110); box.portrait:SetSize(210, 210)
    box.appearance = UI.text(box, "GameFontHighlightSmall", 222, -382, 266, "CENTER")
    -- A public, available unit can supply the actual model. Offline characters
    -- keep their race portrait; gear alone cannot reconstruct a face or hair.
    local ok, model = pcall(CreateFrame, "PlayerModel", nil, box)
    if ok and model then model:Hide() end
    if ok and model and model.SetUnit then
        box.model = model; model:SetPoint("TOPLEFT", 218, -62); model:SetSize(276, 310)
        model:EnableMouse(false)
    end
    box.note = UI.text(box, "GameFontHighlightSmall", 14, -500, 680)
    box.note:SetText(T("Hover an item for its full tooltip. Stats include buffs at the time recorded."))
    local stats = UI.box(body, 710, 268); stats:SetPoint("TOPLEFT", 0, -982); view.attributes = stats
    UI.header(stats, T("Combat attributes"), 12, -10, 686)
    stats.cells = {}
    for i = 1, #E.STATS do
        stats.cells[i] = UI.text(stats, "GameFontHighlight", 12 + ((i - 1) % 2) * 348, -36 - math.floor((i - 1) / 2) * 22, 336)
    end
end

function F.refreshEquipment()
    if not view or not view.row or not view:IsShown() then return end
    local box, row, E = view.equipment, view.row, WoWStatusEquipment
    local snapshot, hidden = WoWStatusRoster.equipment(row.name)
    local waiting = WoWStatusRoster.equipmentWaiting(row.name)
    view.waitingForEquipment = waiting
    box.updated:SetText(snapshot and (T("Last reported:") .. " " .. when(snapshot.at))
        or T(waiting and "Requesting equipment…" or (hidden and "Equipment sharing is off."
            or "No snapshot yet. Their owner needs the latest addon and must be online to share it.")))
    for slot, button in pairs(box.slots) do
        local value = snapshot and snapshot.items[slot]
        button.item = E.item(value)
        local name, _, quality = S.call((C_Item and C_Item.GetItemInfo) or GetItemInfo, button.item)
        name, quality = S.string(name), S.number(quality)
        local id = button.item and tonumber(button.item:match("^item:(%d+)"))
        local icon = id and WoWStatusPresentation.itemIcon({kind="equipment", item_id=id})
        button.icon:SetTexture(icon or button.emptyIcon)
        local empty = value == "-" and "Empty" or "Not available"
        button.emptyText = empty
        local shown = name and name:gsub("|", "||") or (id and (T("Item") .. " " .. id)) or T(empty)
        local colour = ({[0]="ff9d9d9d", [1]="ffffffff", [2]="ff1eff00", [3]="ff0070dd", [4]="ffa335ee", [5]="ffff8000", [6]="ffe6cc80", [7]="ff00ccff"})[quality]
        button.name:SetText(colour and ("|c" .. colour .. shown .. "|r") or shown)
    end
    WoWStatusRoster.portrait(box.portrait, row.name, row.race, row.sex)
    local unit
    for _, candidate in ipairs({"player", "target", "focus", "mouseover", "party1", "party2", "party3", "party4"}) do
        local name, realm = S.call(UnitName, candidate)
        name, realm = S.string(name), S.string(realm)
        if name and key(name .. "-" .. (realm and realm ~= "" and realm or WoWStatusAdapter.realmName() or "")) == key(row.name) then unit = candidate; break end
    end
    local live = false
    if box.model then
        box.model:Hide()
        if unit then local ok, result = pcall(box.model.SetUnit, box.model, unit); live = ok and S.value(result) ~= false end
        box.model:SetShown(live)
    end
    box.portrait:SetShown(not live)
    box.appearance:SetText(T(live and "Live appearance" or "Saved equipment · race portrait"))
    for i, spec in ipairs(E.STATS) do
        local value = snapshot and snapshot.stats[spec[1]]
        local shown = value and (spec[3] and string.format("%.2f%%", value / 100) or tostring(value)) or "—"
        view.attributes.cells[i]:SetText("|cffd0b070" .. T(spec[2]) .. ":|r " .. shown)
    end
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
    view.back = button("Back", 594, -10, 104, function()
        if not WoWStatusMainWindow.back() then F.hide(); WoWStatusMainWindow.go({page="characters"}) end
    end)
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
    -- A fixed header and a scrollable body, with equipment below the history.
    view.scroll = CreateFrame("ScrollFrame", nil, view, "UIPanelScrollFrameTemplate")
    view.scroll:SetPoint("TOPLEFT", 24, -98); view.scroll:SetSize(710, 430)
    view.body = CreateFrame("Frame", nil, view.scroll); view.body:SetSize(710, 1262)
    view.scroll:SetScrollChild(view.body)
    if view.scroll.EnableMouseWheel then view.scroll:EnableMouseWheel(true) end
    view.scroll:SetScript("OnMouseWheel", function(self, delta)
        self:SetVerticalScroll(math.max(0, math.min(832, self:GetVerticalScroll() - delta * 64)))
    end)
    -- Statistics
    local stats = UI.box(view.body, 710, 118); stats:SetPoint("TOPLEFT", 0, 0); view.stats = stats
    UI.header(stats, T("Statistics"), 12, -8, 686)
    stats.cells = {}
    for i = 1, 10 do
        local column, rowIndex = (i - 1) % 3, math.floor((i - 1) / 3)
        stats.cells[i] = UI.text(stats, "GameFontHighlight", 12 + column * 232, -32 - rowIndex * 20, 226)
    end
    -- Level-ups, recent activity and recent gear
    local function column(title, x, width)
        local box = UI.box(view.body, width, 286); box:SetPoint("TOPLEFT", x, -124)
        UI.header(box, T(title), 10, -8, width - 20)
        box.text = UI.text(box, "GameFontHighlightSmall", 10, -32, width - 20)
        if box.text.SetSpacing then box.text:SetSpacing(4) end
        return box
    end
    view.levels = column("Level-ups", 0, 180)
    view.recent = column("Recent activity", 186, 300)
    view.gear = column("Recent gear", 492, 218)
    buildEquipment(view.body)
    if UISpecialFrames then table.insert(UISpecialFrames, "WoWStatusProfileView") end
end

-- Update the visible facts without reopening the profile or moving its scroll.
function F.refreshQuests()
    if not view or not view.row or not view:IsShown() then return end
    for _, group in ipairs(WoWStatusRoster.groups()) do
        for _, row in ipairs(group.rows) do
            if key(row.name) == key(view.row.name) then
                view.row.quests, view.row.quests_source = row.quests, row.quests_source
                local data = F.data(view.row)
                for i, cell in ipairs(view.stats.cells) do
                    local item = data.facts[i]
                    cell:SetText(item and ("|cffd0b070" .. item[1] .. ":|r " .. tostring(item[2])) or "")
                end
                return
            end
        end
    end
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
    view.scroll:SetVerticalScroll(0)
    view:Show()
    WoWStatusRoster.requestEquipment(row.name)
    F.refreshEquipment()
    WoWStatusMainWindow.go({page="characters", profile=row.name})
    return true
end
-- The profile of a character by name (Back and the breadcrumbs).
function F.showByName(name)
    local k = key(name)
    for _, entry in ipairs(WoWStatusRoster.groups()) do
        for _, row in ipairs(entry.rows) do
            if k and key(row.name) == k then return F.show(row, entry) end
        end
    end
    return false
end
function F.hide() if view then view:Hide() end end

-- Item names and icons may arrive after the snapshot. Refresh display only.
local items = CreateFrame("Frame")
pcall(items.RegisterEvent, items, "GET_ITEM_INFO_RECEIVED")
items:SetScript("OnEvent", function() F.refreshEquipment() end)
local waitingElapsed = 0
items:SetScript("OnUpdate", function(_, delta)
    waitingElapsed = waitingElapsed + delta
    if waitingElapsed < 1 then return end
    waitingElapsed = 0
    if view and view:IsShown() and view.waitingForEquipment and not WoWStatusRoster.equipmentWaiting(view.row.name) then
        F.refreshEquipment()
    end
end)

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
