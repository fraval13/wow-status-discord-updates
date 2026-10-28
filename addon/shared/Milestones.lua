-- Conservative milestones: unavailable APIs never become invented achievements.
WoWStatusMilestones = {}
local M, S = WoWStatusMilestones, WoWStatusSafe
local character, emit, report, panel
local unlocks = {
    DRUID={5487,768,783,1066,24858}, WARLOCK={688,697,712,691},
    SHAMAN={2645}, HUNTER={1515}, PRIEST={15473}, PALADIN={7328},
    WARRIOR={71,2458}, ROGUE={1804}, MAGE={3561,3562,3563,3565,3566,3567,10059,11416,11417,11418,11419,11420},
}
local function state()
    character.milestones = character.milestones or {}
    local value = character.milestones
    value.dungeons, value.reputation, value.unlocks = value.dungeons or {}, value.reputation or {}, value.unlocks or {}
    return value
end
local function clean(text, maximum)
    text = S.string(text)
    if not text or #text > maximum or text:find("[%c|]") then return nil end
    text = text:match("^%s*(.-)%s*$")
    return text ~= "" and text or nil
end
local function spellName(id)
    local name = S.stringCall(GetSpellInfo, id)
    if not name and C_Spell and C_Spell.GetSpellInfo then
        local info = S.value(S.call(C_Spell.GetSpellInfo, id))
        if type(info) == "table" then name = S.string(info.name) end
    end
    return name
end
function M.scanUnlocks(baseline)
    local _, class = S.call(UnitClass, "player")
    class = S.string(class)
    local known = IsSpellKnown or (C_SpellBook and C_SpellBook.IsSpellKnown)
    if not known then return end
    local value = state()
    for _, id in ipairs(unlocks[class] or {}) do
        if S.call(known, id) == true and not value.unlocks[tostring(id)] then
            local name = spellName(id)
            if name then
                value.unlocks[tostring(id)] = true
                if not baseline then emit("unlock", {text="Unlocked " .. name, spell_id=id}) end
            end
        end
    end
end
function M.scanReputation(baseline)
    local modern = C_Reputation and C_Reputation.GetFactionDataByIndex
    local count = S.number(S.call(C_Reputation and C_Reputation.GetNumFactions or GetNumFactions))
    if not count then return end
    local value = state()
    for index=1,math.min(count,512) do
        local name, standing, id
        if modern then
            local data = S.value(S.call(modern,index))
            if type(data)=="table" then
                name,standing,id = S.string(data.name),S.number(data.reaction),S.number(data.factionID)
            end
        elseif GetFactionInfo then
            local ok, rawName, _, rawStanding, _, _, _, _, _, header, _, _, _, _, rawID = pcall(GetFactionInfo,index)
            if ok and not S.value(header) then
                name,standing,id = S.string(rawName),S.number(rawStanding),S.number(rawID)
            end
        end
        if name and standing and standing>=1 and standing<=8 then
            local key = tostring(id or name)
            local previous = value.reputation[key]
            value.reputation[key] = math.max(previous or standing,standing)
            if not baseline and previous and standing>previous and standing>=6 then
                local titles = {[6]="Honored",[7]="Revered",[8]="Exalted"}
                emit("reputation", {text=titles[standing] .. " with " .. name, standing=standing})
            end
        end
    end
end
function M.scanPvp(baseline)
    local raw = S.number(S.call(UnitPVPRank,"player"))
    if not raw then return end
    local name, rank = S.call(GetPVPRankInfo,raw,"player")
    name, rank = S.string(name), S.number(rank)
    local value = state()
    if raw==0 or rank==0 then
        value.pvp_rank=value.pvp_rank or 0
        return
    end
    if not name or not rank or rank<0 or rank>100 then return end
    local previous = value.pvp_rank
    value.pvp_rank = math.max(previous or rank,rank)
    if not baseline and previous and rank>previous and rank>0 then
        emit("pvp", {text="Promoted to " .. name, rank=rank})
    end
