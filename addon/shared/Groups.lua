-- Account-wide group choices, with per-character join times and history boundaries.
WoWStatusGroups = {}
local G = WoWStatusGroups
local getCharacter, database, report, panel
local MAX_GROUPS = 8

function G.valid(id)
    return type(id) == "string" and #id == 22 and id:match("^[a-f0-9]+$") ~= nil
end
function G.key(text)
    text = text:match("^%s*(.-)%s*$")
    local _, characters = text:gsub("[^\128-\191]", "")
    if text == "" or characters > 80 or text:find("[%c]") then return nil end
    local a, b, c = 5381, 2166136261, 104729
    local canonical = WoWStatusCaseFold(text)
    for i = 1, #canonical do
        local byte = canonical:byte(i)
        a = (a * 33 + byte) % 4294967296
        b = (b * 65599 + byte) % 4294967296
        c = (c * 131 + byte) % 4294967296
    end
    return string.format("%08x%08x%06x", a, b, c % 16777216), text
end
function G.channel(id) return "WStatus" .. id end
function G.selected(character)
    return character and character.group_ids or {}
end
function G.contains(character, id)
    return character and character.group_ids and character.group_ids[id] ~= nil
end
local function apply(character, force)
    if character.legacy_upload and not force then return end
    local previous, selected = character.group_ids or {}, {}
    for id, label in pairs(database.account_groups) do
        selected[id] = previous[id] or {joined_at = time(), label = label}
        selected[id].label = label
        if not previous[id] and character.settings.enabled
            and character.settings.fields.level and character.settings.collection.level then
            selected[id].baseline_level = character == getCharacter() and WoWStatusAdapter.level()
                or (character.snapshot and character.snapshot.level)
        end
    end
    character.group_ids = selected
    character.legacy_upload = false
    character.player_name = database.player_name or ""
    character.exported_at = time()
end
function G.init(db, getter, reporter)
    database, getCharacter, report = db, getter, reporter
    if not database.account_groups then
        -- Preserve existing selections, merging old character lists deterministically.
        database.account_groups = {}
        local keys, count = {}, 0
        for key in pairs(database.characters) do table.insert(keys, key) end
        table.sort(keys)
        for _, key in ipairs(keys) do
            local old = database.characters[key].group_ids or {}
            local ids = {}
            for id in pairs(old) do table.insert(ids, id) end
            table.sort(ids)
            for _, id in ipairs(ids) do
                local member = old[id]
                if not database.account_groups[id] then
                    if count < MAX_GROUPS then
                        database.account_groups[id] = member.label
                        count = count + 1
                    else
                        report("More than 8 old groups found. Review your account group list.")
                    end
                end
            end
        end
    end
    for _, character in pairs(database.characters) do apply(character) end
end
local function update(text, playerName)
    local selected, count = {}, 0
    for label in text:gmatch("[^\r\n]+") do
        local id, cleaned = G.key(label)
        if not id then return false, "Use a non-empty group name of up to 80 characters, one per line." end
        if selected[id] and WoWStatusCaseFold(selected[id].label) ~= WoWStatusCaseFold(cleaned) then
            return false, "These group names collide; choose a different name."
        end
        if not selected[id] then
            count = count + 1
            if count > MAX_GROUPS then return false, "Choose at most 8 group IDs." end
            selected[id] = {label = cleaned}
        end
    end
    playerName = playerName:match("^%s*(.-)%s*$")
    if #playerName > 40 or playerName:find("[%c|]") then return false, "Use a name of up to 40 characters." end
    database.account_groups = {}
    for id, member in pairs(selected) do database.account_groups[id] = member.label end
    database.player_name = playerName
    for _, saved in pairs(database.characters) do apply(saved, true) end
    if WoWStatusPopups then WoWStatusPopups.groupsChanged() end
    return true, "Group list saved for all characters on this account. /reload exports it. Removed groups stop receiving new data."
end
G.update = update
function G.text(character, multiline)
    local ids = {}
    for id, member in pairs(G.selected(character)) do table.insert(ids, member.label or id) end
    table.sort(ids)
    return table.concat(ids, multiline and "\n" or ", ")
end
local function groupList()
    local groups = {}
    for id, text in pairs(database.account_groups or {}) do
        table.insert(groups, {id = id, label = text})
    end
    table.sort(groups, function(a, b) return a.label < b.label end)
    return groups
