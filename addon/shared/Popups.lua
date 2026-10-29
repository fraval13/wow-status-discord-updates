-- In-game group updates. Custom channels discover peers; addon whispers carry data.
WoWStatusPopups = {}
local P = WoWStatusPopups
local A, S = WoWStatusAdapter, WoWStatusSafe
local prefs, getCharacter, notify, toast, active
local incoming, outgoing = {}, {}
local lastDisplay, lastAttempt = 0, 0
local joinedByAddon, syncPending = {}, false
local frame = CreateFrame("Frame")
local PREFIX = "WSTATUS1"
local ADDON_PREFIX = "WoWStatus"
local rosterRequested = {}

local function realm()
    local value = A.realmName()
    return value and value:gsub("%s", "") or ""
end
function P.senderKey(sender)
    sender = S.string(sender)
    if type(sender) ~= "string" or #sender == 0 or #sender > 120 or sender:find("[%c|]") then return nil end
    if not sender:find("-", 1, true) then sender = sender .. "-" .. realm() end
    return sender:gsub("%s", ""):lower()
end
local function combat()
    return InCombatLockdown and InCombatLockdown()
end
local function groupMode(character)
    character = character or (getCharacter and getCharacter())
    return character and next(WoWStatusGroups.selected(character)) ~= nil
end
local function receiving()
    return prefs and (groupMode() or prefs.receive)
end
local function canShare(character, event)
    if not (prefs and character and character.settings.enabled
        and (groupMode(character) or prefs.broadcast)) then return false end
    if not event then return true end
    if event.kind == "introduction" or event.kind == "discovery" or event.kind == "lfg" then return false end
    if event.kind == "dungeon" and event.data.source ~= "game_api" then return false end
    if not character.settings.collection[event.kind] then return false end
    if character.settings.in_game and character.settings.in_game[event.kind] == false then return false end
    if event.kind == "level" and not character.settings.fields.level then return false end
    if event.kind == "zone" and not character.settings.fields.zone then return false end
    if event.kind == "equipment" then return false end
    if event.kind == "loot" and not WoWStatusLoot.allowed(character.settings,WoWStatusLoot.eventInfo(event.data)) then return false end
    if event.kind == "quest" and not character.settings.fields.quests then return false end
    if event.kind == "profession" and not character.settings.fields.professions then return false end
    return true
end
local function channels()
    local result = {}
    if not prefs then return result end
    local character = getCharacter()
    local groups = WoWStatusGroups.selected(character)
    for id in pairs(groups) do
        if WoWStatusGroups.valid(id) then result[WoWStatusGroups.channel(id):lower()] = id end
    end
    if not next(result) and prefs.legacy_channel then result[prefs.channel:lower()] = "legacy" end
    return result
end
local function joined(group)
    if not prefs or not GetChannelName then return nil end
    local name = group and WoWStatusGroups.channel(group) or prefs.channel
    if not channels()[name:lower()] then return nil end
    local id, actual = S.call(GetChannelName, name)
    if type(id) ~= "number" or id < 1 or type(actual) ~= "string" or actual:lower() ~= name:lower() then return nil end
    return id
end
-- channelIndex here is the display index, not the numbered /chat shortcut.
function P.peers(group)
    local peers, seen = {}, {}
    if not GetNumDisplayChannels or not GetChannelDisplayInfo then return peers end
    local count = S.number(S.call(GetNumDisplayChannels))
    local getter = C_ChatInfo and C_ChatInfo.GetChannelRosterInfo or GetChannelRosterInfo
    if not count or not getter then return peers end
    local expected = WoWStatusGroups.channel(group):lower()
    for index = 1, math.min(count, 128) do
        local ok, name, header, _, _, members = pcall(GetChannelDisplayInfo, index)
        name, members = S.string(name), S.number(members)
        if ok and name and name:lower() == expected and S.value(header) == false then
            if SetSelectedDisplayChannel and (not rosterRequested[group] or time() - rosterRequested[group] >= 30) then
                rosterRequested[group] = time()
                local previous = S.number(S.call(GetSelectedDisplayChannel))
                pcall(SetSelectedDisplayChannel, index)
                if previous and previous ~= index then pcall(SetSelectedDisplayChannel, previous) end
            end
            for member = 1, math.min(members or 0, 64) do
                local target = S.string(S.call(getter, index, member))
                local key = target and P.senderKey(target)
                local own = P.senderKey((A.playerName() or "") .. "-" .. realm())
                if key and key ~= own and not seen[key] then
                    seen[key] = true; table.insert(peers, target)
                end
            end
            break
        end
    end
    return peers
