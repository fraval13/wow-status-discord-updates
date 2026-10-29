local ADDON = ...
local A = WoWStatusAdapter
local H = WoWStatusHistory
local S = WoWStatusSafe
local waitingForIdentity, unsupportedWarned = false, false
local current, panel, discordPanel
local fields = {"level", "class", "race", "faction", "guild", "gear", "zone", "playtime", "professions", "deaths", "quests"}
local kinds = {"level", "death", "zone", "quest", "profession", "dungeon", "mount", "reputation", "unlock", "pvp"}
local playtime, playtimeRecordedAt, pendingPlayedLevel
local frame = CreateFrame("Frame")
local refresh

local function say(message)
    DEFAULT_CHAT_FRAME:AddMessage("|cff66ccffWoW Status:|r " .. message)
end

local function defaults()
    return {
        enabled = true, discord_enabled = false, discord_delivery = "summary", introduction_confirmed = false, character_role = "alt",
        fields = {level = true, class = true, race = true, faction = true, guild = true,
                  gear = true, zone = true, playtime = true, professions = true, deaths = true, quests = true},
        collection = {introduction = true, level = true, loot = true, equipment = false,
                      death = true, zone = true, quest = true, profession = true, lfg = false},
        announcements = {introduction = true, level = true, loot = true,
                         equipment = false, death = true, zone = true, quest = true, profession = true, lfg = false},
        loot_quality = 3, loot_rarities={rare=true,epic=true,legendary=true}, level_interval = 10,
    }
end