end
function M.scanMount(baseline, event)
    local value = state()
    if value.mount_done then return end
    if C_MountJournal and C_MountJournal.GetMountIDs and C_MountJournal.GetMountInfoByID then
        local ids = S.value(S.call(C_MountJournal.GetMountIDs))
        if type(ids)=="table" then
            local count, name = 0,nil
            for _, raw in ipairs(ids) do
                local id = S.number(raw)
                if id then
                    local ok, rawName, _, _, _, _, _, _, _, _, _, collected = pcall(C_MountJournal.GetMountInfoByID,id)
                    if ok and S.value(collected)==true then count=count+1; name=S.string(rawName) or name end
                end
            end
            if count>0 then
                value.mount_done=true
                if not baseline and value.mount_count==0 and (event=="NEW_MOUNT_ADDED" or event=="COMPANION_LEARNED") then
                    emit("mount", {text="First mount: " .. (name or "collected!"), source="collection"})
                end
            end
            value.mount_count=count
            return
        end
    end
    -- Classic clients without a collection API can prove a ride, not acquisition.
    if S.call(IsMounted)==true then
        value.mount_done=true
        if not baseline then emit("mount", {text="First mount ride recorded!", source="observed_ride"}) end
    end
end
local function instance()
    if not GetInstanceInfo then return nil end
    local ok, name, kind, _, _, _, _, _, id = pcall(GetInstanceInfo)
    if ok and S.string(kind)=="party" then return S.string(name), S.number(id) end
end
function M.dungeon(name, source)
    name=clean(name,80)
    if not name then return false end
    local value=state()
    local key=name:lower()
    if value.dungeons[key] then return false end
    value.dungeons[key]=true
    emit("dungeon", {text="First clear: " .. name, source=source or "player_entered"})
    return true
end
function M.checkDungeon(event, ...)
    local name=instance()
    if not name then return end
    if event=="LFG_COMPLETION_REWARD" then M.dungeon(name,"game_api"); return end
    if event=="ENCOUNTER_END" then
        local _, _, _, _, success = ...
        if S.number(success)~=1 then return end
    end
    -- An arbitrary boss kill is not a dungeon clear. Require a complete roster.
    local _, count = S.call(GetInstanceLockTimeRemaining)
    count=S.number(count)
    if not count or count<1 or count>64 or not GetInstanceLockTimeRemainingEncounter then return end
    for index=1,count do
        local _, _, killed = S.call(GetInstanceLockTimeRemainingEncounter,index)
        if killed~=true then return end
    end
    M.dungeon(name,"game_api")
end
function M.discover(text)
    text=clean(text,120)
    if not text then return false end
    emit("discovery", {text=text, source="player_entered"})
    return true
end
function M.init(current, callback, reporter)
    character,emit,report=current,callback,reporter
    M.scanUnlocks(true); M.scanReputation(true); M.scanPvp(true); M.scanMount(true)
end
function M.event(event,...)
    if not character then return end
    local baseline=not character.settings.enabled
    if event=="UPDATE_FACTION" then M.scanReputation(baseline)
    elseif event=="PLAYER_PVP_RANK_CHANGED" or event=="HONOR_XP_UPDATE" then M.scanPvp(baseline)
    elseif event=="SPELLS_CHANGED" or event=="LEARNED_SPELL_IN_TAB" then M.scanUnlocks(baseline)
    elseif event=="NEW_MOUNT_ADDED" or event=="COMPANION_LEARNED" or event=="PLAYER_MOUNT_DISPLAY_CHANGED" then M.scanMount(baseline,event)
    elseif not baseline and (event=="LFG_COMPLETION_REWARD" or event=="ENCOUNTER_END" or event=="BOSS_KILL") then M.checkDungeon(event,...) end
end
local frame=CreateFrame("Frame")
for _, event in ipairs({"UPDATE_FACTION","PLAYER_PVP_RANK_CHANGED","HONOR_XP_UPDATE","SPELLS_CHANGED","LEARNED_SPELL_IN_TAB",
    "NEW_MOUNT_ADDED","COMPANION_LEARNED","PLAYER_MOUNT_DISPLAY_CHANGED","LFG_COMPLETION_REWARD","ENCOUNTER_END","BOSS_KILL"}) do
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid,event) then
        pcall(frame.RegisterEvent,frame,event)
    end
