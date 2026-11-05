-- In-game group updates. Custom channels discover peers; addon whispers carry data.
WoWStatusPopups = {}
local P = WoWStatusPopups
local A, S = WoWStatusAdapter, WoWStatusSafe
local prefs, getCharacter, notify, toast, active
local incoming, outgoing = {}, {}
local lastDisplay, nextSend = 0, 0
local pacing = {} -- Throttles in a row on this prefix: see P.retryWait.
local joinedByAddon, syncPending = {}, false
local frame = CreateFrame("Frame")
local PREFIX = "WSTATUS1"
local ADDON_PREFIX = "WoWStatus"
local ADDON_NAME = (...) or "WoWStatus" -- client-supplied folder/TOC name, not the comm prefix
local rosterRequested,rosterCache,knownPeers,pendingRoster={},{},{},nil
-- GUIDs that channel rosters gave for members, by sender key (bounded).
local rosterGuids,rosterGuidCount={},0
local rosterBusy=false
-- Received updates from a sender not yet in the group's roster wait here while
-- the roster loads. One sender may hold only a few queued or waiting updates.
-- The roster cache is keyed on member count and kept for 30 seconds, so a member
-- who replaced another at the same size appears only once it expires; a refresh
-- can then take a few more 5-second request and read windows.
local unverified, lastVerify = {}, nil
local MAX_QUEUED_PER_SENDER, VERIFY_SECONDS, MAX_UNVERIFIED = 4, 60, 32
-- While a changed roster reloads, members from the last complete read still
-- count, but only for this long after that read.
local LAST_ROSTER_SECONDS = 120
-- Freshness of a live update, in realm time (issues #7 and #9): receivers accept
-- stamps at most LIVE_WINDOW seconds old or LIVE_AHEAD seconds ahead (see
-- late()), and the sender keeps delivering an update to every peer until then:
-- one whisper a second, so three updates to three groups of 20 take three
-- minutes. prefs.seen keeps an update for both together, so a replay the window
-- accepts is still a duplicate. Clients before #9 accept only two minutes.
local LIVE_WINDOW, LIVE_AHEAD = 600, 300
-- Read the running version from this addon's TOC so status never drifts from releases.
-- Retail removed the global GetAddOnMetadata; Classic clients may only have one of the two.
local function metadataVersion(lookup)
    local version = S.stringCall(lookup, ADDON_NAME, "Version")
    version = version and S.trim(version)
    if version and version ~= "" and #version <= 64 and not version:find(S.CONTROL_OR_PIPE) then return version end
end
local function tocVersion()
    return metadataVersion(type(C_AddOns) == "table" and C_AddOns.GetAddOnMetadata)
        or metadataVersion(GetAddOnMetadata) or "unknown"
end
P.runtimeVersion=tocVersion()

local function realm()
    local value = A.realmName()
    return value and S.stripSpace(value) or ""
end
-- Whisper targets of the last few seconds. The server answers an addon whisper
-- to someone who is not (or no longer) online with a "No player named ... is
-- currently playing" chat line; those lines are hidden for these targets only,
-- and the target stops counting as recently heard. Your own whispers still show
-- the message, unless the addon whispered the same name in those seconds.
local whispers = {}
local WHISPER_ECHO = 10
local function whisperKey(name)
    local short = S.string(name) and name:match("^([^-]+)")
    return short and S.lowerASCII(S.stripSpace(short)) or nil
end
function P.whispered(target)
    local key = whisperKey(target)
    if not key then return end
    local now, count = time(), 0
    for k, at in pairs(whispers) do
        if now - at > WHISPER_ECHO then whispers[k] = nil else count = count + 1 end
    end
    if count < 256 or whispers[key] then whispers[key] = now end
end
-- ERR_CHAT_PLAYER_NOT_FOUND_S is the client's "No player named '<name>' is
-- currently playing." line with a format placeholder for the name; the pattern
-- is built from the client's own string, so it follows the client's language.
local notFound
local function notFoundPattern()
    if notFound == nil then
        local text = S.string(ERR_CHAT_PLAYER_NOT_FOUND_S)
        notFound = text and ("^" .. text:gsub("([%^%$%(%)%%%.%[%]%*%+%-%?])", "%%%1"):gsub("%%%%s", "(.+)") .. "$") or false
    end
    return notFound or nil
end
function P.filterNotFound(message)
    local pattern = notFoundPattern()
    local text = S.string(message)
    if not pattern or not text then return false end
    local name = text:match(pattern)
    local key = whisperKey(name)
    local at = key and whispers[key]
    if not at or time() - at > WHISPER_ECHO then return false end
    for group, known in pairs(knownPeers) do
        for k in pairs(known) do if whisperKey(k) == key then known[k] = nil end end
    end
    return true
end
do
    local addFilter = (ChatFrameUtil and ChatFrameUtil.AddMessageEventFilter) or ChatFrame_AddMessageEventFilter
    if addFilter then
        pcall(addFilter, "CHAT_MSG_SYSTEM", function(_, _, message) return P.filterNotFound(message) end)
    end
end
-- WoW Forever requires a first and last name ("Edith Aateigen"); names without
-- one there come from older versions that only knew the first name. True when a
-- name is complete for this edition.
function P.fullName(name)
    if not A.full_names then return true end
    local short = S.string(name) and name:match("^([^-]+)")
    return short ~= nil and S.trim(short):find(" ", 1, true) ~= nil
end
-- The GUID a channel roster gave for this member, if any.
function P.guidFor(name)
    local key=P.senderKey(name)
    return key and rosterGuids[key] or nil
end
-- A character's name and realm as other players see them: "Name-Realm".
-- WoW Forever's UnitName gives only a first name ("Edith") while chat and
-- channel rosters use the full name ("Edith Aateigen"); the full name is learnt
-- from a roster entry carrying this character's GUID (chat_name). The realm is
-- the normalized one, as in senderKey, saved at login (normalized_realm).
function P.characterName(character)
    local identity = character.identity
    local name = S.string(character.chat_name) or identity.name
    local realmName = S.string(character.normalized_realm) or identity.realm
    return name .. "-" .. S.stripSpace(realmName)
end
function P.ownName()
    local character = getCharacter and getCharacter()
    return character and S.string(character.chat_name) or A.playerName()
end
-- Learns this character's full chat name from a roster entry with its GUID.
local function learnName(name)
    local character = getCharacter and getCharacter()
    local short = S.string(name) and name:match("^([^-]+)")
    if not character or not short or character.chat_name == short then return end
    character.chat_name = short
    if WoWStatusJournal and WoWStatusJournal.selfRenamed then WoWStatusJournal.selfRenamed() end
end
-- Whether a name (and the GUID a roster gives) is this character. The realm in
-- a name need not match GetNormalizedRealmName: WoW Forever names its realm
-- internally ("CAMWOWEU5Realm1PvE"), so a full-name comparison alone kept you in
-- your own roster, whispered you ("No player named ...") and counted you online.
function P.isSelf(name, guid)
    local own = S.stringCall(UnitGUID, "player")
    guid = S.string(guid)
    if guid and own then return guid == own end
    name = S.string(name)
    if not name then return false end
    local short = name:match("^([^-]+)")
    for _, player in ipairs({P.ownName() or "", A.playerName() or ""}) do
        if player ~= "" and (P.senderKey(name) == P.senderKey(player .. "-" .. realm())
            or (short and S.lowerASCII(S.stripSpace(short)) == S.lowerASCII(S.stripSpace(player)))) then
            return true
        end
    end
    return false
end
function P.senderKey(sender)
    sender = S.string(sender)
    if type(sender) ~= "string" or #sender == 0 or #sender > 120 or sender:find(S.CONTROL_OR_PIPE) then return nil end
    if not sender:find("-", 1, true) then sender = sender .. "-" .. realm() end
    return S.lowerASCII(S.stripSpace(sender))
end
-- An event's nonce is "<epoch>-<sequence>-<random>". Epoch and sequence keep a
-- character's IDs unique; the random tail makes the next one unpredictable, so a
-- relay can't claim it in advance (issue #3). Receivers accept any [%w-] nonce.
function P.newNonce(character)
    return character.epoch .. "-" .. character.sequence .. "-"
        .. string.format("%04x%04x", math.random(0, 65535), math.random(0, 65535))
end
-- Events from before random tails derive the old "<epoch>-<sequence>" form from
-- their "<guid>:<epoch>:<sequence>" ID.
function P.eventNonce(event)
    if type(event.nonce) == "string" then return event.nonce end
    if type(event.id) ~= "string" then return nil end
    local epoch, sequence = event.id:match(":(%d+%-%d+):(%d+)$")
    return epoch and epoch .. "-" .. sequence or nil
end
-- Whether popups should wait: the player's own combat state where the client
-- reports it. The UI lockdown flag is only a fallback; WoW Forever can report a
-- lockdown outside combat, which held every popup until it expired.
local function combat()
    if UnitAffectingCombat then
        local fighting = S.call(UnitAffectingCombat, "player")
        if fighting ~= nil then return fighting == true end
    end
    return InCombatLockdown and InCombatLockdown() and true or false
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
    if event.kind == "discovery" or event.kind == "lfg" then return false end
    if event.kind == "dungeon" and event.data.source ~= "game_api" then return false end
    local category=({raid="dungeon",epicmount="mount"})[event.kind] or event.kind
    if not character.settings.collection[category] then return false end
    if character.settings.in_game and character.settings.in_game[category] == false then return false end
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
-- The client's channel number when the player is in the named channel right now.
local function inChannel(name)
    if not GetChannelName then return nil end
    local id, actual = S.call(GetChannelName, name)
    if type(id) ~= "number" or id < 1 or type(actual) ~= "string" or actual:lower() ~= name:lower() then return nil end
    return id
end
local function joined(group)
    if not prefs then return nil end
    local name = group and WoWStatusGroups.channel(group) or prefs.channel
    if not channels()[name:lower()] then return nil end
    return inChannel(name)
end
-- The roster arrives asynchronously after selection. Restoring the old UI
-- selection immediately can leave an empty roster forever on one client.
local function displayInfo(index)
    local ok,name,header,_,_,count=pcall(GetChannelDisplayInfo,index)
    if not ok or S.value(header)~=false then return nil end
    return S.string(name),S.number(count) or 0
end
local function readRoster(index,count)
    local getter=C_ChatInfo and C_ChatInfo.GetChannelRosterInfo or GetChannelRosterInfo
    local result,seen,read={}, {},0
    local first=A.playerName()
    first=first and not first:find(" ",1,true) and S.lowerASCII(first) or nil
    local candidates,learnt={},false
    for i=1,math.min(count,64) do
        local name,_,_,guid=S.call(getter,index,i)
        local target=S.string(name);local key=target and P.senderKey(target)
        if key then
            read=read+1
            if S.string(guid) and not P.isSelf(target,guid) and not rosterGuids[key] and rosterGuidCount<512 then
                rosterGuids[key]=S.string(guid);rosterGuidCount=rosterGuidCount+1
            end
            if P.isSelf(target,guid) then
                if S.string(guid) then learnName(target);learnt=true end
            elseif not seen[key] then
                seen[key]=true;result[#result+1]=target
                -- Without GUIDs: "Edith Aateigen" when the game calls this character "Edith".
                local short=target:match("^([^-]+)")
                if first and short and S.lowerASCII(short):sub(1,#first+1)==first.." " then candidates[#candidates+1]=target end
            end
        end
    end
    -- Exactly one such member in a complete read is this character; two could be
    -- anyone, so nothing is learnt then.
    if not learnt and #candidates==1 and count>0 and read>=math.min(count,64) then
        learnName(candidates[1])
        for i,target in ipairs(result) do if target==candidates[1] then table.remove(result,i);break end end
    end
    return result,count>0 and read>=math.min(count,64)
end
-- Blizzard's channel list owns selection; the old getter is not present on
-- every client. Track native selection calls, including the user's changes.
local rosterSelection
if hooksecurefunc and SetSelectedDisplayChannel then
    pcall(hooksecurefunc,"SetSelectedDisplayChannel",function(index) rosterSelection=S.number(index) end)
end
local function selectedChannel()
    local selected=S.number(S.call(GetSelectedDisplayChannel)) or rosterSelection
    if selected then return selected end
    local list=ChannelFrame and S.call(ChannelFrame.GetList,ChannelFrame)
    return list and S.number(S.call(list.GetSelectedChannelIDAndSupportsText,list))
end
local function releaseRoster()
    local request=pendingRoster;pendingRoster=nil
    if request and request.previous and request.previous~=request.index
        and selectedChannel()==request.index then S.call(SetSelectedDisplayChannel,request.previous) end
end
local function advanceRoster()
    if not pendingRoster then return end
    local request=pendingRoster
    local name,count=displayInfo(request.index)
    if not name or name:lower()~=WoWStatusGroups.channel(request.group):lower() then releaseRoster();return end
    local peers,complete=readRoster(request.index,count)
    if complete then rosterCache[request.group]={peers=peers,count=count,at=time()};releaseRoster()
    elseif time()-request.at>=5 then releaseRoster() end
end
function P.notePeer(group,target)
    if not group or not WoWStatusGroups.contains(getCharacter(),group) then return end
    local key=P.senderKey(target)
    if not key or P.isSelf(target) then return end
    knownPeers[group]=knownPeers[group] or {}
    local count,oldest,oldestAt=0,nil,math.huge
    for k,item in pairs(knownPeers[group]) do
        count=count+1;if item.at<oldestAt then oldest,oldestAt=k,item.at end
    end
    if count>=64 and not knownPeers[group][key] and oldest then knownPeers[group][oldest]=nil end
    knownPeers[group][key]={name=target,at=time()}
end
local function withKnown(group,roster)
    local result,seen={},{}
    for _,name in ipairs(roster or {}) do local key=P.senderKey(name);if key then seen[key]=true;result[#result+1]=name end end
    for key,item in pairs(knownPeers[group] or {}) do
        if time()-item.at>300 then knownPeers[group][key]=nil
        elseif not seen[key] and #result<64 then seen[key]=true;result[#result+1]=item.name end
    end
    return result
end
-- Group members online across all joined groups, without requesting a roster:
-- the last complete roster read plus recently heard peers, or else the
-- channel's member count without you. Used by the status line (#62).
function P.character() return getCharacter and getCharacter() or nil end
-- A roster read is never refreshed by this count, so it is trusted only while
-- the channel still has the member count it was read at: members who logged
-- off must not stay "online". Where the channel is visible, its count without
-- you is the ceiling for that group.
local function channelMembers(group)
    if not GetNumDisplayChannels or not GetChannelDisplayInfo then return nil end
    local total=S.number(S.call(GetNumDisplayChannels)) or 0
    for index=1,math.min(total,128) do
        local name,members=displayInfo(index)
        if name and name:lower()==WoWStatusGroups.channel(group):lower() then return members end
    end
end
function P.onlineCount()
    if not prefs or not getCharacter then return 0 end
    local seen,count,fallback={},0,0
    for group in pairs(WoWStatusGroups.selected(getCharacter())) do
        local cached,members=rosterCache[group],channelMembers(group)
        local names
        if members then
            local others=math.max(0,members-1)
            if cached and cached.count==members then names=cached.peers
            else names={};fallback=math.max(fallback,others) end
            -- Recently heard members count only while the channel has room for them.
            local known=withKnown(group,names)
            names={}
            for i=1,math.min(#known,others) do names[i]=known[i] end
        else
            names=withKnown(group,cached and cached.peers)
        end
        for _,name in ipairs(names) do
            local key=P.senderKey(name)
            if key and not seen[key] then seen[key]=true;count=count+1 end
        end
    end
    return math.max(count,fallback)
end
function P.peers(group)
    if not GetNumDisplayChannels or not GetChannelDisplayInfo then return withKnown(group,{}) end
    if rosterBusy then return withKnown(group,rosterCache[group] and rosterCache[group].peers) end
    rosterBusy=true;advanceRoster()
    local count=S.number(S.call(GetNumDisplayChannels)) or 0
    for index=1,math.min(count,128) do
        local name,members=displayInfo(index)
        if name and name:lower()==WoWStatusGroups.channel(group):lower() then
            local cached=rosterCache[group]
            if cached and cached.count==members and time()-cached.at<30 then rosterBusy=false;return withKnown(group,cached.peers) end
            if not SetSelectedDisplayChannel then
                local peers,complete=readRoster(index,members)
                if complete then rosterCache[group]={peers=peers,count=members,at=time()} end
                rosterBusy=false;return withKnown(group,peers)
            end
            if not pendingRoster and (not rosterRequested[group] or time()-rosterRequested[group]>=5) then
                rosterRequested[group]=time()
                pendingRoster={group=group,index=index,at=time(),previous=selectedChannel()}
                S.call(SetSelectedDisplayChannel,index);rosterSelection=index;advanceRoster()
            end
            cached=rosterCache[group];rosterBusy=false
            return withKnown(group,cached and cached.count==members and cached.peers or {})
        end
    end
    rosterBusy=false;return withKnown(group,{})
end
-- logged: commit already wrote this update to the log.
local function remember(item, logged)
    if item.preview then return end
    item.flavour=WoWStatusFlavour.text(item)
    if WoWStatusJournal and not logged then WoWStatusJournal.received(item) end
    prefs.activity = prefs.activity or {}
    table.insert(prefs.activity, 1, {sender = item.sender, level = item.level,
        kind = item.kind or "level", text = item.text, flavour=item.flavour, automatic = item.automatic, nonce = item.nonce, original_at = item.at, quality=item.quality, class_id=item.class_id, equip_loc=item.equip_loc, item_id=item.item_id, at = time(), group_id = item.group_id})
    while #prefs.activity > 200 do table.remove(prefs.activity) end
end
-- Channels this addon joined, kept in SavedVariables: /reload restarts module
-- state while the game keeps the channels joined (issue #20). On load, keep only
-- group channels the player is in right now; the game drops them at logout, so
-- entries from earlier sessions or characters cannot outlive their channel. The
-- client's channel limit bounds what survives.
local function savedChannels(saved)
    local result = {}
    if type(saved) ~= "table" then return result end
    for name, flag in pairs(saved) do
        local id = flag == true and WoWStatusGroups.channelId(name)
        if id and name == WoWStatusGroups.channel(id):lower() and (not GetChannelName or inChannel(name)) then
            result[name] = true
        end
    end
    return result
end
function P.groupsChanged()
    if not prefs then return end
    prefs.legacy_channel = false
    releaseRoster();rosterCache,rosterRequested={},{}
    for group in pairs(knownPeers) do if not WoWStatusGroups.contains(getCharacter(),group) then knownPeers[group]=nil end end
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
    kept = {}
    for _, item in ipairs(unverified) do
        if WoWStatusGroups.contains(getCharacter(), item.group) then table.insert(kept, item) end
    end
    unverified = kept
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
local function status(state, event, target)
    prefs.last_send = {state = state, at = time(), event_id = event and event.id or nil, target = target}
end
local function clear()
    incoming, outgoing, unverified, active, lastVerify = {}, {}, {}, nil, nil
    nextSend, pacing = 0, {}
    if toast then toast:Hide() end
end
-- Classifies a pcall of a send: "sent"; "throttled" (the game asks to wait, so
-- retry later); "uncertain" (an older client's false, which can also mean
-- throttled); "offline" (the target logged off); or "failed". SendAddonMessage
-- returns an Enum.SendAddonMessageResult on newer clients and a boolean on older
-- ones; the deprecated global wrapper returns the code second, so the last value
-- that is not nil counts.
local RESULT = {Success = 0, AddonMessageThrottle = 3, ChannelThrottle = 8, AddOnMessageLockdown = 11, TargetOffline = 12}
function P.sendResult(ok, ...)
    if not ok then return "failed" end
    local result
    for i = select("#", ...), 1, -1 do
        local value = select(i, ...)
        if value ~= nil then result = S.value(value); break end
    end
    if type(result) ~= "number" then return result == false and "uncertain" or "sent" end
    local codes = type(Enum) == "table" and type(Enum.SendAddonMessageResult) == "table" and Enum.SendAddonMessageResult or {}
    local function is(name) return result == (codes[name] or RESULT[name]) end
    if is("Success") then return "sent" end
    if is("AddonMessageThrottle") or is("ChannelThrottle") or is("AddOnMessageLockdown") then return "throttled" end
    return is("TargetOffline") and "offline" or "failed"
end
-- Seconds to wait before sending item again after result, or nil to move on.
-- A throttle is always retried, after 2, 4, 8, then every 16 s while throttles
-- on the queue's prefix (counted in state) continue. An older client's false is
-- retried once, after 2 s, without counting as a throttle. If that retry says
-- false too, false is final on this queue for the next minute, so a client that
-- always says false is barely slowed down, and one whose false is a long
-- throttle still gets retries again after that.
function P.retryWait(result, item, state, now)
    if result == "throttled" then
        state.throttles = (state.throttles or 0) + 1
        return math.min(2 ^ state.throttles, 16)
    end
    if result == "uncertain" then
        if not item.unsure and now >= (state.falseFinalUntil or 0) then item.unsure = true; return 2 end
        if item.unsure then state.falseFinalUntil = now + 60 end
    end
    item.unsure, state.throttles = nil, 0
    return nil
end
local function pruneSeen(now)
    local count, oldest, oldestAt = 0, nil, math.huge
    for key, at in pairs(prefs.seen) do
        if type(at) ~= "number" or now - at > LIVE_WINDOW + LIVE_AHEAD or at > now + LIVE_AHEAD then prefs.seen[key] = nil
        else
            count = count + 1
            if at < oldestAt then oldest, oldestAt = key, at end
        end
    end
    if count >= 512 and oldest then prefs.seen[oldest] = nil end

end

function P.init(database, getter, reporter)
    database.popups = database.popups or {
        receive = true, broadcast = true, sound = false, channel = "WStatusFriends",
        trusted = {}, seen = {},
    }
    prefs, getCharacter, notify = database.popups, getter, reporter
    rosterRequested,rosterCache,knownPeers,pendingRoster={},{},{},nil;rosterBusy=false
    prefs.trusted, prefs.seen = prefs.trusted or {}, prefs.seen or {}
    prefs.level_claims = prefs.level_claims or {}
    prefs.channel = prefs.channel or "WStatusFriends"
    joinedByAddon = savedChannels(prefs.joined_channels)
    prefs.joined_channels = joinedByAddon
    local activity={}
    for _, item in ipairs(prefs.activity or {}) do
        if item.kind~="discovery" and item.kind~="lfg" and (item.kind~="dungeon" or item.automatic)
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

local function invalidLogData(group,sender)
    if group~="legacy" and WoWStatusJournal then WoWStatusJournal.reportInvalid(group,sender) end
    return false
end
local function queuedFrom(key, event)
    local count, held = 0, {[event or false] = true}
    for _, item in ipairs(incoming) do
        if item.key == key and not item.preview and item.kind ~= "guard" then count = count + 1 end
    end
    -- The same event can wait once per shared group; it counts once, and a
    -- further copy of the given event adds nothing.
    for _, item in ipairs(unverified) do
        local event = item.level or item.nonce
        if item.key == key and not held[event] then held[event] = true; count = count + 1 end
    end
    return count
end
local function noteReceive(state, c, now)
    prefs.last_receive = {state=state, sender=c.sender, kind=c.kind or "level", at=now}
end
-- Packet timestamps outside the freshness window are dropped. The latest drop
-- is kept apart from last_receive, so /wstatus popup status can say why (issue
-- #7) even before the sender's roster entry loads, and no sender can hide the
-- last real update behind a drop.
local function late(sender, kind, at, now)
    local reason, realm = S.outside(at, LIVE_WINDOW, LIVE_AHEAD)
    if reason then
        prefs.last_dropped = {state="rejected_"..reason, sender=sender, kind=kind or "level", at=now,
            offset=at-realm, pc_clock=S.realmTime()==nil or nil}
    end
    return reason ~= nil
end
-- Store a validated update from a known peer (or a trusted legacy sender): log
-- it, then queue its popup unless the log already had it.
local function commit(c, now)
    pruneSeen(now)
    local item = {sender=c.sender, key=c.key, kind=c.kind, level=c.level, count=c.level and 1 or nil, text=c.text,
        automatic=c.automatic, received_at=now, at=c.at, nonce=c.nonce, group_id=c.group~="legacy" and c.group or nil}
    for k,v in pairs(c.loot or {}) do item[k]=v end
    local duplicate = c.key .. ":" .. (c.level or c.nonce)
    local logged = false
    if WoWStatusJournal and WoWStatusJournal.contains(WoWStatusJournal.eventID(c.sender,c.nonce)) then
        -- A relay's claim on this ID with other content is not a duplicate: the
        -- live data replaces it in the log, even if the popup is dropped below.
        if not WoWStatusJournal.received(item) then
            prefs.seen[duplicate]=now
            noteReceive("already_in_log", c, now)
            return false
        end
        logged = true
    end
    local claims = c.level and prefs.level_claims[c.key]
    if prefs.seen[duplicate] or (claims and claims.levels[c.level]) or #incoming >= 128 then return false end
    if queuedFrom(c.key) >= MAX_QUEUED_PER_SENDER then noteReceive("sender_queue_full", c, now); return false end
    prefs.seen[duplicate] = now
    if c.level then
        if not claims then
            local count, oldest, oldestAt = 0, nil, math.huge
            for senderKey, value in pairs(prefs.level_claims) do
                count = count + 1
                if value.at < oldestAt then oldest, oldestAt = senderKey, value.at end
            end
            if count >= 512 and oldest then prefs.level_claims[oldest] = nil end
            claims = {levels = {}, at = now}
            prefs.level_claims[c.key] = claims
        end
        claims.levels[c.level], claims.at = true, now
    end
    remember(item, logged)
    noteReceive("queued", c, now)
    table.insert(incoming, item)
    return true
end
-- Members of the group's channel: only they may show popups or sync the log.
-- When the member count changes, P.peers lists nobody until the new roster
-- loads, so members from a recent complete read also count: one login or
-- logout must not hold everybody's popups.
local function memberKeys(group)
    local keys = {}
    local current = P.peers(group)
    local cached = rosterCache[group]
    local recent = cached and time() - cached.at < LAST_ROSTER_SECONDS and cached.peers or {}
    for _, list in ipairs({current, recent}) do
        for _, name in ipairs(list) do local key = P.senderKey(name); if key then keys[key] = true end end
    end
    return keys
end
function P.isPeer(group, key)
    return key ~= nil and memberKeys(group)[key] == true
end
-- Whether the group channel's member count differs from the last complete
-- roster read, or there is none. Only then is reading the roster again worth it:
-- a read selects the channel in the chat UI for a moment.
local function rosterChanged(group)
    local cached = rosterCache[group]
    if not cached or not GetNumDisplayChannels or not GetChannelDisplayInfo then return true end
    local count = S.number(S.call(GetNumDisplayChannels)) or 0
    for index = 1, math.min(count, 128) do
        local name, members = displayInfo(index)
        if name and name:lower() == WoWStatusGroups.channel(group):lower() then return members ~= cached.count end
    end
    return false
end
-- Whether a complete roster read taken since the given time lacks this peer,
-- and it was not heard in the channel lately either: it has left. A channel over
-- 64 members is read only in part, so its roster proves nothing.
local function departed(group, target, since)
    local cached, key = rosterCache[group], P.senderKey(target)
    if not key or not cached or cached.at < since or cached.count > 64 then return false end
    for _, name in ipairs(withKnown(group, cached.peers)) do
        if P.senderKey(name) == key then return false end
    end
    return true
end
-- Rosters load asynchronously, so a member who joined moments ago can be
-- missing: their updates wait here, in arrival order, instead of being dropped.
local function verifyPending(now, members)
    if #unverified == 0 then return end
    local waiting = unverified
    members, unverified, lastVerify = members or {}, {}, now
    for _, c in ipairs(waiting) do
        if WoWStatusGroups.contains(getCharacter(), c.group) then
            members[c.group] = members[c.group] or memberKeys(c.group)
            if members[c.group][c.key] then commit(c, now)
            elseif now < c.expires then table.insert(unverified, c)
            else noteReceive("rejected_unknown_sender", c, now) end
        end
    end
end
local function admit(c, now)
    local members = c.group ~= "legacy" and memberKeys(c.group)
    if not members or members[c.key] then
        verifyPending(now, members and {[c.group] = members}) -- Earlier updates that waited go first.
        local queued = commit(c, now)
        P.tick()
        return queued
    end
    if queuedFrom(c.key, c.level or c.nonce) >= MAX_QUEUED_PER_SENDER then noteReceive("sender_queue_full", c, now); return false end
    if #unverified >= MAX_UNVERIFIED then noteReceive("rejected_unknown_sender", c, now); return false end
    c.expires = now + VERIFY_SECONDS
    table.insert(unverified, c)
    noteReceive("verifying_sender", c, now)
    return false
end
function P.receive(text, sender, channel)
    text, sender, channel = S.string(text), S.string(sender), S.string(channel)
    if not receiving() or type(text) ~= "string" or #text > 220
        or type(channel) ~= "string" then return false end
    local group = channels()[channel:lower()]
    if not group then return false end
    local key = P.senderKey(sender)
    if not key or P.isSelf(sender) or (group == "legacy" and not prefs.trusted[key]) then return false end
    local client, kind, atText, nonce, encoded = text:match("^WSTATUS3 ([%w%-]+) (%a+) (%d+) ([%w%-]+) ([a-f0-9]+)$")
    local raw, automatic, armor, extended = false, false, false, false
    if not client then
        client,kind,atText,nonce,encoded=text:match("^WSTATUS8 ([%w%-]+) (%a+) (%d+) ([%w%-]+) (.+)$")
        raw,extended=client~=nil,client~=nil
    end
    if not client then
        client,kind,atText,nonce,encoded = text:match("^WSTATUS4 ([%w%-]+) (%a+) (%d+) ([%w%-]+) (.+)$")
        raw = client ~= nil
    end
    if not client then
        client,kind,atText,nonce,encoded = text:match("^WSTATUS5 ([%w%-]+) (%a+) (%d+) ([%w%-]+) (.+)$")
        raw,automatic = client~=nil,client~=nil
    end
    if not client then
        client,kind,atText,nonce,encoded=text:match("^WSTATUS7 ([%w%-]+) (%a+) (%d+) ([%w%-]+) (.+)$")
        raw,armor=client~=nil,client~=nil
    end
    if client then
        local allowed = {raid=true,epicmount=true,recap=true,introduction=true,loot=true, death=true, zone=true, quest=true, profession=true, dungeon=true, mount=true, reputation=true, unlock=true, pvp=true}
        if extended~=(kind=="raid" or kind=="epicmount" or kind=="recap") then return false end
        local at, now = tonumber(atText), time()
        if client ~= A.client_id or not allowed[kind] or #nonce > 64 or #encoded > (raw and 120 or 96)
            or (not raw and #encoded % 2 ~= 0) then return false end
        if late(sender, kind, at, now) then return false end
        local detail = raw and encoded or encoded:gsub("..", function(pair) return string.char(tonumber(pair, 16)) end)
        if detail:find(S.CONTROL_OR_PIPE) then return invalidLogData(group,sender) end
        local lootInfo
        if armor and kind~="loot" then return false end
        if kind=="loot" then
            if not armor then return false end
            local quality,class,slot,id,name=detail:match("^(%d) (%d+) ([A-Z_]+) (%d+) (.+)$")
            lootInfo={quality=tonumber(quality),class_id=tonumber(class),equip_loc=slot,item_id=tonumber(id)}
            if not lootInfo.item_id or not name or not WoWStatusLoot.allowed(getCharacter().settings,lootInfo) then return false end
            detail="Equipped "..name
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
        -- Check the text as it will be shown, after the loot and dungeon conversions.
        if WoWStatusJournal and not WoWStatusJournal.validText(kind,detail) then return invalidLogData(group,sender) end
        return admit({sender=sender, key=key, group=group, kind=kind, text=detail,
            automatic=automatic, at=at, nonce=nonce, loot=lootInfo}, now)
    end
    local client, levelText, atText, nonce = text:match("^WSTATUS2 ([%w%-]+) LEVEL (%d+) (%d+) ([%w%-]+)$")
    if not client and A.client_id == "classic-era" then
        levelText, atText, nonce = text:match("^" .. PREFIX .. " LEVEL (%d+) (%d+) ([%w%-]+)$")
        if levelText then client = "classic-era" end
    end
    if client ~= A.client_id then return false end
    local level, at, now = tonumber(levelText), tonumber(atText), time()
    if not at or not nonce or #nonce > 64 then return false end
    if late(sender, nil, at, now) then return false end
    if not level or level < 2 or level > A.max_level then return invalidLogData(group,sender) end
    return admit({sender=sender, key=key, group=group, level=level, at=at, nonce=nonce}, now)
end

-- Big banners (#61): max level and every 10th level get a larger toast.
-- Successful first raid encounters and proven Classic epic mounts also qualify.
function P.bigMoment(item)
    if not prefs or prefs.big_banners == false then return false end
    if item.kind=="raid" or item.kind=="epicmount" then return true end
    local level = S.number(item.level)
    return level ~= nil and level > 0 and (level % 10 == 0 or level == A.max_level)
end
local function anchor(frame, drop)
    local position = prefs and prefs.popup_position
    frame:ClearAllPoints()
    if type(position) == "table" and type(position.point) == "string" and type(position.x) == "number"
        and type(position.y) == "number" then
        frame:SetPoint(position.point, UIParent, position.relative or position.point, position.x, position.y - drop)
    else
        frame:SetPoint("TOP", 0, -170 - drop)
    end
end
-- Movable popups: unlocking shows a drag handle; the position is account-wide.
function P.setUnlocked(value)
    if not prefs then return end
    prefs.popup_unlocked = value == true
    if toast then toast.handle:SetShown(prefs.popup_unlocked) end
    if prefs.popup_unlocked then P.preview("level") end
end
function P.resetPosition()
    if not prefs then return end
    prefs.popup_position = nil
    if toast then anchor(toast, 0) end
end
-- Re-apply the size of a visible toast after a theme change.
function P.restyle()
    if toast and toast:IsShown() then
        toast:SetScale((toast.big and 1.35 or 1) * (WoWStatusTheme and WoWStatusTheme.scale(true) or 1))
    end
end
function P.setBigBanners(value) if prefs then prefs.big_banners = value ~= false end end
function P.options()
    return {unlocked = prefs and prefs.popup_unlocked == true, big_banners = not prefs or prefs.big_banners ~= false}
end
-- Left-click opens the toast's activity-log entry; any click dismisses it.
local function entryID(item)
    if not item or item.preview or not item.nonce or not WoWStatusJournal then return nil end
    local id = WoWStatusJournal.eventID(item.sender, item.nonce)
    return id and WoWStatusJournal.contains(id) and id or nil
end

local function show(item, now)
    if not toast then
        toast = CreateFrame("Frame", "WoWStatusLevelPopup", UIParent)
        toast:SetSize(560, 124)
        anchor(toast, 0)
        toast:SetFrameStrata("DIALOG")
        toast:EnableMouse(true)
        toast:SetMovable(true)
        toast:RegisterForDrag("LeftButton")
        toast:SetScript("OnDragStart", function(self)
            if not prefs.popup_unlocked then return end
            self.dragging, self.moved = true, true
            self:StartMoving()
        end)
        toast:SetScript("OnDragStop", function(self)
            if not self.dragging then return end
            self:StopMovingOrSizing()
            self.dragging = false
            if self.GetPoint then
                local point, _, relative, x, y = self:GetPoint(1)
                if type(point) == "string" and type(x) == "number" and type(y) == "number" then
                    prefs.popup_position = {point=point, relative=relative, x=x, y=y}
                end
            end
        end)
        toast:SetScript("OnMouseUp",function(self,button)
            if self.moved then self.moved = false; return end -- The end of a drag, not a click.
            if button=="LeftButton" or button=="RightButton" then
                local id = button=="LeftButton" and entryID(self.item)
                self:Hide();active=nil
                lastDisplay=time()-7 -- Advance on the next tick, without dropping queued entries.
                if id then WoWStatusJournal.focus(id) end
            end
        end)
        local bg = toast:CreateTexture(nil, "BACKGROUND")
        bg:SetAllPoints(); bg:SetColorTexture(.025, .035, .065, .96)
        toast.bg = bg
        if WoWStatusTheme then WoWStatusTheme.attach(toast, bg, true) end
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
        toast.handle = toast:CreateTexture(nil, "OVERLAY")
        toast.handle:SetPoint("BOTTOMLEFT", toast, "TOPLEFT"); toast.handle:SetSize(560, 10)
        toast.handle:SetColorTexture(1, .82, .25, .8)
        toast.handle:SetShown(prefs.popup_unlocked == true)
        toast:SetScript("OnUpdate", function(self, elapsed)
            if self.dragging then return end -- Hold still and stay visible while being moved.
            self.age = (self.age or 0) + elapsed
            local entrance = math.min(1, self.age / .22)
            local fade = math.max(0, math.min(1, (6 - self.age) / .5))
            self:SetAlpha(entrance * fade)
            anchor(self, (1 - entrance) * 12)
            self.glow:SetAlpha(.5 + .3 * math.sin(self.age * 7))
            if self.age >= 6 then self:Hide(); active = nil end
        end)
    end
    local alias = not item.preview and prefs.trusted[item.key]
    local name = item.sender:match("^[^-]+") or item.sender
    if type(alias) == "string" and alias ~= "" then name = alias .. "’s " .. name end
    name = name:gsub("|", "||")
    local texture, r, g, b, heading = WoWStatusPresentation.theme(item)
    local big = P.bigMoment(item)
    if big and item.level then
        local level = S.number(item.level)
        heading = level == A.max_level and "MAXIMUM LEVEL!" or ("LEVEL " .. level .. "!")
    end
    toast:SetScale((big and 1.35 or 1) * (WoWStatusTheme and WoWStatusTheme.scale(true) or 1))
    toast.big, toast.item = big, item
    toast.handle:SetShown(prefs.popup_unlocked == true)
    toast.icon:SetTexture(texture)
    toast.glow:SetVertexColor(r,g,b)
    toast.accent:SetColorTexture(r,g,b,1)
    toast.heading:SetTextColor(r,g,b); toast.heading:SetText(heading)
    toast.message:SetHeight(42)
    local detail = item.level and ("reached level " .. item.level .. "!"
        .. ((item.count or 1) > 1 and (" (" .. item.count .. " recorded level-ups)") or ""))
        or ((item.text or "Shared an update"):gsub("|", "||"))
    toast.message:SetText(name .. ((item.level or item.kind=="guard") and " " or " — ") .. detail)
    local flavour=WoWStatusFlavour.text(item)
    toast.detail:SetText(flavour)
    toast.detail:SetShown(flavour~="")
    toast.age = 0
    toast:SetAlpha(0)
    toast:Show()
    item.hide_at = now + 6
    active, lastDisplay = item, now
    if not item.preview then prefs.last_receive={state="displayed",sender=item.sender,kind=item.kind or "level",at=now} end
    if prefs.sound and PlaySound and SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPEN then
        PlaySound(SOUNDKIT.IG_MAINMENU_OPEN)
    end
end


-- A local-only notice (for example a new First). Never logged, sent or opened in the log.
-- Notices wait for the next tick, so they follow the update that caused them.
local notices = {}
function P.notice(item)
    if not prefs or #incoming + #notices >= 128 then return false end
    item.preview, item.key, item.received_at = true, "local-notice", time()
    table.insert(notices, item)
    return true
end

function P.preview(kind)
    if not prefs then return end
    local samples = {
        introduction="Joined the WoW Status group", loot="Equipped Robe of the Archmage",
        death="Died — total tracked deaths: 15",
        zone="Entered Stranglethorn Vale", quest="Completed 100 quests!",
        profession="Tailoring: Expert (225 max)",
        profession_learned="Learned Blacksmithing (Apprentice)",
        dungeon="First clear: The Deadmines", mount="First mount: Brown Horse",
        reputation="Exalted with Ironforge", unlock="Unlocked Bear Form", pvp="Promoted to Sergeant",
    }
    if A.classicProfessionTitles==false then
        samples.profession="Learned Inscription"
        samples.profession_learned="Learned Inscription"
    end
    if A.pvpText then samples.pvp=A.pvpText("",101) end
    if kind ~= "level" and not samples[kind] then return end
    if #incoming >= 128 then notify("Notification queue is full; wait for previews to finish."); return end
    table.insert(incoming, {sender="Previewlock",key="local-preview",kind=kind=="profession_learned" and "profession" or kind,text=samples[kind],
        level=kind=="level" and 33 or nil,quality=kind=="loot" and 4 or nil,received_at=time(),preview=true})
    P.tick()
end

local function tick()
    if not prefs then return end
    for _, item in ipairs(notices) do table.insert(incoming, item) end
    notices = {}
    local now = time()
    syncGroups()
    if not receiving() then
        local previews = {}
        for _, item in ipairs(incoming) do if item.preview then table.insert(previews,item) end end
        incoming, unverified = previews, {}
        if active and not active.preview then
            active = nil
            if toast then toast:Hide() end
        end
    end
    if now ~= lastVerify then verifyPending(now) end -- At most once a second.
    if active and not active.preview and not (active.group_id
        and WoWStatusGroups.contains(getCharacter(), active.group_id)) and not prefs.trusted[active.key] then
        active = nil
        if toast then toast:Hide() end
    end
    -- Combat only holds what is shown. Sending carries on: addon messages are not
    -- combat-protected, and holding them let queued updates expire unsent.
    if combat() then
        if active then
            table.insert(incoming, 1, active)
            active = nil
            if toast then toast:Hide() end
        end
    else
        if active and now >= active.hide_at then active = nil; if toast then toast:Hide() end end
        if (receiving() or (#incoming > 0 and incoming[1].preview)) and not active and #incoming > 0 and now - lastDisplay >= 7 then
            local item = table.remove(incoming, 1)
            if (item.preview or (item.group_id and WoWStatusGroups.contains(getCharacter(), item.group_id))
                or prefs.trusted[item.key]) and (item.kind~="guard" or canShare(getCharacter())) then show(item, now) end
        end
    end
    if #outgoing == 0 or now < nextSend then return end
    local item, character = outgoing[1], getCharacter()
    -- Every target is tried until receivers would drop the packet as stale,
    -- however many whispers are queued ahead of it (#9).
    if not canShare(character, item.event) or S.now() - item.at > LIVE_WINDOW
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
            item.targets, item.target, item.since, item.checked = targets, 1, now, now
        elseif now - item.checked >= 10 then
            -- The list is taken at the first send and can be minutes old by the
            -- last, or partial while the roster was loading: when the member
            -- count changes, read the roster again and add peers not yet listed.
            item.checked = now
            if rosterChanged(item.group_id) then
                local listed = {}
                for _, name in ipairs(item.targets) do listed[P.senderKey(name) or name] = true end
                for _, name in ipairs(P.peers(item.group_id)) do
                    local key = P.senderKey(name)
                    if key and not listed[key] and #item.targets < 64 then listed[key] = true; item.targets[#item.targets + 1] = name end
                end
            end
        end
        -- Skip a peer that a newer complete roster read no longer lists.
        while departed(item.group_id, item.targets[item.target], item.since) do
            item.unsure = nil -- A pending retry was for that peer.
            if item.target == #item.targets then
                table.remove(outgoing, 1); status("remaining_peers_left", item.event); return
            end
            item.target = item.target + 1
        end
        args = {ADDON_PREFIX, item.group_id .. " " .. item.message, "WHISPER", item.targets[item.target]}
    else
        send = A.chatSender()
        if not send then status("unsupported_api", item.event); return end
        args = {item.message, "CHANNEL", nil, tostring(joined(item.group_id))}
    end
    local unpackArgs = unpack or table.unpack
    if args[3] == "WHISPER" then P.whispered(args[4]) end
    local result = P.sendResult(pcall(send, unpackArgs(args, 1, 4)))
    -- A throttled whisper goes to the same target again after a pause; only a
    -- send that went out or failed moves on to the next target.
    local wait = P.retryWait(result, item, pacing, now)
    if wait then
        nextSend = now + wait
        status(result .. "_retrying", item.event, args[4])
        return
    end
    nextSend = now + 1
    if item.targets and item.target < #item.targets then item.target = item.target + 1
    else table.remove(outgoing, 1) end
    if result == "sent" then status("attempted_no_receipt", item.event, args[4])
    elseif result == "offline" then status("peer_offline", item.event, args[4])
    else
        status("blocked_or_uncertain", item.event, args[4])
        if not item.warned then
            item.warned = true -- Once per update, not once per peer.
            notify("In-game update blocked/uncertain; see /wstatus popup status.")
        end
    end
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
    if event.kind=="raid" or event.kind=="epicmount" or event.kind=="recap"
        or event.kind == "dungeon" or event.kind == "mount" or event.kind == "reputation"
        or event.kind == "unlock" or event.kind == "pvp" then return data.text end
    if event.kind == "introduction" then return "Joined the WoW Status group" end
    if event.kind == "quest" then
        return data.completed and ("Completed " .. data.completed .. " quests!") or nil
    end
    if event.kind == "profession" and data.learned then
        local title=data.title or (A.classicProfessionTitles~=false and WoWStatusProgress.professionTitle(data.max_skill))
        return "Learned " .. (data.name or "Profession") .. (title and (" ("..title..")") or "")
    end
    if event.kind == "profession" then return (data.name or "Profession") .. ": " .. (data.title or WoWStatusProgress.professionTitle(data.max_skill)) .. " (" .. (data.max_skill or "?") .. " max)" end
    if event.kind == "death" then return data.total_deaths and ("Total deaths: " .. data.total_deaths) or "Died" end
    if event.kind == "session" then return data.state == "addon_loaded" and "Started a session" or "Ended a session" end
    if event.kind == "zone" then return "Entered " .. (data.zone or "a new zone") end
    if event.kind == "loot" or event.kind == "equipment" then
        local item = data.item and data.item:match("%[([^%]]+)%]") or "an item"
        return (event.kind=="loot" and not data.first_equip and "Looted " or "Equipped ") .. item
    end
end
P.canShare = canShare
P.eventText = eventText
function P.broadcast(character, event)
    if not event or event.kind == "session" or event.kind == "equipment" or not canShare(character, event) or event.data.synthetic then return end
    local nonce = P.eventNonce(event)
    if not nonce then return end
    local text
    if event.kind=="loot" then
        local info=WoWStatusLoot.eventInfo(event.data)
        if not WoWStatusLoot.allowed(character.settings,info) then return end
        local name=info.name or (info.item or ""):match("%[([^%]]+)%]") or "Armor"
        name=name:gsub(S.CONTROL_OR_PIPE," ")
        if #name>72 then name=name:sub(1,69):gsub("[\194-\244][\128-\191]*$","").."..." end
        text="WSTATUS7 "..A.client_id.." loot "..event.at.." "..nonce.." "..info.quality.." "..info.class_id.." "..info.equip_loc.." "..info.item_id.." "..name
    elseif event.kind == "dungeon" then
        local id,name=event.data.instance_id,event.data.name
        if type(id)~="number" or id<1 or id>1000000000 or type(name)~="string" or #name>80 or name:find(S.CONTROL_OR_PIPE) then return end
        text="WSTATUS5 " .. A.client_id .. " dungeon " .. event.at .. " " .. nonce .. " " .. id .. " " .. name
    elseif event.kind == "level" then
        if event.data.level < 2 or event.data.level > A.max_level then return end
        text = "WSTATUS2 " .. A.client_id .. " LEVEL " .. event.data.level .. " " .. event.at .. " " .. nonce
    else
        if event.kind == "loot" and (event.data.quality or 0) < character.settings.loot_quality then return end
        local detail = eventText(event)
        if not detail then return end
        detail = S.stripEscapes(detail):gsub(S.CONTROL_OR_PIPE, " ")
        if not detail:find("[^ ]") then return end
        local extended=event.kind=="raid" or event.kind=="epicmount" or event.kind=="recap"
        local modern = extended or event.kind == "introduction" or event.kind == "dungeon" or event.kind == "mount" or event.kind == "reputation"
            or event.kind == "unlock" or event.kind == "pvp"
        local limit = modern and 120 or 48
        if #detail > limit then
            detail = detail:sub(1, limit-3):gsub("[\194-\244][\128-\191]*$", "") .. "..."
        end
        -- Never send a text that updated receivers would reject and report as invalid.
        if WoWStatusJournal and not WoWStatusJournal.validText(event.kind, detail) then
            status("invalid_text", event); return
        end
        local encoded = modern and detail or detail:gsub(".", function(char) return string.format("%02x", char:byte()) end)
        text = (extended and "WSTATUS8 " or modern and "WSTATUS4 " or "WSTATUS3 ") .. A.client_id .. " " .. event.kind .. " " .. event.at .. " " .. nonce .. " " .. encoded
    end
    if #text > 220 then return end
    -- Updates stay queued for up to LIVE_WINDOW; a full queue says so.
    local groups, full = WoWStatusGroups.selected(character), false
    local function enqueue(item)
        if #outgoing < 32 then table.insert(outgoing, item) else full = true end
    end
    for id in pairs(groups) do
        if event.group_ids and event.group_ids[id] then enqueue({message = text, at = event.at, event = event, group_id = id}) end
    end
    if not next(groups) and prefs.legacy_channel then enqueue({message = text, at = event.at, event = event}) end
    status(full and "send_queue_full" or #outgoing > 0 and "queued" or "no_group_selected", event)
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

-- "185 s behind realm time" for a difference of -185 seconds; pcClock: it was
-- measured on this PC's clock, without realm time.
local function realmOffset(seconds, pcClock)
    return math.abs(seconds).." s "..(seconds<0 and "behind" or "ahead of")
        ..(pcClock and " this PC's clock" or " realm time")
end
function P.command(text)
    if not prefs then return end
    local command, rest = text:match(S.SPLIT_WORD)
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
        if not prefs.broadcast then outgoing, nextSend, pacing = {}, 0, {} end
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
        local sender, alias = rest:match(S.SPLIT_WORD)
        local key = P.senderKey(sender)
        if not key or #alias > 40 or alias:find(S.CONTROL_OR_PIPE) then notify("Use trust Character-Realm [optional friend label]."); return end
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
        notify("Runtime "..P.runtimeVersion.." · "..A.display_name.." · "..(A.realmName() or "unknown realm")
            .." · "..(S.stringCall(UnitFactionGroup,"player") or "unknown faction"))
        notify((groupMode() and "Group updates: automatic" or ("Legacy popups: receive=" .. tostring(prefs.receive) .. ", broadcast=" .. tostring(prefs.broadcast)))
            .. ", sound=" .. tostring(prefs.sound) .. ", channel=" .. prefs.channel
            .. ", groups=" .. WoWStatusGroups.text(getCharacter()) .. ".")
        for id in pairs(WoWStatusGroups.selected(getCharacter())) do
            local peers=P.peers(id)
            notify("Group "..id..": joined="..tostring(joined(id)~=nil)..", discovered peers="..#peers
                ..(pendingRoster and pendingRoster.group==id and " (roster loading)" or ""))
            if #peers>0 then notify("Peer names: "..table.concat(peers,", ")) end
        end
        notify("Last broadcast: " .. (prefs.last_send and prefs.last_send.state or "none")
            ..(prefs.last_send and prefs.last_send.target and (" to "..prefs.last_send.target) or "")
            .."; updates still sending="..#outgoing)
        local received=prefs.last_receive
        notify("Last received: "..(received and (received.kind.." from "..received.sender.." — "..received.state) or "none")
            .."; popup queue="..#incoming.."; awaiting roster="..#unverified.."; in combat="..tostring(combat() and true or false))
        local dropped=prefs.last_dropped
        if type(dropped)=="table" and type(dropped.offset)=="number" and type(dropped.at)=="number" then
            local ago=math.max(0,time()-dropped.at)
            notify("Last dropped: "..tostring(dropped.kind).." from "..tostring(dropped.sender).." — "..tostring(dropped.state)
                .." (stamped "..realmOffset(dropped.offset,dropped.pc_clock)..", "
                ..(ago<120 and (ago.." s") or (math.floor(ago/60).." min")).." ago)")
        end
        local offset=S.clockOffset()
        -- Within a minute of a whole number of half hours: a time zone mix-up, on
        -- this PC or in the game's realm clock (#25 checks GetServerTime).
        local halves=offset and math.floor((math.abs(offset)+60)/1800)
        local zone=halves and halves>=1 and math.abs(math.abs(offset)-halves*1800)<=60
        notify("Clock: "..(not offset and "realm time unavailable; using this PC's clock"
            or math.abs(offset)<=1 and "this PC matches realm time"
            or ("this PC is "..realmOffset(offset)))
            ..(zone and " (check the PC's time zone)" or "")..".")
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
        channel,sender=S.string(channel),S.string(sender)
        local group=channel and channels()[channel:lower()]
        if group then P.notePeer(group,sender) end
        P.receive(text, sender, channel)
        P.tick()
    else P.tick() end
end)
local accumulated = 0
frame:SetScript("OnUpdate", function(_, elapsed)
    accumulated = accumulated + elapsed
    if accumulated >= .25 then accumulated = 0; P.tick() end
end)
