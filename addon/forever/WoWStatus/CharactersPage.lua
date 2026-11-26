-- The Characters page of the main window: a card per character under each
-- player's header, the "Play together now" band, "Where we are", the pin stars
-- and collapsible sections. Part of WoWStatusRoster; see Roster.lua, which
-- loads first and owns the list's data and its messages (#230).
local R, S = WoWStatusRoster, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local I = R.internal
local key, state, shownRace, shownTitle, counted, onlineSignature, updateSyncButton =
    I.key, I.state, I.shownRace, I.shownTitle, I.counted, I.onlineSignature, I.updateSyncButton
local page

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
-- Characters page: one bordered card per character under each player's header.
local UI = WoWStatusUI
-- The card grew by the profession strip's height: a row of icons with each
-- skill level under its icon, centred between the texts and the XP bar.
local CARD, HEADER, GAP = 114, 26, 6
local PROFESSION_ICON, PROFESSION_PITCH, PROFESSION_TOP = 18, 26, -62
-- The pin star (#170): a Button, so mouse and controller both press it.
local STAR = "Interface\\TargetingFrame\\UI-RaidTargetingIcon_1"
R.STAR_REPEAT = 0.5
local starClicked
local function starTooltip(self)
    if not GameTooltip or not self.pinKind then return end
    local on = R.pinned(self.pinKind, self.pinName) ~= nil
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(T(on and "Unpin" or (self.pinKind == "player" and "Pin this player to the top" or "Pin this character to the top")))
    GameTooltip:AddLine(T("Pinned friends come first on the Characters page, online before offline, in the order you pinned them. Only you see this; nothing is sent."), 1, 1, 1, true)
    GameTooltip:Show()
end
local function star(parent)
    local b = CreateFrame("Button", nil, parent)
    b:SetSize(18, 18)
    b.icon = b:CreateTexture(nil, "ARTWORK"); b.icon:SetAllPoints(); b.icon:SetTexture(STAR)
    b:SetScript("OnClick", function(self)
        if not self.pinKind then return end
        -- The list reorders at once, so this star may now belong to someone
        -- else: a quick second click (a double-click) is ignored, and the
        -- tooltip, which described the one just pinned, closes.
        local now = S.uptime()
        if starClicked and now - starClicked < R.STAR_REPEAT then return end
        starClicked = now
        R.togglePin(self.pinKind, self.pinName)
        if GameTooltip and GameTooltip.IsOwned and GameTooltip:IsOwned(self) then GameTooltip:Hide() end
    end)
    b:SetScript("OnEnter", starTooltip)
    b:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    return b
end
local function showStar(b, kind, name)
    b.pinKind, b.pinName = kind, name
    local on = R.pinned(kind, name) ~= nil
    b.icon:SetAlpha(on and 1 or .3)
    b.icon:SetVertexColor(on and 1 or .6, on and 1 or .6, on and 1 or .6)
    b:Show()
end
local function header(index)
    local h = CreateFrame("Frame", nil, page.list)
    h:SetSize(680, HEADER)
    h.text = UI.header(h, "", 0, -4, 650)
    h.star = star(h); h.star:SetPoint("TOPRIGHT", -6, -3)
    page.headers[index] = h
    return h
end
local function card(index)
    local c = UI.box(page.list, 680, CARD, "Button")
    c.portrait = c:CreateTexture(nil, "ARTWORK"); c.portrait:SetPoint("TOPLEFT", 10, -9); c.portrait:SetSize(40, 40)
    c.badge = UI.levelBadge(c, 24); c.badge:SetPoint("TOPLEFT", 34, -30)
    c.name = UI.text(c, "GameFontNormalLarge", 66, -8, 300)
    c.dot = c:CreateTexture(nil, "OVERLAY"); c.dot:SetPoint("TOPLEFT", 66, -32); c.dot:SetSize(14, 14)
    c.status = UI.text(c, "GameFontHighlightSmall", 82, -33, 290)
    c.itemLevel = UI.text(c, "GameFontHighlightSmall", 66, -48, 280)
    c.xp = UI.xpBar(c, 660, 14); c.xp:SetPoint("BOTTOMLEFT", 10, 6)
    -- Professions: the game's icon with its skill level underneath. Plain
    -- textures, so there is nothing here for a controller to step onto; the
    -- names and maximums are in the card's tooltip, and the card itself still
    -- opens the character's profile.
    c.professions = {}
    for i = 1, R.PROFESSION_MAX do
        local slot = {}
        slot.icon = c:CreateTexture(nil, "ARTWORK"); slot.icon:SetSize(PROFESSION_ICON, PROFESSION_ICON)
        slot.icon:SetPoint("TOPLEFT", 0, PROFESSION_TOP)
        slot.skill = UI.text(c, "GameFontHighlightSmall", 0, PROFESSION_TOP - PROFESSION_ICON - 1, PROFESSION_PITCH, "CENTER")
        c.professions[i] = slot
    end

    c.class = UI.text(c, "GameFontHighlight", 380, -10, 266, "RIGHT")
    c.latest = UI.text(c, "GameFontDisableSmall", 380, -30, 266, "RIGHT")
    c.groups = UI.text(c, "GameFontHighlightSmall", 380, -44, 266, "RIGHT")
    c.star = star(c); c.star:SetPoint("TOPRIGHT", -8, -9)
    -- Clicking a character shows its entries on the Activity page.
    c:SetScript("OnClick", function(self)
        -- Clicking a character opens their profile (with Show activity on it).
        if self.character and WoWStatusProfile then WoWStatusProfile.show(self.character, self.player)
        elseif self.character and WoWStatusJournal.showCharacter then WoWStatusJournal.showCharacter(self.character.name) end
    end)
    c:SetScript("OnEnter", function(self)
        UI.tint(self, true)
        if GameTooltip and self.character then
            local character = self.character
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT"); GameTooltip:SetText(character.name)
            -- The shared statistics in full.
            local function line(label, value) if value then GameTooltip:AddDoubleLine(T(label), value, .8, .8, .8, 1, 1, 1) end end
            line("Gold", S.number(character.gold) and UI.money(character.gold))
            line("Gold earned", S.number(character.earned) and UI.money(character.earned))
            line(character.quests_source == "tracked_since" and "Quests (tracked)" or "Quests",
                S.number(character.quests) and tostring(character.quests))
            line("Monsters killed", S.number(character.kills) and tostring(character.kills))
            line("Played", S.number(character.played) and UI.duration(character.played))
            line("Honorable kills", S.number(character.honor_kills) and character.honor_kills > 0 and tostring(character.honor_kills))
            line("Dungeons cleared", S.number(character.dungeons) and character.dungeons > 0 and tostring(character.dungeons))
            line("Mounts", S.number(character.mounts) and character.mounts > 0 and tostring(character.mounts))
            local average=R.itemLevel(character.name)
            line("Average item level", average and string.format("%.2f",average))
            for _, item in ipairs(R.professionsOf(character)) do
                line(item.name, item.max and (item.skill .. " / " .. item.max) or tostring(item.skill))
            end
            if R.isUnreachable(character.name) then
                GameTooltip:AddLine(T("Your live updates did not reach this character. Ask them to /reload, or check that you are on the same realm type."), 1, .4, .4, true)
            end
            GameTooltip:AddLine(T("Click to open this character's profile."), 1, 1, 1, true); GameTooltip:Show()
        end
    end)
    c:SetScript("OnLeave", function(self) UI.tint(self, false); if GameTooltip then GameTooltip:Hide() end end)
    page.lines[index] = c
    return c
end

-- Collapsed sections, saved account-wide by section key.
function R.collapsed(key)
    local roster = state()
    roster.collapsed = type(roster.collapsed) == "table" and roster.collapsed or {}
    return roster.collapsed[key] == true
end
function R.toggle(key)
    local roster = state()
    roster.collapsed = type(roster.collapsed) == "table" and roster.collapsed or {}
    roster.collapsed[key] = not roster.collapsed[key] or nil
    R.render()
end
local SECTION = 30
local function sectionButton()
    local b = CreateFrame("Button", nil, page.list)
    b:SetSize(680, SECTION - 4)
    b.bg = b:CreateTexture(nil, "BACKGROUND"); b.bg:SetAllPoints(); b.bg:SetColorTexture(1, .82, 0, .08)
    b.icon = b:CreateTexture(nil, "ARTWORK"); b.icon:SetPoint("TOPLEFT", 4, -5); b.icon:SetSize(16, 16)
    b.text = UI.text(b, "GameFontNormalLarge", 26, -5, 640)
    b:SetScript("OnClick", function(self) if self.key then R.toggle(self.key) end end)
    return b
end
-- Places a section heading at y with its fold icon and text; returns the y below it.
local function placeHeading(b, key, y, text)
    local closed = R.collapsed(key)
    b.key = key
    b:ClearAllPoints(); b:SetPoint("TOPLEFT", 0, -y)
    b.icon:SetTexture(closed and "Interface\\Buttons\\UI-PlusButton-Up" or "Interface\\Buttons\\UI-MinusButton-Up")
    b.text:SetText(text)
    b:Show()
    return y + SECTION, closed
end
local function section(index)
    local b = sectionButton()
    page.sections[index] = b
    return b
end

function R.refreshQuests()
    if not I.db then return end
    R.render()
    if WoWStatusFirsts and WoWStatusFirsts.render then WoWStatusFirsts.render() end
    if WoWStatusMainWindow and WoWStatusMainWindow.active() == "overview" and WoWStatusOverview then WoWStatusOverview.render() end
end

-- The "Play together now" band at the top of the list: its section heading, a
-- level-window control, then one row per friend with Whisper and Invite.
local TOGETHER_BAR, TOGETHER_ROW = 30, 30
local function enable(button, on)
    if not UI.call(button, on and "Enable" or "Disable") then UI.call(button, "SetEnabled", on) end
end
local function smallButton(parent, label, x, width, onClick)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetPoint("TOPLEFT", x, -4); b:SetSize(width, 22); b:SetText(T(label))
    b:SetScript("OnClick", onClick)
    return b
end
local function togetherBar()
    local bar = CreateFrame("Frame", nil, page.list)
    bar:SetSize(680, TOGETHER_BAR)
    bar.label = UI.text(bar, "GameFontHighlight", 12, -8, 200)
    bar.less = smallButton(bar, "-", 216, 28, function() R.setTogetherRange(R.togetherRange() - 1) end)
    bar.more = smallButton(bar, "+", 248, 28, function() R.setTogetherRange(R.togetherRange() + 1) end)
    bar.note = UI.text(bar, "GameFontDisableSmall", 288, -10, 390)
    page.togetherBar = bar
    return bar
end
local function togetherRow(index)
    local row = CreateFrame("Frame", nil, page.list)
    row:SetSize(680, TOGETHER_ROW)
    row.name = UI.text(row, "GameFontNormal", 24, -8, 190)
    row.level = UI.text(row, "GameFontHighlightSmall", 216, -10, 110)
    row.info = UI.text(row, "GameFontDisableSmall", 330, -10, 160)
    row.whisper = smallButton(row, "Whisper", 494, 88, function(self) if self.target then R.whisper(self.target.name) end end)
    row.invite = smallButton(row, "Invite", 588, 88, function(self)
        if self.target and R.partyInvite(self.target) then R.render() end
    end)
    row.invite:SetScript("OnEnter", function(self)
        if GameTooltip and self.target then
            GameTooltip:SetOwner(self, "ANCHOR_TOP"); GameTooltip:SetText(T("Invite to your group"))
            if self.target.blocked then GameTooltip:AddLine(T(self.target.blocked), 1, .4, .4, true) end
            GameTooltip:Show()
        end
    end)
    row.invite:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    -- The reason shows on a disabled button's tooltip too, where the client allows it.
    UI.call(row.invite, "SetMotionScriptsWhileDisabled", true)
    page.together[index] = row
    return row
end
-- Draws the band from y down and returns the y below it.
local function renderTogether(y, groups)
    page.togetherHead = page.togetherHead or sectionButton()
    local b = page.togetherHead
    local data = R.together(groups)
    local closed
    y, closed = placeHeading(b, "together", y, T("Play together now") .. "   " .. WoWStatusUI.MUTED_CODE
        .. (data.range == 1 and TF("%d within 1 level", data.inRange) or TF("%d within %d levels", data.inRange, data.range)) .. "|r")
    local bar = page.togetherBar or togetherBar()
    local shown = 0
    if not closed then
        bar:ClearAllPoints(); bar:SetPoint("TOPLEFT", 0, -y)
        bar.label:SetText(TF("Level range: ±%d", data.range))
        enable(bar.less, data.range > 1); enable(bar.more, data.range < R.TOGETHER_MAX)
        local list = data.rows
        if not data.level then
            bar.note:SetText(T("Your level is not known yet."))
        elseif #list == 0 and (data.online or 0) == 0 then
            bar.note:SetText(T("No friends who share their list are online right now."))
        elseif #list == 0 then
            bar.note:SetText(T("No online friends within your level range."))
        else
            bar.note:SetText(T("Closest level first."))
        end
        bar:Show()
        y = y + TOGETHER_BAR
        for _, item in ipairs(list) do
            shown = shown + 1
            local row = page.together[shown] or togetherRow(shown)
            row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -y)
            local name = (item.name:match("^[^-]+") or item.name):gsub("|", "||")
            local colour = UI.classColour(item.class)
            row.name:SetText(colour and (colour .. name .. "|r") or name)
            row.level:SetText(TF("Level %d", item.level) .. " (" .. (item.diff == 0 and "±0" or string.format("%+d", item.diff)) .. ")")
            -- Why Invite is greyed out, or else where they were last.
            row.info:SetText(item.blocked and ("|cffff7777" .. T(item.blocked) .. "|r")
                or (item.zone and item.zone:gsub("|", "||")) or "")
            row.whisper.target, row.invite.target = item, item
            enable(row.whisper, not item.noWhisper)
            enable(row.invite, item.blocked == nil)
            row:Show()
            y = y + TOGETHER_ROW
        end
    else
        bar:Hide()
    end
    for i = shown + 1, #page.together do page.together[i]:Hide() end
    return y + 4