end
frame:SetScript("OnEvent",function(_,event,...) M.event(event,...) end)

local function label(parent,text,x,y,width)
    local widget=parent:CreateFontString(nil,"OVERLAY","GameFontHighlightLarge")
    widget:SetPoint("TOPLEFT",x,y);widget:SetWidth(width or 550);widget:SetJustifyH("LEFT");widget:SetText(text)
    return widget
end
local function button(parent,text,x,y,width,callback)
    local widget=CreateFrame("Button",nil,parent,"UIPanelButtonTemplate")
    widget:SetPoint("TOPLEFT",x,y);widget:SetSize(width,30);widget:SetText(text);widget:SetScript("OnClick",callback)
    return widget
end
function M.show(host)
    if not panel then
        panel=CreateFrame("Frame","WoWStatusMilestoneSettings",UIParent)
        panel:SetSize(600,750)
        local bg=panel:CreateTexture(nil,"BACKGROUND");bg:SetAllPoints();bg:SetColorTexture(.025,.035,.065,.98)
        label(panel,"Milestones and discoveries",24,-20)
        label(panel,"First dungeon clears, first mount, reputation promotions,\nmajor class unlocks and PvP promotions join the notification queue.\nExisting progress is baselined silently on login.\nAutomatic detection depends on your client's available APIs.",24,-64)
        label(panel,"Share a discovery (details hidden on the toast)",24,-180)
        panel.discovery=CreateFrame("EditBox",nil,panel,"InputBoxTemplate")
        panel.discovery:SetPoint("TOPLEFT",30,-218);panel.discovery:SetSize(530,32)
        panel.discovery:SetAutoFocus(false);panel.discovery:SetMaxLetters(120)
        button(panel,"Share discovery",24,-264,200,function()
            if not character.settings.enabled or not character.settings.collection.discovery then report("Enable discovery sharing first.");return end
            if M.discover(panel.discovery:GetText()) then panel.discovery:SetText("");report("Discovery queued. Friends can read details in Group activity.")
            else report("Enter discovery text without chat links or control characters (up to 120 bytes).") end
        end)
        label(panel,"Record a first dungeon clear",24,-328)
        label(panel,"Use this after a clear when the client has no completion API.\nEnter the dungeon name; each dungeon is recorded once.\nYour completion report is shared with your groups.",24,-364)
        panel.dungeon=CreateFrame("EditBox",nil,panel,"InputBoxTemplate")
        panel.dungeon:SetPoint("TOPLEFT",30,-444);panel.dungeon:SetSize(530,32)
        panel.dungeon:SetAutoFocus(false);panel.dungeon:SetMaxLetters(80)
        button(panel,"Record first clear",24,-490,200,function()
            if not character.settings.enabled or not character.settings.collection.dungeon then report("Enable dungeon sharing first.");return end
            if M.dungeon(panel.dungeon:GetText(),"player_entered") then report("First clear queued.")
            else report("Enter a new dungeon name; already recorded clears are not repeated.") end
        end)
        label(panel,"Loot rarity filter (also available with /wstatus quality)",24,-554)
        button(panel,"Rare + epic loot",24,-594,210,function() character.settings.loot_quality=3;report("Rare and epic loot notifications enabled.") end)
        button(panel,"Epic loot only",260,-594,210,function() character.settings.loot_quality=4;report("Epic loot notifications enabled.") end)
        label(panel,"Preview every notification in Notification previews.\nDiscoveries are voluntary; avoid sharing story spoilers unprompted.",24,-650)
        panel.close=button(panel,"Close",424,-704,140,function() panel:Hide() end)
    end
    panel:SetParent(host or UIParent);panel:ClearAllPoints();panel:SetPoint(host and "TOPLEFT" or "CENTER")
    panel.close:SetShown(not host)
    panel:SetFrameStrata(host and host:GetFrameStrata() or "FULLSCREEN_DIALOG")
    if host then panel:SetFrameLevel(host:GetFrameLevel()+1) end
    if panel.dungeon:GetText()=="" then
        local name=instance()
        if name then panel.dungeon:SetText(name) end
    end
    panel:Show()
end