local function snapshot()
    if not current then return end
    current.exported_at = time()
    if current.settings.enabled then current.enrolled = true end
    current.player_name = WoWStatusDB.player_name or ""
    current.snapshot = current.settings.enabled and A.snapshot(current.settings.fields) or {}
    local tracking = current.history and current.history.tracking
    local last = tracking and tracking.points[#tracking.points]
    if tracking and tracking.active and last and current.snapshot.level == last.level then
        tracking.observed_until = current.exported_at
    end
    if current.settings.enabled then
        for key, value in pairs(WoWStatusProgress.observe(current, current.settings.fields)) do
            current.snapshot[key] = value
        end
    end
    if current.settings.enabled and current.settings.fields.playtime and playtime then
        current.snapshot.playtime = playtime
        current.snapshot.playtime_recorded_at = playtimeRecordedAt
    end
end

local function queue(kind, data, fixed)
    if not current or not current.settings.enabled or not current.settings.collection[kind] then
        return
    end
    if kind == "discovery" or kind == "lfg" then return end
    if kind == "dungeon" and data.source ~= "game_api" then return end
    if kind == "introduction" then return end
    if kind == "loot" and not WoWStatusLoot.allowed(current.settings,WoWStatusLoot.eventInfo(data)) then return end
    current.sequence = (current.sequence or 0) + 1
    local id = fixed or (current.identity.guid .. ":" .. current.epoch .. ":" .. current.sequence)
    for _, event in ipairs(current.events) do if event.id == id then return end end
    if #current.events >= 500 then
        table.remove(current.events, 1)
        if not current.warned then
            say("Recent buffer is full; older events remain in History.")
            current.warned = true
        end
    end
    data = H.copy(data or {})
    if current.settings.fields.zone then data.zone = A.zone() end
    local event = {id = id, kind = kind, at = time(), data = data,
        group_ids = H.copy(current.group_ids or {})}
    table.insert(current.events, event)
    H.record(current, event)
    WoWStatusJournal.recordLocal(event)
    snapshot()
    WoWStatusPopups.broadcast(current, event)
    return event
end

local function questMilestone()
    local milestone = WoWStatusProgress.questMilestone(current, current.snapshot.quests_completed, current.snapshot.quests_source)
    if milestone and current.settings.fields.quests then
        queue("quest", {completed=milestone, source=current.snapshot.quests_source})
    end
end

local function scrub()
    -- Remove data immediately when privacy choices change, before any disk export.
    local retained = {}
    for _, event in ipairs(current.events) do
        local allowed = current.settings.enabled and current.settings.collection[event.kind]
        if event.kind == "level" and not current.settings.fields.level then allowed = false end
        if event.kind == "zone" and not current.settings.fields.zone then allowed = false end
        if event.kind == "equipment" and not current.settings.fields.gear then allowed = false end
        if event.kind == "loot" and not WoWStatusLoot.allowed(current.settings,WoWStatusLoot.eventInfo(event.data)) then allowed=false end
        if event.kind == "introduction" and not current.settings.introduction_confirmed then
            allowed = false
        end
        if allowed then
            H.scrubEvent(current, event)
            table.insert(retained, event)
        end
    end
    current.events = retained
    H.scrub(current)
    local level = A.level()
    if level then H.sync(current, level, time()) end
    WoWStatusPopups.privacyChanged()
    WoWStatusJournal.privacyChanged()
    if not current.settings.enabled or not current.settings.fields.playtime then
        playtime, playtimeRecordedAt, pendingPlayedLevel = nil, nil, nil
        current.played_boundary = nil
    end
    if not current.settings.fields.professions then current.professions = nil end
    snapshot()
end

local function button(parent, text, x, y, width, fn)
    local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    b:SetPoint("TOPLEFT", x, y)
    b:SetSize(width, 26)
    b:SetText(text)
    b:SetScript("OnClick", fn)
    return b
end

local function label(parent, text, x, y, width)
    local t = parent:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
    t:SetPoint("TOPLEFT", x, y)
    t:SetWidth(width or 560)
    t:SetJustifyH("LEFT")
    t:SetText(text)
    return t
end

local openSettings, registerSettings

local function showPanel(host)
    if not current then say("Character is not ready."); return end
    if not panel then
        panel = CreateFrame("Frame", "WoWStatusSetup", UIParent)
        panel:SetSize(600, 1130)
        panel:SetPoint("CENTER");panel:SetFrameStrata("DIALOG");panel:EnableMouse(true)
        panel.background=panel:CreateTexture(nil,"BACKGROUND")
        panel.background:SetAllPoints();panel.background:SetColorTexture(.025,.035,.055,.96)
        label(panel,"WoW Status",24,-20)
        label(panel,"Set the same group ID as your friends to start sharing.",24,-64,550)
        panel.checks={}
        local function section(text,y)
            local title=label(panel,text,24,y,550);title:SetTextColor(1,.82,.25)
        end
        local function checkbox(key,title,x,y,group)
            local check=CreateFrame("CheckButton",nil,panel,"UICheckButtonTemplate")
            check:SetPoint("TOPLEFT",x,y);check:SetSize(32,32)
            label(check,title,38,-6,group=="loot_rarities" and 460 or 230)
            check:SetScript("OnClick",function(self)
                local target=group and current.settings[group] or current.settings
                target[key]=self:GetChecked() and true or false
                if key=="enabled" and target[key] then current.enrolled=true end
                if group=="in_game" and target[key] then current.settings.collection[key]=true end
                scrub();refresh()
            end)
            panel.checks[#panel.checks+1]={widget=check,key=key,group=group}
        end
        button(panel,"Groups",24,-116,160,function() openSettings(true) end)
        button(panel,"Activity log",204,-116,160,function() WoWStatusJournal.show() end)
        button(panel,"Preview toasts",384,-116,170,function() openSettings("previews") end)
        checkbox("enabled","Share my progress",24,-174)
        section("Announcements",-234)
        local titles={level="Level up",death="Deaths",zone="New location",quest="Every 100 quests",
            profession="Profession title",dungeon="First dungeon clear",mount="First mount",
            reputation="Reputation rank",unlock="Class ability unlock",pvp="PvP rank"}
        for i,key in ipairs(kinds) do
            checkbox(key,titles[key] or key,(i-1)%2==0 and 24 or 310,-270-math.floor((i-1)/2)*42,"in_game")
        end
        section("Loot",-508)
        checkbox("loot","Announce armor loot",24,-544,"in_game")
        checkbox("rare","Rare equipment",54,-586,"loot_rarities")
        checkbox("epic","Epic equipment",54,-628,"loot_rarities")
        checkbox("legendary","Legendary equipment",54,-670,"loot_rarities")
        section("Character details",-742)
        local names={level="Level and XP",class="Class",race="Race and male/female",faction="Faction",
            guild="Guild",gear="Equipment",zone="Location",playtime="Played time",professions="Professions",deaths="Total deaths",quests="Completed quests"}
        for i,key in ipairs(fields) do
            checkbox(key,names[key] or key,(i-1)%2==0 and 24 or 310,-780-math.floor((i-1)/2)*42,"fields")
        end
        button(panel,"History / graph",24,-1072,170,function() WoWStatusHistoryUI.show(function() return current end,"logs") end)
        panel.close=button(panel,"Close",424,-1072,130,function() panel:Hide() end)
    end
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusSetup" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusSetup") end
    panel.close:SetShown(not host)
    panel.background:SetShown(not host)
    panel:SetScale(1)
    panel:SetParent(host or UIParent)
    panel:ClearAllPoints()
    panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel:SetMovable(not host)
    if host then panel:SetScript("OnDragStart", nil)
    else panel:SetScript("OnDragStart", panel.StartMoving) end
    panel:SetFrameStrata(host and host:GetFrameStrata() or "DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel() + 1) end
    if not host and WoWStatusGroupWindow then WoWStatusGroupWindow:Hide() end
    refresh()
    panel:Show()
end

local function showDiscord(host)
    if not discordPanel then
        discordPanel = CreateFrame("Frame", "WoWStatusDiscordSettings", UIParent)
        discordPanel:SetSize(600, 930)
        discordPanel:EnableMouse(true)
        local bg = discordPanel:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.04, .04, .07, .98)
        label(discordPanel, "Optional Discord sharing", 24, -20, 550)
        label(discordPanel, "Off by default. In-game sharing works without this.\n"
            .. "If enabled, run the companion to upload after /reload or logout.\n"
            .. "Discord receives a status card only when your progress changes.", 24, -60, 550)
        discordPanel.checks = {}
        local function check(key, text, y, group)
            local widget = CreateFrame("CheckButton", nil, discordPanel, "UICheckButtonTemplate")
            widget:SetPoint("TOPLEFT", 24, y); widget:SetSize(32, 32)
            label(widget, text, 38, -6, 460)
            widget:SetScript("OnClick", function(self)
                local target = group and current.settings[group] or current.settings
                target[key] = self:GetChecked() and true or false
                if key == "discord_enabled" and target[key] then
                    current.discord_enrolled, current.discord_since = true, time()
                end
                current.settings.discord_delivery = "summary"
                snapshot()
            end)
            table.insert(discordPanel.checks, {widget=widget, key=key, group=group})
        end
        check("discord_enabled", "Also share this character to Discord", -150)
        label(discordPanel, "Include in Discord status updates", 24, -204, 550)
        for i, kind in ipairs(kinds) do check(kind, kind, -238 - (i - 1) * 38, "announcements") end
        label(discordPanel, "Repeat uploads do not repeat old activity. Already posted messages\n"
            .. "remain in Discord. Turn off, then export and upload to apply a pause\n"
            .. "remotely; companion group privacy controls can pause immediately.", 24, -820, 550)
    end
        discordPanel.close = discordPanel.close or button(discordPanel, "Close", 424, -880, 110,
            function() discordPanel:Hide() end)
    for i = #UISpecialFrames, 1, -1 do
        if UISpecialFrames[i] == "WoWStatusDiscordSettings" then table.remove(UISpecialFrames, i) end
    end
    if not host then table.insert(UISpecialFrames, "WoWStatusDiscordSettings") end
    discordPanel.close:SetShown(not host)
    if not host then
        if panel then panel:Hide() end
        if WoWStatusGroupWindow then WoWStatusGroupWindow:Hide() end
    end
    discordPanel:SetParent(host or UIParent); discordPanel:ClearAllPoints()
    discordPanel:SetPoint(host and "TOPLEFT" or "CENTER")
    if host then discordPanel:SetFrameStrata(host:GetFrameStrata()); discordPanel:SetFrameLevel(host:GetFrameLevel()+1) end
    for _, entry in ipairs(discordPanel.checks) do
        local target = entry.group and current.settings[entry.group] or current.settings
        entry.widget:SetChecked(target[entry.key])
    end
    discordPanel:Show()
end

-- Both pages live inside the game's AddOns settings, with scrollable content.
local settingsCategory, groupsCategory, discordCategory, previewsCategory, milestonesCategory
local function settingsPage(name, width, show)
    local page = CreateFrame("Frame")
    page:Hide()
    page.name = name
    local scroll = CreateFrame("ScrollFrame", nil, page, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 0, -8)
    scroll:SetPoint("BOTTOMRIGHT", -30, 8)
    local content
    local function resize()
        if content then
            -- Reflowed controls use native font and checkbox sizes. Never shrink them.
            content:SetScale(1)
            content:SetFrameStrata(scroll:GetFrameStrata())
            content:SetFrameLevel(scroll:GetFrameLevel() + 1)
            local available = scroll:GetWidth()
            content:SetWidth(math.max(width, available or width))
        end
    end
    local function display()
        show(scroll)
        local pages = {Groups=WoWStatusGroupWindow, Discord=WoWStatusDiscordSettings,
            ["Notification previews"]=WoWStatusNotificationPreviews, Milestones=WoWStatusMilestoneSettings}
        content = pages[name] or WoWStatusSetup
        scroll:SetScrollChild(content)
        resize()
    end
    page:SetScript("OnShow", display)
    page:SetScript("OnSizeChanged", resize)
    -- Canvas frames start shown in WoW. Build while explicitly hidden so the first
    -- sidebar selection works even when the Settings API skips an OnShow transition.
    display()
    page.OnRefresh = resize
    page.refresh = resize -- Legacy InterfaceOptions refresh callback.
    return page
end

registerSettings = function()
    if settingsCategory then return end
    if Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterCanvasLayoutSubcategory
        and Settings.RegisterAddOnCategory then
        local page = settingsPage("WoW Status", 600, showPanel)
        settingsCategory = Settings.RegisterCanvasLayoutCategory(page, "WoW Status")
        Settings.RegisterAddOnCategory(settingsCategory)
        local groups = settingsPage("Groups", 620, WoWStatusGroups.show)
        groupsCategory = Settings.RegisterCanvasLayoutSubcategory(settingsCategory, groups, "Groups")
        Settings.RegisterAddOnCategory(groupsCategory)
        -- Dormant integration: re-enable in Features.lua to restore this page.
        if WoWStatusFeatures.discord then
            local discord=settingsPage("Discord",600,showDiscord)
            discordCategory=Settings.RegisterCanvasLayoutSubcategory(settingsCategory,discord,"Discord (optional)")
            Settings.RegisterAddOnCategory(discordCategory)
        end
        local previews = settingsPage("Notification previews", 600, WoWStatusPreviews.show)
        previewsCategory = Settings.RegisterCanvasLayoutSubcategory(settingsCategory, previews, "Notification previews")
        Settings.RegisterAddOnCategory(previewsCategory)
    elseif InterfaceOptions_AddCategory then
        local page = settingsPage("WoW Status", 600, showPanel)
        InterfaceOptions_AddCategory(page)
        settingsCategory = page
        local groups = settingsPage("Groups", 620, WoWStatusGroups.show)
        groups.parent = page.name
        InterfaceOptions_AddCategory(groups)
        groupsCategory = groups
        if WoWStatusFeatures.discord then
            local discord=settingsPage("Discord",600,showDiscord)
            discord.parent=page.name;InterfaceOptions_AddCategory(discord);discordCategory=discord
        end
        local previews = settingsPage("Notification previews", 600, WoWStatusPreviews.show)
        previews.parent = page.name
        InterfaceOptions_AddCategory(previews)
        previewsCategory = previews
    end
end
openSettings = function(groups)
    if groups=="milestones" then groups=nil end
    if groups=="discord" and not WoWStatusFeatures.discord then groups=nil end
    registerSettings()
    local category = groups == "milestones" and milestonesCategory or groups == "previews" and previewsCategory or groups == "discord" and discordCategory or (groups and groupsCategory or settingsCategory)
    if category and category.GetID and Settings and Settings.OpenToCategory then
        Settings.OpenToCategory(category:GetID())
    elseif category and InterfaceOptionsFrame_OpenToCategory then
        InterfaceOptionsFrame_OpenToCategory(category)
    elseif groups == "previews" then WoWStatusPreviews.show()
    elseif groups == "discord" then showDiscord()
    elseif groups then WoWStatusGroups.show()
    else showPanel() end
end

refresh = function()
    if not panel then return end
    for _, entry in ipairs(panel.checks) do
        local target = entry.group and current.settings[entry.group] or current.settings
        entry.widget:SetChecked(target[entry.key])
    end
end

local function initialize()
    if not A.supported() then
        if not unsupportedWarned then
            say("This addon folder targets " .. A.display_name .. ". Collection is disabled on this client.")
            unsupportedWarned = true
        end
        return
    end
    WoWStatusDB = WoWStatusDB or {version = 1, characters = {}}
    if WoWStatusDB.version ~= 1 then say("Unsupported saved data version."); return end
    local identity = A.identity()
    if not identity then
        if not waitingForIdentity then
            say("Waiting for readable player identity. Collection will retry after loading/combat.")
            waitingForIdentity = true
        end
        return
    end
    waitingForIdentity = false
    local key = identity.client .. ":" .. identity.realm .. ":" .. identity.guid
    local first = not WoWStatusDB.characters[key]
    WoWStatusDB.characters[key] = WoWStatusDB.characters[key] or {
        identity = identity, settings = defaults(), snapshot = {}, events = {}, sequence = 0,
        epoch = tostring(time()) .. "-" .. tostring(math.random(100000, 999999)),
    }
    current = WoWStatusDB.characters[key]
    current.identity = identity
    WoWStatusLoot.defaults(current.settings)
    for _, character in pairs(WoWStatusDB.characters) do
        if not WoWStatusFeatures.discord then
            if character.discord_hidden_opt_in==nil then character.discord_hidden_opt_in=character.settings.discord_enabled==true end
            if character.discord_hidden_enrolled==nil then character.discord_hidden_enrolled=character.discord_enrolled==true end
            character.settings.discord_enabled=false;character.discord_enrolled=false
        elseif character.discord_hidden_opt_in~=nil then
            character.settings.discord_enabled=character.discord_hidden_opt_in
            character.discord_enrolled=character.discord_hidden_enrolled or false;character.discord_hidden_enrolled=nil
            if character.discord_hidden_opt_in then character.discord_since=time();character.discord_enrolled=true end
            character.discord_hidden_opt_in=nil
        end
    end
    if current.settings.discord_enabled == nil then
        current.discord_enrolled = current.enrolled == true
        current.settings.discord_enabled = false
    end
    current.settings.discord_delivery = "summary"
    current.settings.collection.equipment = false
    current.settings.announcements.equipment = false
    current.settings.in_game = current.settings.in_game or {}
    current.settings.in_game.equipment = false
    current.settings.in_game.introduction=false
    current.settings.collection.introduction=false
    current.settings.announcements.introduction=false
    for _, removed in ipairs({"discovery", "lfg"}) do
        current.settings.collection[removed]=false
        current.settings.announcements[removed]=false
        current.settings.in_game[removed]=false
    end
    for _, field in ipairs({"deaths", "quests"}) do
        if current.settings.fields[field] == nil then current.settings.fields[field] = true end
    end
    for _, kind in ipairs({"quest", "profession", "dungeon", "mount", "reputation", "unlock", "pvp"}) do
        if current.settings.collection[kind] == nil then current.settings.collection[kind] = true end
        if current.settings.announcements[kind] == nil then current.settings.announcements[kind] = true end
    end
    current.settings.in_game = current.settings.in_game or {}
    if current.settings.in_game.loot==nil then current.settings.in_game.loot=true end
    if current.settings.collection.loot==false then current.settings.in_game.loot=false end
    for _,kind in ipairs(kinds) do
        if current.settings.in_game[kind]==nil then current.settings.in_game[kind]=true end
        if current.settings.collection[kind]==false then current.settings.in_game[kind]=false end
    end
    WoWStatusGroups.init(WoWStatusDB, function() return current end, say)
    WoWStatusPopups.init(WoWStatusDB, function() return current end, say)
    H.init(current)
    WoWStatusJournal.prepare(WoWStatusDB)
    H.scrub(current)
    WoWStatusMinimap.init(WoWStatusDB)
    WoWStatusJournal.init(WoWStatusDB,current)
    local level = A.level()
    if level then H.sync(current, level, time()) end
    snapshot()
    current.last_zone = A.zone()
    local dead = S.call(UnitIsDeadOrGhost, "player")
    if dead ~= nil then current.death_latched = dead == true or dead == 1 end
    WoWStatusProgress.questMilestone(current, current.snapshot.quests_completed, current.snapshot.quests_source, true)
    if current.settings.fields.professions then WoWStatusProgress.professionChanges(current, true) end
    WoWStatusMilestones.init(current, queue, say)
    registerSettings()
    if current.settings.enabled then
        if current.settings.fields.playtime then A.requestPlaytime() end
    end
    if first then
        say("Set the same group ID as your friends in Options > AddOns > WoW Status.")
        openSettings()
    end
end

frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGIN")
frame:RegisterEvent("PLAYER_ENTERING_WORLD")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")
frame:RegisterEvent("PLAYER_LOGOUT")
frame:RegisterEvent("PLAYER_LEVEL_UP")
frame:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
frame:RegisterEvent("CHAT_MSG_LOOT")
frame:RegisterEvent("ZONE_CHANGED_NEW_AREA")
frame:RegisterEvent("PLAYER_DEAD")
frame:RegisterEvent("TIME_PLAYED_MSG")
frame:RegisterEvent("PLAYER_XP_UPDATE")
frame:RegisterEvent("QUEST_TURNED_IN")
frame:RegisterEvent("QUEST_LOG_UPDATE")
-- Some clients no longer expose this legacy query event. RegisterEvent throws
-- on unknown names, which would abort this file before OnEvent/slash setup.
if not C_EventUtils or not C_EventUtils.IsEventValid
    or S.call(C_EventUtils.IsEventValid, "QUEST_QUERY_COMPLETE") then
    pcall(frame.RegisterEvent, frame, "QUEST_QUERY_COMPLETE")
end
frame:RegisterEvent("SKILL_LINES_CHANGED")
frame:RegisterEvent("PLAYER_ALIVE")
frame:RegisterEvent("PLAYER_UNGHOST")
frame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then
        if current then registerSettings();WoWStatusMinimap.init(WoWStatusDB) end
        return
    end
    if event == "PLAYER_LOGIN" or event == "PLAYER_ENTERING_WORLD" or event == "PLAYER_REGEN_ENABLED" then
        if not current then initialize()
        elseif event == "PLAYER_REGEN_ENABLED" or event == "PLAYER_ENTERING_WORLD" then
            local level = A.level()
            if level then H.sync(current, level, time()) end
            snapshot()
        end
        return
    end
    if not current then return end
    if event == "PLAYER_LOGOUT" then
        scrub()
    elseif event == "PLAYER_LEVEL_UP" then
        local level = S.number(...)
        if level and level >= 1 and level <= A.max_level and current.settings.fields.level then
            local maxLevel = A.max_level
            local event = queue("level", {level = level, maximum = level == maxLevel})
            if event and current.settings.fields.playtime then
                pendingPlayedLevel = event
                A.requestPlaytime()
            end
        end
    elseif event == "CHAT_MSG_LOOT" then
        -- Match only localized self-loot formats, never another party member's loot.
        local message = S.string(...)
        if not message then return end
        local function matches(format)
            format = S.string(format)
            if not format then return false end
            local pattern = format:gsub("([%(%)%.%%%+%-%*%?%[%]%^%$])", "%%%1")
            pattern = pattern:gsub("%%%%s", ".+"):gsub("%%%%d", "%%d+")
            return message:match("^" .. pattern .. "$") ~= nil
        end
        if matches(LOOT_ITEM_SELF) or matches(LOOT_ITEM_SELF_MULTIPLE) then
            local link = message:match("(|Hitem:.-|h.-|h)")
            if link then WoWStatusLoot.capture(link,function(info)
                if WoWStatusLoot.allowed(current.settings,info) then queue("loot",info) end
            end) end
        end
    elseif event == "PLAYER_EQUIPMENT_CHANGED" then
        local slot=S.number(...)
        local item=slot and A.equipment(slot)
        WoWStatusJournal.equipment(slot,item)
        snapshot() -- Keep the profile current without an equipment notification.
    elseif event == "ZONE_CHANGED_NEW_AREA" then
        local zone = A.zone()
        if zone and current.last_zone and zone ~= current.last_zone and current.settings.fields.zone then
            queue("zone", {zone = zone})
        end
        if zone then current.last_zone = zone end
        snapshot()
    elseif event == "PLAYER_DEAD" then
        if current.settings.enabled and current.settings.collection.death and WoWStatusProgress.death(current) then
            queue("death", current.settings.fields.deaths and {total_deaths=current.progress.deaths} or {})
        end
    elseif event == "PLAYER_ALIVE" or event == "PLAYER_UNGHOST" then current.death_latched = false
    elseif event == "PLAYER_XP_UPDATE" then snapshot()
    elseif event == "QUEST_QUERY_COMPLETE" or event == "QUEST_LOG_UPDATE" then
        WoWStatusProgress.queryComplete(); snapshot(); questMilestone()
    elseif event == "QUEST_TURNED_IN" then
        local id = S.number(...)
        if current.settings.enabled and current.settings.fields.quests then
            WoWStatusProgress.quest(current,id)
            snapshot()
            questMilestone()
        end
    elseif event == "SKILL_LINES_CHANGED" then
        if current.settings.enabled and current.settings.fields.professions then
            for _, profession in ipairs(WoWStatusProgress.professionChanges(current)) do
                queue("profession", {name=profession.name, skill=profession.skill, max_skill=profession.max_skill, title=profession.title})
            end
            WoWStatusJournal.professions(current.progress.professions)
        end
        snapshot()
    elseif event == "TIME_PLAYED_MSG" then
        if current.settings.enabled and current.settings.fields.playtime then
            local total, thisLevel = ...
            total, thisLevel = S.number(total), S.number(thisLevel)
            local level = A.level()
            if total and total >= 0 then playtime, playtimeRecordedAt = total, time() end
            if total and thisLevel and level and thisLevel >= 0 and total >= thisLevel then
                local boundary = total - thisLevel
                local previous = current.played_boundary
                if pendingPlayedLevel and pendingPlayedLevel.data.level == level and previous
                    and previous.level == level - 1 and boundary >= previous.total then
                    local seconds = boundary - previous.total
                    -- Update both retained copies before the next SavedVariables export.
                    for _, events in ipairs({current.events, current.history.events}) do
                        for _, saved in ipairs(events) do
                            if saved.id == pendingPlayedLevel.id then saved.data.played_level_seconds = seconds end
                        end
                    end
                end
                current.played_boundary = {level = level, total = boundary}
                pendingPlayedLevel = nil
            end
        end
        snapshot()
    end
end)

