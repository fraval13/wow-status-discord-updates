-- Account-wide group choices, with per-character join times and history boundaries.
WoWStatusGroups = {}
local G, S = WoWStatusGroups, WoWStatusSafe
local T = WoWStatusLocale.T
local getCharacter, database, report, panel
local MAX_GROUPS = 8

-- One-way fingerprints of retired routing IDs. These are not usable group
-- names or route keys. Never put the underlying values here. Empty: the owner
-- chose to keep the groups players use (the two retired in 0.16.0 work again).
local RETIRED = {
}
G.RETIRED_MESSAGE="This exposed group is retired. Ask its owner privately for the replacement name."
local function hash(text)
    local a,b,c=5381,2166136261,104729
    for i=1,#text do
        local byte=text:byte(i)
        a=(a*33+byte)%4294967296
        b=(b*65599+byte)%4294967296
        c=(c*131+byte)%4294967296
    end
    return string.format("%08x%08x%06x",a,b,c%16777216)
end
function G.retired(id)
    return type(id)=="string" and #id==22 and id:match("^[a-f0-9]+$")~=nil and RETIRED[hash(id)]==true
end
function G.valid(id)
    return type(id)=="string" and #id==22 and id:match("^[a-f0-9]+$")~=nil and not G.retired(id)
end
function G.key(text)
    text = S.trim(text)
    local _, characters = text:gsub("[^\128-\191]", "")
    if text == "" or characters > 80 or text:find(S.CONTROL) then return nil end
    local canonical=WoWStatusCaseFold(text)
    if G.retired(canonical) then return nil,nil,G.RETIRED_MESSAGE end
    local id=hash(canonical)
    if G.retired(id) then return nil,nil,G.RETIRED_MESSAGE end
    return id,text
end
-- A group's name is its only protection (issue #151): the channel is derived from
-- it with public code, so names can be guessed offline. These help players pick
-- one that cannot be. The hash and channel scheme stay as they are.
-- Letters and digits that cannot be mistaken for each other (no 0/o, 1/i/l).
local ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
local GROUPS, GROUP_LENGTH = 5, 4 -- 20 symbols of about 5 bits: roughly 99 bits
local mix
local function draw(count)
    -- The client's random source does the work. The clock-seeded offset only
    -- keeps two sessions apart on a client whose source restarts the same way.
    if not mix then
        mix = (tonumber(S.call(time)) or 0) + math.floor((tonumber(S.call(GetTime)) or 0) * 1000)
            + math.floor(tonumber(S.call(debugprofilestop)) or 0)
        mix = mix % 4294967296
    end
    mix = (mix * 69069 + 1) % 4294967296
    return (math.random(count) - 1 + mix) % count + 1