end
local function remember(item)
    if item.preview then return end
    if WoWStatusJournal then WoWStatusJournal.received(item) end
    prefs.activity = prefs.activity or {}
    table.insert(prefs.activity, 1, {sender = item.sender, level = item.level,
        kind = item.kind or "level", text = item.text, automatic = item.automatic, nonce = item.nonce, original_at = item.at, quality=item.quality, class_id=item.class_id, equip_loc=item.equip_loc, item_id=item.item_id, at = time(), group_id = item.group_id})
    while #prefs.activity > 200 do table.remove(prefs.activity) end
end
function P.groupsChanged()
    if not prefs then return end
    prefs.legacy_channel = false
    local allowed = channels()
    for name in pairs(joinedByAddon) do
        if not allowed[name] then
            if LeaveChannelByName then pcall(LeaveChannelByName, name) end
            joinedByAddon[name] = nil
        end
    end
    local kept = {}
    for _, item in ipairs(incoming) do
        if item.preview or (item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id)) then
            table.insert(kept, item)
        end
    end
    incoming = kept
    if active and not active.preview and not WoWStatusGroups.contains(getCharacter(), active.group_id) then
        active = nil
        if toast then toast:Hide() end
    end
    kept = {}
    for _, item in ipairs(outgoing) do
        if item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id) then table.insert(kept, item) end
    end
    outgoing, syncPending = kept, true
    local history = {}
    for _, item in ipairs(prefs.activity or {}) do
        if item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id) then table.insert(history, item) end
    end
    prefs.activity = history
    if WoWStatusJournal then WoWStatusJournal.groupsChanged() end
end
local function syncGroups()
    if not syncPending or combat() then return end
    syncPending = false
    for id in pairs(WoWStatusGroups.selected(getCharacter())) do
        if WoWStatusGroups.valid(id) and not joined(id) and JoinTemporaryChannel then
            local name = WoWStatusGroups.channel(id)
            local ok = pcall(JoinTemporaryChannel, name)
            if ok then joinedByAddon[name:lower()] = true end
        end
    end
end
local function status(state, event)
    prefs.last_send = {state = state, at = time(), event_id = event and event.id or nil}
end
local function clear()
    incoming, outgoing, active = {}, {}, nil
    if toast then toast:Hide() end
end
local function pruneSeen(now)
    local count, oldest, oldestAt = 0, nil, math.huge
    for key, at in pairs(prefs.seen) do
        if type(at) ~= "number" or now - at > 600 or at > now + 300 then prefs.seen[key] = nil
        else
            count = count + 1
            if at < oldestAt then oldest, oldestAt = key, at end
        end
    end
    if count >= 256 and oldest then prefs.seen[oldest] = nil end

end

function P.init(database, getter, reporter)
    database.popups = database.popups or {
        receive = true, broadcast = true, sound = false, channel = "WStatusFriends",
        trusted = {}, seen = {},
    }
    prefs, getCharacter, notify = database.popups, getter, reporter
    prefs.trusted, prefs.seen = prefs.trusted or {}, prefs.seen or {}
    prefs.level_claims = prefs.level_claims or {}
    prefs.channel = prefs.channel or "WStatusFriends"
    local activity={}
    for _, item in ipairs(prefs.activity or {}) do
        if item.kind~="discovery" and item.kind~="lfg" and item.kind~="introduction" and (item.kind~="dungeon" or item.automatic)
            and (item.kind~="loot" or WoWStatusLoot.allowed(getter().settings,item)) then
            table.insert(activity,item)
        end
    end
    prefs.activity = activity
    if not database.in_game_primary then
        prefs.receive, prefs.broadcast = true, true
        database.in_game_primary = true
    end
    local register = C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix or RegisterAddonMessagePrefix
    if register then pcall(register, ADDON_PREFIX) end
    clear()
    pruneSeen(time())
    syncPending = true
    syncGroups()