SLASH_WOWSTATUS1 = "/wstatus"
SlashCmdList.WOWSTATUS = function(message)
    local command, rest = message:match("^(%S*)%s*(.-)$")
    if not current then say(A.display_name .. " character is not ready or identity is currently restricted."); return end
    if command == "groups" then
        if rest == "legacy" then
            current.group_ids = {}
            current.legacy_upload = true
            current.exported_at = time()
            WoWStatusPopups.groupsChanged()
            say("Legacy single-service upload selected. Only use with your own configured /link credentials.")
        else openSettings(true) end
    elseif command == "milestones" then openSettings("milestones")
    elseif command == "discover" or command == "dungeon" or command == "lfg" then
        say("Manual announcements have been removed. Milestones are detected automatically.")
    elseif command == "previews" then openSettings("previews")
    elseif command == "discord" and WoWStatusFeatures.discord then openSettings("discord")
    elseif command == "sync" then say("Activity syncs automatically when group members log in.")
    elseif command == "journal" or command == "friends" or command == "activity" then WoWStatusPopups.showActivity()
    elseif command == "popup" then
        WoWStatusPopups.command(rest)
    elseif command == "logs" or command == "graph" or command == "times" then
        local mode = command == "graph" and "graph" or (command == "times" and "timing" or "logs")
        WoWStatusHistoryUI.show(function() return current end, mode)
    elseif command == "pause" then
        current.settings.enabled = false
        current.settings.introduction_confirmed = false
        scrub()
        refresh()
        say("Sharing paused.")
    elseif command == "test" then
        queue("level", {level = 10, synthetic = true})
        say("Synthetic level 10 event requested; requires sharing, level field and level storage.")
    elseif command == "interval" or command == "quality" then
        local number = tonumber(rest)
        local upper = command == "interval" and 100 or 5
        local lower = command == "interval" and 1 or 0
        if number and number == math.floor(number) and number >= lower and number <= upper then
            current.settings[command == "interval" and "level_interval" or "loot_quality"] = number
            if command=="quality" then
                current.settings.loot_rarities={rare=number<=3,epic=number<=4,legendary=number<=5}
            end
            scrub()
            say("Filter updated.")
        else say("Invalid filter value.") end
    elseif command == "professions" then
        if not current.settings.enabled or not current.settings.fields.professions then
            say("Enable profession sharing first. Names are player-entered, not verified skill ranks.")
            return
        end
        local names = {}
        for rawName in rest:gmatch("[^,]+") do
            local name = rawName:match("^%s*(.-)%s*$")
            if #name > 0 and #name <= 50 and #names < 6 then
                table.insert(names, {name = name, source = "player_entered"})
            end
        end
        current.professions = names
        snapshot()
        say("Shared profession labels updated. /reload to export.")
    else openSettings() end
end

if C_Timer and C_Timer.NewTicker then C_Timer.NewTicker(30, snapshot) end