end

-- "Where we are": a section heading, then one row per zone with who is there
-- and how old each report is. The rows only show text; the heading folds it.
local WHERE_ROW = 22
local function reportAge(seconds)
    if seconds < 60 then return T("just now") end
    return TF("%d min ago", math.floor(seconds / 60))
end
local function whereRow(index)
    local row = CreateFrame("Frame", nil, page.list)
    row:SetSize(680, WHERE_ROW)
    -- One line each: a long zone or a crowded one is cut short, never wrapped into the next row.
    row.zone = UI.text(row, "GameFontNormal", 24, -4, 250)
    row.members = UI.text(row, "GameFontHighlightSmall", 280, -6, 400)
    UI.call(row.zone, "SetWordWrap", false); UI.call(row.members, "SetWordWrap", false)
    page.where[index] = row
    return row
end
-- Draws the section from y down and returns the y below it.
local function renderWhere(y, groups)
    page.whereHead = page.whereHead or sectionButton()
    local b = page.whereHead
    local data = R.whereWeAre(groups)
    local closed
    y, closed = placeHeading(b, "where", y, T("Where we are") .. "   " .. WoWStatusUI.MUTED_CODE
        .. (data.people == 1 and T("1 friend") or TF("%d friends", data.people))
        .. ", " .. ((data.count or 0) == 1 and T("1 zone") or TF("%d zones", data.count or 0)) .. "|r")
    page.whereNote = page.whereNote or UI.text(page.list, "GameFontDisableSmall", 24, 0, 650)
    local note, shown = page.whereNote, 0
    if not closed then
        note:ClearAllPoints(); note:SetPoint("TOPLEFT", 24, -(y + 4))
        note:SetText(#data.zones == 0 and TF("No online friend has reported a zone in the last %d minutes.", R.WHERE_MAX_AGE / 60)
            or T("Your zone first, then the newest report."))
        note:Show()
        y = y + WHERE_ROW
        for _, item in ipairs(data.zones) do
            shown = shown + 1
            local row = page.where[shown] or whereRow(shown)
            row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -y)
            local zone = item.zone:gsub("|", "||")
            row.zone:SetText(item.here and (zone .. " |cff40ff40(" .. T("your zone") .. ")|r") or zone)
            local names = {}
            for i, member in ipairs(item.members) do
                if i > R.WHERE_NAMES then
                    names[#names + 1] = TF("+%d more", #item.members - R.WHERE_NAMES)
                    break
                end
                local name = (member.name:match("^[^-]+") or member.name):gsub("|", "||")
                local colour = UI.classColour(member.class)
                names[#names + 1] = (colour and (colour .. name .. "|r") or name) .. " " .. WoWStatusUI.MUTED_CODE .. "(" .. reportAge(member.age) .. ")|r"
            end
            row.members:SetText(table.concat(names, ", "))
            row:Show()
            y = y + WHERE_ROW
        end
        if (data.more or 0) > 0 then
            shown = shown + 1
            local row = page.where[shown] or whereRow(shown)
            row:ClearAllPoints(); row:SetPoint("TOPLEFT", 0, -y)
            row.zone:SetText(WoWStatusUI.MUTED_CODE .. (data.more == 1 and T("+1 more zone") or TF("+%d more zones", data.more)) .. "|r")
            row.members:SetText("")
            row:Show()
            y = y + WHERE_ROW
        end
    else
        note:Hide()
    end
    for i = shown + 1, #page.where do page.where[i]:Hide() end
    I.whereDue, I.whereRevision = data.due, WoWStatusJournal.zoneRevision
    return y + 4
end

function R.render()
    if WoWStatusMainWindow then WoWStatusMainWindow.refresh("leaderboard") end
    if WoWStatusProfile and WoWStatusProfile.refreshQuests then WoWStatusProfile.refreshQuests() end
    if not page or not page.IsShown or not page:IsShown() then return end
    local index, headers, sections, y = 0, 0, 0, 0
    I.onlineSeen, I.partyChanged = onlineSignature(), false
    local groups = R.groups()
    y = renderTogether(y, groups)
    y = renderWhere(y, groups)
    local band = y
    for _, part in ipairs(R.sections(groups)) do
        sections = sections + 1
        local b = page.sections[sections] or section(sections)
        local summary = part.characters and ("   " .. WoWStatusUI.MUTED_CODE .. part.characters .. " " .. T(part.characters == 1 and "character" or "characters")
            .. ", " .. part.online .. " " .. T("online") .. "|r") or ""
        local closed
        y, closed = placeHeading(b, part.key, y, T(part.title):gsub("|", "||") .. summary)
        if not closed then
            -- The rows a player's heading covers right now: all of them, or only
            -- the ones online while the filter is on.
            local function visible(group)
                if not R.onlineOnly() then return group.rows end
                local shown = {}
                for _, character in ipairs(group.rows) do
                    if character.status == "online" then shown[#shown + 1] = character end
                end
                return shown
            end
            local covered = 0
            for _, group in ipairs(part.entries) do covered = covered + #visible(group) end
            if covered == 0 then
                headers = headers + 1
                local h = page.headers[headers] or header(headers)
                h:ClearAllPoints(); h:SetPoint("TOPLEFT", 12, -y)
                -- Say which of the two it is: nobody met yet, or nobody online now.
                local note = (#part.entries > 0 and R.onlineOnly()) and "Nobody from this group is online right now."
                    or "Nobody else seen in this group yet."
                h.text:SetText(WoWStatusUI.MUTED_CODE .. T(note) .. "|r"); h.star:Hide(); h:Show()
                y = y + HEADER
            end
            for _, group in ipairs(part.entries) do
                local rows = visible(group)
                if #rows > 0 then
                headers = headers + 1
                local h = page.headers[headers] or header(headers)
                h:ClearAllPoints(); h:SetPoint("TOPLEFT", 12, -y)
                -- The heading counts the cards under it, so the filter shows in it.
                -- The version note stays small and grey beside the title.
                h.text:SetText(shownTitle(counted(group.name, #rows)):gsub("|", "||") .. (group.note and ("   " .. WoWStatusUI.MUTED_CODE .. T(group.note) .. "|r") or "")); h:Show()
                if group.pinnable then showStar(h.star, "player", group.name) else h.star:Hide() end
                y = y + HEADER
                for _, character in ipairs(rows) do
                    if index >= 200 then break end
                    index = index + 1
                    local c = page.lines[index] or card(index)
                    c:ClearAllPoints(); c:SetPoint("TOPLEFT", 0, -y)
                    c.portraitKind = R.portrait(c.portrait, character.name, character.race, character.sex)
                    local name = (character.name:match("^[^-]+") or character.name):gsub("|", "||")
                    local colour = UI.classColour(character.class)
                    c.name:SetText(colour and (colour .. name .. "|r") or name)
                    c.badge:SetLevel(character.level); c.badge:SetShown(character.level ~= nil)
                    local class = character.class and T(character.class:sub(1, 1) .. character.class:sub(2):lower()) or T("Never met")
                    c.class:SetText(character.race and (shownRace(character.race) .. " " .. class) or class)
                    local online = character.status == "online"
                    -- Filled when online, a hollow ring when not, beside the status text (#185).
                    c.dot:SetTexture(online and UI.ONLINE_ICON or UI.OFFLINE_ICON)
                    local gold = S.number(character.gold) and UI.money(character.gold, true)
                    -- Live updates did not reach them (their client never confirmed).
                    local lost = not group.self and R.isUnreachable(character.name) and ("   |cffff5555" .. T("not reached") .. "|r") or ""
                    -- A muted friend says so on the card, so nobody wonders why they went quiet (#169).
                    local mode = not group.self and WoWStatusMutes and WoWStatusMutes.mode(character.name) or "show"
                    local muted = mode ~= "show" and ("   " .. WoWStatusUI.MUTED_CODE .. T(mode == "hide" and "hidden" or "muted") .. "|r") or ""
                    c.status:SetText(T(character.status) .. (gold and ("   " .. gold) or "") .. lost .. muted)
                    local xp = S.number(character.xp)
                    if character.level and character.level >= (WoWStatusAdapter.max_level or 999) then
                        c.xp:SetProgress(1,T("Maximum level"))
                    else
                        c.xp:SetProgress(xp and xp / 1000, xp and TF("XP %d%%", math.floor(xp / 10)) or T("XP unavailable"))
                        c.xp:Show()
                    end
                    local average=R.itemLevel(character.name)
                    c.itemLevel:SetText(T("Average item level:") .. " " .. (average and math.floor(average) or "—"))
                    local professions = R.professionsOf(character)
                    local span = #professions * PROFESSION_ICON + math.max(0, #professions - 1) * (PROFESSION_PITCH - PROFESSION_ICON)
                    local left = math.floor((680 - span) / 2)
                    for i, slot in ipairs(c.professions) do
                        local item = professions[i]
                        if item then
                            local x = left + (i - 1) * PROFESSION_PITCH
                            slot.icon:ClearAllPoints(); slot.icon:SetPoint("TOPLEFT", x, PROFESSION_TOP)
                            slot.icon:SetTexture("Interface\\Icons\\" .. item.icon); slot.icon:Show()
                            slot.skill:ClearAllPoints()
                            slot.skill:SetPoint("TOPLEFT", x - math.floor((PROFESSION_PITCH - PROFESSION_ICON) / 2), PROFESSION_TOP - PROFESSION_ICON - 1)
                            slot.skill:SetText(tostring(item.skill))
                        else
                            slot.icon:Hide(); slot.skill:SetText("")
                        end
                    end
                    -- Level and total deaths at the end of the card.
                    local facts = {}
                    if character.level then table.insert(facts, TF("Level %d", character.level)) end
                    local died = S.number(character.deaths)
                    if died then table.insert(facts, died == 1 and T("1 death") or TF("%d deaths", died)) end
                    local kills = S.number(character.kills)
                    if kills and kills > 0 then table.insert(facts, kills == 1 and T("1 kill") or TF("%d kills", kills)) end
                    c.latest:SetText(table.concat(facts, " · "))
                    local groups = character.groups and #character.groups > 0 and table.concat(character.groups, ", ") or ""
                    c.groups:SetText(groups ~= "" and (WoWStatusUI.MUTED_CODE .. T("Groups:") .. "|r " .. groups:gsub("|", "||")) or "")
                    c.text = c.name -- Older callers read a row's text.
                    c.kind, c.character, c.player = "character", character, group
                    if group.self then c.star:Hide() else showStar(c.star, "character", character.name) end
                    UI.tint(c, false)
                    c:Show()
                    y = y + CARD + GAP
                end
                end -- #rows > 0: a heading with no cards under it is left out
            end
        end
        y = y + 4
    end
    for i = index + 1, #page.lines do page.lines[i]:Hide() end
    for i = headers + 1, #page.headers do page.headers[i]:Hide() end
    for i = sections + 1, #page.sections do page.sections[i]:Hide() end
    page.list:SetHeight(math.max(1, y))
    page.empty:SetText(T(R.onlineOnly() and "Nobody is online right now." or "No characters yet."))
    page.empty:ClearAllPoints(); page.empty:SetPoint("TOPLEFT", 24, -(52 + band))
    page.empty:SetShown(index == 0 and sections == 0)
    page.count = index
end

local function build(parent)
    page = CreateFrame("Frame", "WoWStatusCharactersPage", parent); page:SetAllPoints(parent)
    I.page = page
    page.scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    page.scroll:SetPoint("TOPLEFT", 24, -44); page.scroll:SetSize(710, 430)
    page.list = CreateFrame("Frame", nil, page.scroll); page.list:SetSize(686, 32); page.lines, page.headers, page.sections = {}, {}, {}
    page.together, page.where = {}, {}
    page.scroll:SetScrollChild(page.list)
    page.empty = page:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    page.empty:SetPoint("TOPLEFT", 24, -12); page.empty:SetText(T("No characters yet."))
    page.share = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate")
    page.share:SetPoint("TOPLEFT", 24, -486); page.share:SetSize(32, 32)
    local shareLabel = page.share:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    shareLabel:SetPoint("TOPLEFT", 38, -8); shareLabel:SetText(T("Share my character list"))
    page.share:SetScript("OnClick", function(self) R.setSharing(self:GetChecked() and true or false) end)
    page.onlineOnly = CreateFrame("CheckButton", nil, page, "UICheckButtonTemplate")
    page.onlineOnly:SetPoint("TOPLEFT", 24, -4); page.onlineOnly:SetSize(32, 32)
    local onlineLabel = page.onlineOnly:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    onlineLabel:SetPoint("TOPLEFT", 34, -8); onlineLabel:SetText(T("Online only"))
    page.onlineOnly:SetScript("OnClick", function(self) R.setOnlineOnly(self:GetChecked() and true or false) end)
    page.onlineOnly:SetScript("OnEnter", function(self)
        if GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_TOP"); GameTooltip:SetText(T("Online only"))
            GameTooltip:AddLine(T("Shows only the characters online right now. Nothing is hidden from your friends and no progress is lost."), 1, 1, 1, true)
            GameTooltip:Show()
        end
    end)
    page.onlineOnly:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    page.visibility = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.visibility:SetPoint("TOPLEFT", 330, -486); page.visibility:SetSize(240, 28)
    page.visibility:SetText(T("Character visibility"))
    page.visibility:SetScript("OnClick", function() SlashCmdList.WOWSTATUS("visibility") end)
    page.sync = CreateFrame("Button", nil, page, "UIPanelButtonTemplate")
    page.sync:SetPoint("TOPLEFT", 594, -486); page.sync:SetSize(128, 28)
    page.sync:SetScript("OnClick", function() if R.syncNow() then R.whoLookup() end end)
    page.sync:SetScript("OnEnter", function(self)
        if GameTooltip then
            GameTooltip:SetOwner(self, "ANCHOR_TOP"); GameTooltip:SetText(T("Sync with everyone online"))
            GameTooltip:AddLine(T("Sends your character list, asks for theirs, looks up one friend's level with /who and catches up the activity log. Once a minute."), 1, 1, 1, true)
            GameTooltip:Show()
        end
    end)
    page.sync:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    return page
end

WoWStatusMainWindow.register("characters", "Characters", build, function()
    if not page then return end
    page.share:SetChecked(state().share)
    page.onlineOnly:SetChecked(R.onlineOnly())
    updateSyncButton()
    R.render()
end)