end
local function renderGroups()
    local groups = groupList()
    panel.count:SetText("Groups (" .. #groups .. " / " .. MAX_GROUPS .. ")")
    panel.empty:SetShown(#groups == 0)
    for i, row in ipairs(panel.rows) do
        local group = groups[i]
        row.id = group and group.id
        row.fullLabel = group and group.label
        row:SetShown(group ~= nil)
        if group then row.label:SetText((group.label:gsub("|", "||"))) end
    end
end
local function saveList(groups)
    local labels = {}
    for _, group in ipairs(groups) do table.insert(labels, group.label) end
    local ok, message = update(table.concat(labels, "\n"), panel.name:GetText())
    panel.status:SetText(message)
    report(message)
    if ok then renderGroups() end
    return ok
end
function G.show(host)
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusGroupWindow", UIParent)
        panel:SetSize(620, 690)
        panel:SetPoint("CENTER")
        panel:SetFrameStrata("DIALOG")
        panel:EnableMouse(true)
        local bg = panel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.04, .04, .07, .98)
        local function label(text, y, width)
            local f = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
            f:SetPoint("TOPLEFT", 24, y); f:SetWidth(width or 570)
            f:SetJustifyH("LEFT"); f:SetText(text)
            return f
        end
        local function button(parent, text, x, y, width, action)
            local widget = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
            widget:SetPoint("TOPLEFT", x, y); widget:SetSize(width, 28)
            widget:SetText(text); widget:SetScript("OnClick", action)
            return widget
        end
        local function input(y, limit)
            local edit = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
            edit:SetPoint("TOPLEFT", 28, y); edit:SetSize(400, 30)
            edit:SetFontObject("ChatFontNormal")
            edit:SetAutoFocus(false); edit:SetMultiLine(false); edit:SetMaxLetters(limit)
            edit:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
            return edit
        end
        label("Your groups — all characters on this account", -20)
        label("Your name (optional)", -55)
        panel.name = input(-80, 40)
        local function saveName() saveList(groupList()) end
        panel.saveName = button(panel, "Save name", 454, -80, 120, saveName)
        panel.name:SetScript("OnEnterPressed", saveName)
        label("Group ID", -126)
        panel.input = input(-150, 80)
        local function add()
            local id, cleaned = G.key(panel.input:GetText())
            if not id then
                panel.status:SetText("Enter one group ID of up to 80 characters.")
                return
            end
            if database.account_groups[id] then
                panel.status:SetText("That group is already in your list.")
                return
            end
            local groups = groupList()
            if #groups >= MAX_GROUPS then
                panel.status:SetText("You can add up to 8 groups. Remove one before adding another.")
                return
            end
            table.insert(groups, {id = id, label = cleaned})
            if saveList(groups) then
                panel.input:SetText("")
                panel.input:SetFocus()
            end
        end
        panel.add = button(panel, "Add", 454, -150, 120, add)
        panel.input:SetScript("OnEnterPressed", add)
        panel.count = label("", -194)
        panel.empty = label("No groups selected. Enter a group ID above and click Add.", -230)
        panel.rows = {}
        for i = 1, MAX_GROUPS do
            local row = CreateFrame("Frame", nil, panel)
            row:SetPoint("TOPLEFT", 24, -222 - (i - 1) * 36)
            row:SetSize(550, 32)
            row.label = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
            row.label:SetPoint("TOPLEFT", 0, -6); row.label:SetWidth(410)
            row.label:SetJustifyH("LEFT"); row.label:SetWordWrap(false)
            row:EnableMouse(true)
            row:SetScript("OnEnter", function(self)
                if GameTooltip and self.fullLabel then
                    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
                    GameTooltip:SetText((self.fullLabel:gsub("|", "||")))
                    GameTooltip:Show()
                end
            end)
            row:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
            row.remove = button(row, "Remove", 430, 0, 120, function()
                local retained = {}
                for _, group in ipairs(groupList()) do
                    if group.id ~= row.id then table.insert(retained, group) end
                end
                saveList(retained)
            end)
            table.insert(panel.rows, row)
        end
        panel.status = label("", -520)
        label("Add and Remove save immediately for all your characters.\n"
            .. "Use /reload or log out to export changes, then run the companion.\n"
            .. "New groups receive current status and future shared events.", -586)
        panel.close = button(panel, "Close", 454, -644, 120, function() panel:Hide() end)
    end
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusGroupWindow" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusGroupWindow") end
    panel.close:SetShown(not host)
    panel:SetScale(1)
    panel:SetParent(host or UIParent)
    panel:ClearAllPoints()
    panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel:SetFrameStrata(host and host:GetFrameStrata() or "FULLSCREEN_DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel() + 1) end
    if not host and WoWStatusSetup then WoWStatusSetup:Hide() end
    panel:SetMovable(not host)
    panel:RegisterForDrag("LeftButton")
    if host then panel:SetScript("OnDragStart", nil)
    else panel:SetScript("OnDragStart", panel.StartMoving) end
    panel:SetScript("OnDragStop", panel.StopMovingOrSizing)
    panel.status:SetText("")
    panel.name:SetText(database.player_name or "")
    panel.input:SetText("")
    renderGroups()
    panel:Show()
end