end

function P.receive(text, sender, channel)
    text, sender, channel = S.string(text), S.string(sender), S.string(channel)
    if not receiving() or type(text) ~= "string" or #text > 220
        or type(channel) ~= "string" then return false end
    local group = channels()[channel:lower()]
    if not group then return false end
    local key = P.senderKey(sender)
    local selfKey = P.senderKey((A.playerName() or "") .. "-" .. realm())
    if not key or key == selfKey or (group == "legacy" and not prefs.trusted[key]) then return false end
    local client, kind, atText, nonce, encoded = text:match("^WSTATUS3 ([%w%-]+) (%a+) (%d+) ([%w%-]+) ([a-f0-9]+)$")
    local raw, automatic, armor = false, false, false
    if not client then
        client,kind,atText,nonce,encoded = text:match("^WSTATUS4 ([%w%-]+) (%a+) (%d+) ([%w%-]+) (.+)$")
        raw = client ~= nil
    end
    if not client then
        client,kind,atText,nonce,encoded = text:match("^WSTATUS5 ([%w%-]+) (%a+) (%d+) ([%w%-]+) (.+)$")
        raw,automatic = client~=nil,client~=nil
    end
    if not client then
        client,kind,atText,nonce,encoded=text:match("^WSTATUS6 ([%w%-]+) (%a+) (%d+) ([%w%-]+) (.+)$")
        raw,armor=client~=nil,client~=nil
    end
    if client then
        local allowed = {loot=true, death=true, zone=true, quest=true, profession=true, dungeon=true, mount=true, reputation=true, unlock=true, pvp=true}
        local at, now = tonumber(atText), time()
        if client ~= A.client_id or not allowed[kind] or #nonce > 64 or #encoded > (raw and 120 or 96)
            or (not raw and #encoded % 2 ~= 0) or at < now - 120 or at > now + 300 then return false end
        local detail = raw and encoded or encoded:gsub("..", function(pair) return string.char(tonumber(pair, 16)) end)
        if detail:find("[%c|]") then return false end
        local lootInfo
        if armor and kind~="loot" then return false end
        if kind=="loot" then
            if not armor then return false end
            local quality,class,slot,id,name=detail:match("^(%d) (%d+) ([A-Z_]+) (%d+) (.+)$")
            lootInfo={quality=tonumber(quality),class_id=tonumber(class),equip_loc=slot,item_id=tonumber(id)}
            if not lootInfo.item_id or not name or not WoWStatusLoot.allowed(getCharacter().settings,lootInfo) then return false end
            detail="Looted "..name
        end
        if automatic and kind~="dungeon" then return false end
        if kind=="dungeon" then
            if not automatic then return false end -- Old manual reports used WSTATUS4.
            local id,name=detail:match("^(%d+) (.+)$")
            id=tonumber(id)
            if not id or id<1 or id>1000000000 or #name>80 then return false end
            detail="First clear: " .. name
        end
        -- Ignore older addon versions' per-quest and per-skill spam.
        if kind == "quest" and not detail:match("^Completed %d+ quests!$") then return false end
        if kind == "profession" and detail:match(": %d+ / %d+") then return false end
        pruneSeen(now)
        local duplicate = key .. ":" .. nonce
        if WoWStatusJournal and WoWStatusJournal.contains(WoWStatusJournal.eventID(sender,nonce)) then
            local duplicateItem={sender=sender,kind=kind,text=detail,at=at,nonce=nonce,group_id=group~="legacy" and group or nil}
            if lootInfo then for k,v in pairs(lootInfo) do duplicateItem[k]=v end end
            WoWStatusJournal.received(duplicateItem)
            prefs.seen[duplicate]=now;return false
        end
        if prefs.seen[duplicate] or #incoming >= 128 then return false end
        prefs.seen[duplicate] = now
        local item = {sender=sender, key=key, kind=kind, text=detail, automatic=automatic, received_at=now, at=at, nonce=nonce,
            group_id=group ~= "legacy" and group or nil}
        if lootInfo then for k,v in pairs(lootInfo) do item[k]=v end end
        remember(item)
        table.insert(incoming, item)
        P.tick()
        return true
    end
    local client, levelText, atText, nonce = text:match("^WSTATUS2 ([%w%-]+) LEVEL (%d+) (%d+) ([%w%-]+)$")
    if not client and A.client_id == "classic-era" then
        levelText, atText, nonce = text:match("^" .. PREFIX .. " LEVEL (%d+) (%d+) ([%w%-]+)$")
        if levelText then client = "classic-era" end
    end
    if client ~= A.client_id then return false end
    local level, at, now = tonumber(levelText), tonumber(atText), time()
    if not level or level < 2 or level > A.max_level or not at or not nonce or #nonce > 64
        or at < now - 120 or at > now + 300 then return false end
    pruneSeen(now)
    local duplicateKey = key .. ":" .. level
    local claims = prefs.level_claims[key]
    if WoWStatusJournal and WoWStatusJournal.contains(WoWStatusJournal.eventID(sender,nonce)) then
        WoWStatusJournal.received({sender=sender,kind="level",level=level,at=at,nonce=nonce,
            group_id=group~="legacy" and group or nil})
        prefs.seen[duplicateKey]=now;return false
    end
    if prefs.seen[duplicateKey] or (claims and claims.levels[level]) then return false end
    if #incoming >= 128 then return false end
    if not claims then
        local count, oldest, oldestAt = 0, nil, math.huge
        for senderKey, value in pairs(prefs.level_claims) do
            count = count + 1
            if value.at < oldestAt then oldest, oldestAt = senderKey, value.at end
        end
        if count >= 512 and oldest then prefs.level_claims[oldest] = nil end
        claims = {levels = {}, at = now}
        prefs.level_claims[key] = claims
    end
    claims.levels[level], claims.at = true, now
    prefs.seen[duplicateKey] = now
    table.insert(incoming, {sender = sender, key = key, level = level, received_at = now,
        count = 1, group_id = group ~= "legacy" and group or nil})
    remember({sender=sender, level=level, at=at, nonce=nonce, group_id=group ~= "legacy" and group or nil})
    P.tick()
    return true
end

local function show(item, now)
    if not toast then
        toast = CreateFrame("Frame", "WoWStatusLevelPopup", UIParent)
        toast:SetSize(560, 108)
        toast:SetPoint("TOP", 0, -170)
        toast:SetFrameStrata("DIALOG")
        toast:EnableMouse(true)
        toast:SetScript("OnMouseUp",function(self,button)
            if button=="LeftButton" or button=="RightButton" then
                self:Hide();active=nil
                lastDisplay=time()-7 -- Advance on the next tick, without dropping queued entries.
            end
        end)
        local bg = toast:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.025, .035, .065, .96)
        toast.accent = toast:CreateTexture(nil, "OVERLAY")
        toast.accent:SetPoint("TOPLEFT"); toast.accent:SetSize(560, 3)
        toast.icon = toast:CreateTexture(nil, "ARTWORK")
        toast.icon:SetPoint("TOPLEFT", 18, -22); toast.icon:SetSize(64, 64)
        toast.glow = toast:CreateTexture(nil, "OVERLAY")
        toast.glow:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
        toast.glow:SetPoint("CENTER", toast.icon, "CENTER"); toast.glow:SetSize(112, 112)
        toast.glow:SetBlendMode("ADD")
        toast.heading = toast:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
        toast.heading:SetPoint("TOPLEFT", 104, -14); toast.heading:SetWidth(438)
        toast.heading:SetJustifyH("LEFT")
        toast.message = toast:CreateFontString(nil, "OVERLAY", "GameFontHighlightLarge")
        toast.message:SetPoint("TOPLEFT", 104, -38); toast.message:SetWidth(438)
        toast.message:SetJustifyH("LEFT")
        toast.detail = toast:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        toast.detail:SetPoint("BOTTOMLEFT", 104, 12); toast.detail:SetWidth(438)
        toast.detail:SetJustifyH("LEFT")
        toast:SetScript("OnUpdate", function(self, elapsed)
            self.age = (self.age or 0) + elapsed
            local entrance = math.min(1, self.age / .22)
            local fade = math.max(0, math.min(1, (6 - self.age) / .5))
            self:SetAlpha(entrance * fade)
            self:ClearAllPoints(); self:SetPoint("TOP", 0, -170 - (1 - entrance) * 12)
            self.glow:SetAlpha(.5 + .3 * math.sin(self.age * 7))
            if self.age >= 6 then self:Hide(); active = nil end
        end)
    end
    local alias = not item.preview and prefs.trusted[item.key]
    local name = item.sender:match("^[^-]+") or item.sender
    if type(alias) == "string" and alias ~= "" then name = alias .. "’s " .. name end
    name = name:gsub("|", "||")
    local texture, r, g, b, heading = WoWStatusPresentation.theme(item)
    toast.icon:SetTexture(texture)
    toast.glow:SetVertexColor(r,g,b)
    toast.accent:SetColorTexture(r,g,b,1)
    toast.heading:SetTextColor(r,g,b); toast.heading:SetText(heading)
    local detail = item.level and ("reached level " .. item.level .. "!"
        .. ((item.count or 1) > 1 and (" (" .. item.count .. " recorded level-ups)") or ""))
        or ((item.text or "Shared an update"):gsub("|", "||"))
    toast.message:SetText(name .. (item.level and " " or " — ") .. detail)
    toast.detail:SetText(item.preview and "Local preview · Click to dismiss" or "Click to dismiss")
    toast.age = 0
    toast:SetAlpha(0)
    toast:Show()
    item.hide_at = now + 6
    active, lastDisplay = item, now
    if prefs.sound and PlaySound and SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPEN then
        PlaySound(SOUNDKIT.IG_MAINMENU_OPEN)
    end