end
-- A new, long, made-up group name such as "k7qm-4xfz-pr2d-9hwt-cn3b".
function G.generate()
    local parts = {}
    for part = 1, GROUPS do
        local symbols = {}
        for i = 1, GROUP_LENGTH do
            local at = draw(#ALPHABET)
            symbols[i] = ALPHABET:sub(at, at)
        end
        parts[part] = table.concat(symbols)
    end
    return table.concat(parts, "-")
end
G.WEAK_MESSAGE = "Short or ordinary names can be guessed by strangers, who would then see your group's activity. "
    .. "Use a longer, made-up name, or let the addon create one."
local MIN_LENGTH, MIN_VARIETY = 16, 8
-- Only letters and digits: "Silver-Hand" and "silver hand" compare equal.
-- Explicit byte ranges, not %w or %p, which follow the C library's locale.
local function bare(text)
    return (WoWStatusCaseFold(text):gsub("[%z\1-\47\58-\64\91-\96\123-\127]", ""))
end
-- True when a typed group name is easy to guess: short, one plain word, few
-- different characters, or just this player's, guild's or realm's name. Only a
-- warning: the player may use it anyway, and saved groups are never checked.
function G.weak(name)
    if type(name) ~= "string" then return false end
    local text = WoWStatusCaseFold(S.trim(name))
    if text == "" then return false end
    local _, length = text:gsub("[^\128-\191]", "")
    if length < MIN_LENGTH then return true end
    local seen, variety = {}, 0
    for symbol in text:gmatch("[^\128-\191][\128-\191]*") do
        if not symbol:find(S.SPACE) and not seen[symbol] then seen[symbol] = true; variety = variety + 1 end
    end
    if variety < MIN_VARIETY then return true end
    if not text:find("[^a-z]") then return true end -- a single word of plain letters
    local compact = bare(text)
    local player, realm = S.string(S.call(UnitName, "player")), S.string(S.call(GetRealmName))
    local guild = S.string(S.call(GetGuildInfo, "player"))
    for _, known in ipairs({player or "", guild or "", realm or "", (player or "") .. (realm or "")}) do
        if known ~= "" and compact == bare(known) then return true end
    end
    return false
end
local CHANNEL_PREFIX = "WStatus"
function G.channel(id) return CHANNEL_PREFIX .. id end
-- The group ID in a group channel name (any case), or nil for other channels.
function G.channelId(name)
    if type(name) ~= "string" then return nil end
    local lowered = name:lower()
    if lowered:sub(1, #CHANNEL_PREFIX) ~= CHANNEL_PREFIX:lower() then return nil end
    local id = lowered:sub(#CHANNEL_PREFIX + 1)
    if G.valid(id) then return id end
end
function G.selected(character)
    return character and character.group_ids or {}
end
function G.contains(character, id)
    return character and character.group_ids and character.group_ids[id] ~= nil
end
-- Shared history follows account membership, not the current character's age.
-- Character joined_at remains available for character-specific exports.
function G.historySince(id)
    return database and database.account_group_joined_at and database.account_group_joined_at[id]
end
local function apply(character, force)
    if character.legacy_upload and not force then return end
    local previous, selected, now = character.group_ids or {}, {}, S.now()
    for id, label in pairs(database.account_groups) do
        selected[id] = previous[id] or {joined_at = now, label = label}
        selected[id].label = label
        -- A join time ahead of realm time was saved on a fast PC clock (issue #7).
        if type(selected[id].joined_at) == "number" and selected[id].joined_at > now then selected[id].joined_at = now end
        if not previous[id] and character.settings.enabled
            and character.settings.fields.level and character.settings.collection.level then
            selected[id].baseline_level = character == getCharacter() and WoWStatusAdapter.level()
                or (character.snapshot and character.snapshot.level)
        end
    end
    character.group_ids = selected
    character.legacy_upload = false
    character.player_name = database.player_name or ""
    S.stampExport(character)
end
function G.init(db, getter, reporter)
    database, getCharacter, report = db, getter, reporter
    local removed=false
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
                if G.retired(id) then removed=true;S.call(LeaveChannelByName,G.channel(id))
                elseif not database.account_groups[id] then
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
    for id in pairs(database.account_groups) do
        if G.retired(id) then
            database.account_groups[id]=nil;removed=true
            S.call(LeaveChannelByName,G.channel(id))
        end
    end
    -- A legacy companion choice skips ordinary account propagation. Retirement
    -- still applies to every saved character, including those legacy selections.
    for _,saved in pairs(database.characters) do
        for id in pairs(saved.group_ids or {}) do
            if G.retired(id) then
                saved.group_ids[id]=nil;removed=true
                S.call(LeaveChannelByName,G.channel(id))
            end
        end
    end
    local channels=database.popups and database.popups.joined_channels
    if type(channels)=="table" then
        for name in pairs(channels) do
            if type(name)=="string" and name:sub(1,7):lower()=="wstatus" and G.retired(name:sub(8):lower()) then
                S.call(LeaveChannelByName,name);channels[name]=nil;removed=true
            end
        end
    end
    -- Nothing is retired any more: drop the notice an earlier version saved.
    if not next(RETIRED) then database.retired_groups_removed=nil end
    if removed then
        database.retired_groups_removed=true
        if not database.retired_group_notice then report(G.RETIRED_MESSAGE);database.retired_group_notice=true end
    end
    local joined, now = {}, S.now()
    for id in pairs(database.account_groups) do
        local at = database.account_group_joined_at and database.account_group_joined_at[id]
        if not at then
            -- Upgrade old saves from the earliest membership still retained.
            for _, character in pairs(database.characters) do
                local member = character.group_ids and character.group_ids[id]
                if member and type(member.joined_at)=="number" then
                    at = math.min(at or S.now(), member.joined_at)
                end
            end
        end
        -- A join time ahead of realm time was saved on a fast PC clock (issue #7).
        joined[id] = type(at) == "number" and math.min(at, now) or now
    end
    database.account_group_joined_at = joined
    for _, character in pairs(database.characters) do apply(character) end
end
local function update(text, playerName)
    local selected, count = {}, 0
    for label in text:gmatch("[^\r\n]+") do
        local id, cleaned, reason = G.key(label)
        if not id then return false, reason or "Use a non-empty group name of up to 80 characters, one per line." end
        if selected[id] and WoWStatusCaseFold(selected[id].label) ~= WoWStatusCaseFold(cleaned) then
            return false, "These group names collide; choose a different name."
        end
        if not selected[id] then
            count = count + 1
            if count > MAX_GROUPS then return false, "Choose at most 8 group IDs." end
            selected[id] = {label = cleaned}
        end
    end
    playerName = S.trim(playerName)
    if #playerName > 40 or playerName:find(S.CONTROL_OR_PIPE) then return false, "Use a name of up to 40 characters." end
    local joined = {}
    for id in pairs(selected) do
        joined[id] = database.account_group_joined_at[id] or S.now()
    end
    database.account_group_joined_at = joined
    database.account_groups = {}
    for id, member in pairs(selected) do database.account_groups[id] = member.label end
    local renamed = (database.player_name or "") ~= playerName
    database.player_name = playerName
    database.retired_groups_removed=nil
    for _, saved in pairs(database.characters) do apply(saved, true) end
    if WoWStatusPopups then WoWStatusPopups.groupsChanged() end
    if G.announce then G.announce() end
    -- Members online now get the new name at once, not at the next login.
    if renamed and WoWStatusRoster and WoWStatusRoster.changed then WoWStatusRoster.changed() end
    return true, "Groups saved for all characters."
end
G.update = update
-- Listed ("public") groups: the account's own choice, per group. A listed group's
-- name goes to members of this account's other groups, who can join it from
-- Browse groups. Unlisted groups are never sent anywhere.
function G.isListed(id) return database ~= nil and type(database.listed_groups) == "table" and database.listed_groups[id] == true end
function G.setListed(id, listed)
    if not database or not (database.account_groups or {})[id] then return false end
    database.listed_groups = type(database.listed_groups) == "table" and database.listed_groups or {}
    database.listed_groups[id] = listed == true or nil
    if WoWStatusRoster and WoWStatusRoster.listingChanged then WoWStatusRoster.listingChanged(id, listed == true) end
    return true
end
-- Listed groups with their names: {[id] = name}.
function G.listed()
    local result = {}
    for id, name in pairs(database and database.account_groups or {}) do
        if G.isListed(id) then result[id] = name end
    end
    return result
end
-- Join a group by name (Browse groups).
function G.join(name)
    local id, cleaned, reason = G.key(name or "")
    if not id then return false, reason or "Enter one group ID of up to 80 characters." end
    if (database.account_groups or {})[id] then return false, "That group is already in your list." end
    local labels, count = {}, 0
    for _, label in pairs(database.account_groups or {}) do table.insert(labels, label); count = count + 1 end
    if count >= MAX_GROUPS then return false, "You can add up to 8 groups. Remove one before adding another." end
    table.insert(labels, cleaned)
    return update(table.concat(labels, "\n"), database.player_name or "")
end
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
    panel.count:SetText(T("Groups") .. " (" .. #groups .. " / " .. MAX_GROUPS .. ")")
    panel.empty:SetShown(#groups == 0)
    for i, row in ipairs(panel.rows) do
        local group = groups[i]
        row.id = group and group.id
        row.fullLabel = group and group.label
        row:SetShown(group ~= nil)
        if group then
            row.label:SetText((group.label:gsub("|", "||")))
            row.listed:SetChecked(G.isListed(group.id))
        end
    end
end
local function saveList(groups)
    local labels = {}
    for _, group in ipairs(groups) do table.insert(labels, group.label) end
    local ok, message = update(table.concat(labels, "\n"), panel.name:GetText())
    panel.status:SetText(T(message))
    report(message)
    if ok then renderGroups() end
    return ok
end
function G.show(host)
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusGroupWindow", UIParent)
        panel:SetSize(620, 866)
        panel:SetPoint("CENTER")
        panel:SetFrameStrata("DIALOG")
        panel:EnableMouse(true)
        local bg = panel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.025,.035,.055,.96);panel.background=bg
        if WoWStatusTheme and WoWStatusTheme.attachBackground then WoWStatusTheme.attachBackground(bg) end
        local function label(text, y, width)
            local f = panel:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
            f:SetPoint("TOPLEFT", 24, y); f:SetWidth(width or 570)
            f:SetJustifyH("LEFT"); f:SetText(T(text))
            return f
        end
        local function button(parent, text, x, y, width, action)
            local widget = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
            widget:SetPoint("TOPLEFT", x, y); widget:SetSize(width, 28)
            widget:SetText(T(text)); widget:SetScript("OnClick", action)
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
        label("Your name (optional)", -62)
        panel.name = input(-92, 40)
        local function saveName() saveList(groupList()) end
        panel.saveName = button(panel, "Save name", 454, -92, 120, saveName)
        panel.name:SetScript("OnEnterPressed", saveName)
        label("Group ID", -146)
        label("Use the same ID as your friends.\nAdding or removing a group saves for all your characters.", -182)
        panel.input = input(-234, 80)
        -- A refusal is shown under the input and in chat: in Options the page
        -- scrolls, so a message lower down could go unseen.
        local function refuse(message)
            panel.status:SetText(T(message))
            report(message)
        end
        local function add()
            local id, cleaned, reason = G.key(panel.input:GetText())
            if not id then
                refuse(reason or "Enter one group ID of up to 80 characters.")
                return
            end
            if (database.account_groups or {})[id] then
                refuse("That group is already in your list.")
                return
            end
            local groups = groupList()
            if #groups >= MAX_GROUPS then
                refuse("You can add up to 8 groups. Remove one before adding another.")
                return
            end
            -- A guessable name is the player's call: warn once, then Add anyway.
            if G.weak(cleaned) and panel.confirmed ~= cleaned then
                panel.confirmed = cleaned
                panel.add:SetText(T("Add anyway"))
                refuse(G.WEAK_MESSAGE)
                return
            end
            table.insert(groups, {id = id, label = cleaned})
            if saveList(groups) then
                panel.confirmed = nil
                panel.add:SetText(T("Add"))
                panel.input:SetText("")
                panel.input:SetFocus()
            end
        end
        panel.add = button(panel, "Add", 454, -234, 120, add)
        panel.input:SetScript("OnEnterPressed", add)
        -- Editing the name takes back an earlier "Add anyway".
        panel.input:SetScript("OnTextChanged", function(self)
            if panel.confirmed and S.trim(self:GetText()) ~= panel.confirmed then
                panel.confirmed = nil
                panel.add:SetText(T("Add"))
            end
        end)
        panel.status = label("", -270)
        panel.status:SetTextColor(1, .82, .25)
        -- The recommended path: let the addon make a name nobody can guess.
        panel.create = button(panel, "Create a group", 24, -330, 170, function()
            local name = G.generate()
            panel.created:SetText(name); panel.created.value = name
            -- Not focused for the player: a focused text box would take the
            -- controller's buttons. Clicking into it selects the whole name.
            panel.created:Show(); panel.join:Show()
            panel.createHint:SetText(T("Click it, copy with Ctrl+C and send it privately. Every friend must type exactly this name."))
        end)
        -- Read-only but selectable, so it can be copied.
        panel.created = CreateFrame("EditBox", nil, panel, "InputBoxTemplate")
        panel.created:SetPoint("TOPLEFT", 206, -330); panel.created:SetSize(236, 30)
        panel.created:SetFontObject("ChatFontNormal")
        panel.created:SetAutoFocus(false); panel.created:SetMultiLine(false); panel.created:SetMaxLetters(80)
        panel.created:SetScript("OnTextChanged", function(self, typed)
            if typed and self.value then self:SetText(self.value); self:HighlightText() end
        end)
        panel.created:SetScript("OnEditFocusGained", function(self) self:HighlightText() end)
        panel.created:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
        panel.created:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
        panel.join = button(panel, "Join it", 454, -330, 120, function()
            local name = panel.created.value
            if not name then return end
            panel.input:SetText(name)
            add()
            if (database.account_groups or {})[G.key(name)] then
                panel.created.value = nil
                panel.created:SetText(""); panel.created:Hide(); panel.join:Hide()
                panel.createHint:SetText(T("Recommended: let the addon create a name nobody can guess."))
            end
        end)
        panel.createHint = label("Recommended: let the addon create a name nobody can guess.", -366)
        panel.createHint:SetFontObject("GameFontHighlight")
        panel.protection = label("Anyone who knows a group's name can read its activity. Share it privately, "
            .. "never in public chat, on a stream or in a screenshot.", -400)
        panel.protection:SetFontObject("GameFontHighlight")
        panel.count = label("", -446, 400)
        -- Groups friends listed, to join with one click.
        panel.browse = button(panel, "Browse groups", 430, -440, 144, function(self)
            local list = WoWStatusRoster and WoWStatusRoster.listings and WoWStatusRoster.listings() or {}
            if #list == 0 then refuse("No listed groups yet. Friends list a group by ticking Listed on their Groups page."); return end
            local items = {}
            for _, item in ipairs(list) do
                items[#items + 1] = {label = item.name:gsub("|", "||") .. "  |cff9d9d9d" .. T("listed by") .. " " .. item.by:gsub("|", "||") .. "|r", value = item.name}
            end
            WoWStatusUI.menu(self, items, function(name)
                local ok, message = G.join(name)
                refuse(message)
                if ok then renderGroups() end
            end)
        end)
        panel.empty = label("No groups selected. Enter a group ID above and click Add.", -484)
        panel.rows = {}
        for i = 1, MAX_GROUPS do
            local row = CreateFrame("Frame", nil, panel)
            row:SetPoint("TOPLEFT", 24, -478 - (i - 1) * 36)
            row:SetSize(550, 32)
            row.label = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
            row.label:SetPoint("TOPLEFT", 0, -6); row.label:SetWidth(290)
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
            -- Listed: friends in your other groups can see and join it.
            row.listed = CreateFrame("CheckButton", nil, row, "UICheckButtonTemplate")
            row.listed:SetPoint("TOPLEFT", 300, 0); row.listed:SetSize(30, 30)
            row.listedLabel = row.listed:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
            row.listedLabel:SetPoint("TOPLEFT", 32, -8); row.listedLabel:SetText(T("Listed"))
            row.listed:SetScript("OnClick", function(self) G.setListed(row.id, self:GetChecked() and true or false) end)
            row.listed:SetScript("OnEnter", function(self)
                if GameTooltip then
                    GameTooltip:SetOwner(self, "ANCHOR_RIGHT"); GameTooltip:SetText(T("Listed group"))
                    GameTooltip:AddLine(T("Friends in your other groups can see this group under Browse groups and join it. Leave it off for a private group."), 1, 1, 1, true)
                    GameTooltip:Show()
                end
            end)
            row.listed:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
            row.remove = button(row, "Remove", 430, 0, 120, function()
                local retained = {}
                for _, group in ipairs(groupList()) do
                    if group.id ~= row.id then table.insert(retained, group) end
                end
                saveList(retained)
            end)
            table.insert(panel.rows, row)
        end
        panel.close = button(panel, "Close", 454, -810, 120, function() panel:Hide() end)
    end
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusGroupWindow" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusGroupWindow") end
    panel.close:SetShown(not host)
    panel.background:SetShown(not host)
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
    panel.status:SetText(database.retired_groups_removed and T(G.RETIRED_MESSAGE) or "")
    panel.name:SetText(database.player_name or "")
    panel.input:SetText("")
    panel.confirmed = nil
    panel.add:SetText(T("Add"))
    panel.created.value = nil
    panel.created:SetText(""); panel.created:Hide(); panel.join:Hide()
    panel.createHint:SetText(T("Recommended: let the addon create a name nobody can guess."))
    renderGroups()
    panel:Show()
end