end

function P.preview(kind)
    if not prefs then return end
    local samples = {
        introduction="Joined the group tracker", loot="Looted Robe of the Archmage",
        death="Died — total tracked deaths: 15",
        zone="Entered Stranglethorn Vale", quest="Completed 100 quests!",
        profession="Tailoring: Expert (225 max)",
        dungeon="First clear: The Deadmines", mount="First mount: Brown Horse",
        reputation="Exalted with Ironforge", unlock="Unlocked Bear Form", pvp="Promoted to Sergeant",
    }
    if kind ~= "level" and not samples[kind] then return end
    if #incoming >= 128 then notify("Notification queue is full; wait for previews to finish."); return end
    table.insert(incoming, {sender="Previewlock",key="local-preview",kind=kind,text=samples[kind],
        level=kind=="level" and 33 or nil,quality=kind=="loot" and 4 or nil,received_at=time(),preview=true})
    P.tick()
end

local function tick()
    if not prefs then return end
    local now = time()
    syncGroups()
    if not receiving() then
        local previews = {}
        for _, item in ipairs(incoming) do if item.preview then table.insert(previews,item) end end
        incoming = previews
        if active and not active.preview then
            active = nil
            if toast then toast:Hide() end
        end
    end
    if active and not active.preview and not (active.group_id
        and WoWStatusGroups.contains(getCharacter(), active.group_id)) and not prefs.trusted[active.key] then
        active = nil
        if toast then toast:Hide() end
    end
    if combat() then
        if active then
            table.insert(incoming, 1, active)
            active = nil
            if toast then toast:Hide() end
        end
        return
    end
    if active and now >= active.hide_at then active = nil; if toast then toast:Hide() end end
    if (receiving() or (#incoming > 0 and incoming[1].preview)) and not active and #incoming > 0 and now - lastDisplay >= 7 then
        local item = table.remove(incoming, 1)
        if (item.preview or (item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id))
            or prefs.trusted[item.key]) then show(item, now) end
    end
    if #outgoing == 0 or now - lastAttempt < 1 then return end
    local item, character = outgoing[1], getCharacter()
    if not canShare(character, item.event) or now - item.at > 120
        or (item.group_id and not WoWStatusGroups.contains(character, item.group_id)) then
        table.remove(outgoing, 1)
        status("cancelled_or_expired", item.event)
        return
    end
    if not joined(item.group_id) then status("not_joined", item.event); return end
    if A.chatRestricted() then status("chat_restricted", item.event); return end
    local send, args
    if item.group_id then
        send = C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
        if not send then status("unsupported_addon_whispers", item.event); return end
        if not item.targets then
            local targets = P.peers(item.group_id)
            if #targets == 0 then status("waiting_for_group_peers", item.event); return end
            item.targets, item.target = targets, 1
        end
        args = {ADDON_PREFIX, item.group_id .. " " .. item.message, "WHISPER", item.targets[item.target]}
    else
        send = A.chatSender()
        if not send then status("unsupported_api", item.event); return end
        args = {item.message, "CHANNEL", nil, tostring(joined(item.group_id))}
    end
    lastAttempt = now
    local unpackArgs = unpack or table.unpack
    local ok, result = pcall(send, unpackArgs(args, 1, 4))
    result = S.value(result)
    if item.targets and item.target < #item.targets then item.target = item.target + 1
    else table.remove(outgoing, 1) end
    local accepted = ok and result ~= false
    if type(result) == "number" then
        accepted = ok and Enum and Enum.SendAddonMessageResult and result == Enum.SendAddonMessageResult.Success
    end
    status(accepted and "attempted_no_receipt" or "blocked_or_uncertain", item.event)
    if not accepted then notify("In-game update blocked/uncertain; see /wstatus popup status.") end
end

local ticking = false
function P.tick()
    if ticking then return end
    ticking = true
    local ok, problem = pcall(tick)
    ticking = false
    if not ok then error(problem) end
end

local function eventText(event)
    local data = event.data or {}
    if event.kind == "dungeon" or event.kind == "mount" or event.kind == "reputation"
        or event.kind == "unlock" or event.kind == "pvp" then return data.text end
    if event.kind == "introduction" then return "Joined the tracker" end
    if event.kind == "quest" then
        return data.completed and ("Completed " .. data.completed .. " quests!") or nil
    end
    if event.kind == "profession" then return (data.name or "Profession") .. ": " .. (data.title or WoWStatusProgress.professionTitle(data.max_skill)) .. " (" .. (data.max_skill or "?") .. " max)" end
    if event.kind == "death" then return data.total_deaths and ("Total deaths: " .. data.total_deaths) or "Died" end
    if event.kind == "session" then return data.state == "addon_loaded" and "Started a session" or "Ended a session" end
    if event.kind == "zone" then return "Entered " .. (data.zone or "a new zone") end
    if event.kind == "loot" or event.kind == "equipment" then
        local item = data.item and data.item:match("%[([^%]]+)%]") or "an item"
        return (event.kind == "loot" and "Looted " or "Equipped ") .. item
    end
end
P.canShare = canShare
P.eventText = eventText
function P.broadcast(character, event)
    if not event or event.kind == "session" or event.kind == "equipment" or not canShare(character, event) or event.data.synthetic or #outgoing >= 32 then return end
    local nonce = character.epoch .. "-" .. character.sequence
    local text
    if event.kind=="loot" then
        local info=WoWStatusLoot.eventInfo(event.data)
        if not WoWStatusLoot.allowed(character.settings,info) then return end
        local name=info.name or (info.item or ""):match("%[([^%]]+)%]") or "Armor"
        name=name:gsub("[%c|]"," ")
        if #name>72 then name=name:sub(1,69):gsub("[\194-\244][\128-\191]*$","").."..." end
        text="WSTATUS6 "..A.client_id.." loot "..event.at.." "..nonce.." "..info.quality.." "..info.class_id.." "..info.equip_loc.." "..info.item_id.." "..name
    elseif event.kind == "dungeon" then
        local id,name=event.data.instance_id,event.data.name
        if type(id)~="number" or id<1 or id>1000000000 or type(name)~="string" or #name>80 or name:find("[%c|]") then return end
        text="WSTATUS5 " .. A.client_id .. " dungeon " .. event.at .. " " .. nonce .. " " .. id .. " " .. name
    elseif event.kind == "level" then
        if event.data.level < 2 or event.data.level > A.max_level then return end
        text = "WSTATUS2 " .. A.client_id .. " LEVEL " .. event.data.level .. " " .. event.at .. " " .. nonce
    else
        if event.kind == "loot" and (event.data.quality or 0) < character.settings.loot_quality then return end
        local detail = eventText(event)
        if not detail then return end
        detail = detail:gsub("[%c]", " ")
        local modern = event.kind == "dungeon" or event.kind == "mount" or event.kind == "reputation"
            or event.kind == "unlock" or event.kind == "pvp"
        local limit = modern and 120 or 48
        if #detail > limit then
            detail = detail:sub(1, limit-3):gsub("[\194-\244][\128-\191]*$", "") .. "..."
        end
        local encoded = modern and detail or detail:gsub(".", function(char) return string.format("%02x", char:byte()) end)
        text = (modern and "WSTATUS4 " or "WSTATUS3 ") .. A.client_id .. " " .. event.kind .. " " .. event.at .. " " .. nonce .. " " .. encoded
    end
    if #text > 220 then return end
    local groups = WoWStatusGroups.selected(character)
    for id in pairs(groups) do
        if #outgoing < 32 and event.group_ids and event.group_ids[id] then
            table.insert(outgoing, {message = text, at = event.at, event = event, group_id = id})
        end
    end
    if not next(groups) and prefs.legacy_channel then
        table.insert(outgoing, {message = text, at = event.at, event = event})
    end
    status(#outgoing > 0 and "queued" or "no_group_selected", event)
    P.tick()
end

function P.privacyChanged()
    if not prefs then return end
    local kept = {}
    for _, item in ipairs(outgoing) do
        if canShare(getCharacter(), item.event) then table.insert(kept, item) end
    end
    outgoing = kept
    if not canShare(getCharacter()) and prefs.last_send then status("disabled_by_character_privacy") end
end

function P.showActivity()
    if WoWStatusJournal then WoWStatusJournal.show() end
end

function P.command(text)
    if not prefs then return end
    local command, rest = text:match("^(%S*)%s*(.-)$")
    if groupMode() and (command == "on" or command == "off" or command == "send") then
        notify("Group membership automatically enables updates. Remove a group in /wstatus groups to leave it.")
        return
    end
    if command == "on" then prefs.receive = true; notify("Popup reception enabled for your selected group IDs. Use /wstatus groups to choose them.")
    elseif command == "off" then
        prefs.receive, prefs.broadcast = false, false
        clear()
        status("disabled")
        notify("Popup reception and broadcasts are off.")
    elseif command == "send" and (rest == "on" or rest == "off") then
        prefs.broadcast = rest == "on"
        if not prefs.broadcast then outgoing = {} end
        notify(prefs.broadcast and "Broadcasts enabled for shared characters with level collection. Group updates use addon whispers; both players must be reachable in WoW."
            or "Popup broadcasts disabled.")
    elseif command == "sound" and (rest == "on" or rest == "off") then
        prefs.sound = rest == "on"
        notify("Popup sound " .. rest .. ".")
    elseif command == "channel" and rest:match("^WStatus[%w]+$") and #rest <= 30 then
        if next(WoWStatusGroups.selected(getCharacter())) then
            notify("Group IDs control popup channels. Edit /wstatus groups instead."); return
        end
        clear()
        prefs.channel, prefs.legacy_channel = rest, true
        notify("Channel selected. Join it yourself with /join " .. rest .. ". Everyone must choose the same channel.")
    elseif command == "trust" or command == "untrust" then
        local sender, alias = rest:match("^(%S+)%s*(.-)$")
        local key = P.senderKey(sender)
        if not key or #alias > 40 or alias:find("[%c|]") then notify("Use trust Character-Realm [optional friend label]."); return end
        if command == "trust" then
            local count = 0
            for _ in pairs(prefs.trusted) do count = count + 1 end
            if count >= 200 and not prefs.trusted[key] then notify("Trust list is full."); return end
            prefs.trusted[key] = alias ~= "" and alias or true
        else prefs.trusted[key] = nil end
        notify("Trust preference updated for " .. sender .. ".")
        P.tick()
    elseif command == "test" then
        if not receiving() then notify("Join a group first, or use /wstatus popup on for a local preview."); return end
        if #incoming < 20 then
            table.insert(incoming, {sender = "Preview", key = "local-preview", level = 25,
                received_at = time(), preview = true})
            P.tick()
        end
    elseif command == "status" then
        notify((groupMode() and "Group updates: automatic" or ("Legacy popups: receive=" .. tostring(prefs.receive) .. ", broadcast=" .. tostring(prefs.broadcast)))
            .. ", sound=" .. tostring(prefs.sound) .. ", channel=" .. prefs.channel
            .. ", groups=" .. WoWStatusGroups.text(getCharacter()) .. ".")
        for id in pairs(WoWStatusGroups.selected(getCharacter())) do
            notify("Group " .. id .. ": joined=" .. tostring(joined(id) ~= nil) .. ", discovered peers=" .. #P.peers(id))
        end
        notify("Last broadcast: " .. (prefs.last_send and prefs.last_send.state or "none")
            .. ". Delivery is not acknowledged. Character privacy gates outgoing levels.")
    else
        notify("Popup commands: on | off | send on/off | sound on/off | channel WStatusNAME")
        notify("Trust: trust Character-Realm [friend label] | untrust Character-Realm. Test: test. Diagnostics: status.")
    end
end

frame:RegisterEvent("CHAT_MSG_CHANNEL")
frame:RegisterEvent("CHAT_MSG_ADDON")
frame:RegisterEvent("CHANNEL_ROSTER_UPDATE")
frame:RegisterEvent("PLAYER_REGEN_ENABLED")
frame:RegisterEvent("PLAYER_REGEN_DISABLED")
frame:SetScript("OnEvent", function(_, event, ...)
    if not prefs or not getCharacter then return end
    if event == "CHAT_MSG_ADDON" then
        local prefix, text, distribution, sender = ...
        prefix, text, distribution = S.string(prefix), S.string(text), S.string(distribution)
        if prefix ~= ADDON_PREFIX or distribution ~= "WHISPER" or not text or #text > 243 then return end
        local group, message = text:match("^([a-f0-9]+) (.+)$")
        if group and WoWStatusGroups.valid(group) and WoWStatusGroups.contains(getCharacter(), group) then
            P.receive(message, sender, WoWStatusGroups.channel(group))
        end
    elseif event == "CHAT_MSG_CHANNEL" then
        local text, sender, _, _, _, _, _, _, channel = ...
        P.receive(text, sender, channel)
    else P.tick() end
end)
local accumulated = 0
frame:SetScript("OnUpdate", function(_, elapsed)
    accumulated = accumulated + elapsed
    if accumulated >= .25 then accumulated = 0; P.tick() end
end)
