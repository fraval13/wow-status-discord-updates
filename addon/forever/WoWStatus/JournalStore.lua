-- Persistent account log: its entries, what may be kept and relayed, and the
-- reactions friends whisper about them.
-- No server, remote code, executable serialization or arbitrary chat input.
-- WoWStatusJournal is one table filled by three files, loaded in this order:
-- JournalStore.lua (the log), JournalSync.lua (catch-up between members and its
-- wire format) and ActivityLogPage.lua (the Activity page). J.internal holds
-- what those three share with each other and nothing else should use (#230).
WoWStatusJournal = {}
local J, S, P = WoWStatusJournal, WoWStatusSafe, WoWStatusPopups
local T = WoWStatusLocale.T
local I = {}
J.internal = I
-- db, current, index and digests are mirrored in I (I.db ...) whenever they
-- are replaced, so the other two files always read the live tables.
local db, current, index, digests = nil,nil,{},{}
-- CAP bounds this account's own entries and, separately, received entries (#4).
local PREFIX, CAP, AGE, PAGE = "WoWStatusLog",2000,7*86400,6
I.PREFIX, I.CAP, I.AGE, I.PAGE = PREFIX, CAP, AGE, PAGE
local equipment = {}
local sharedKinds={introduction=true,level=true,loot=true,death=true,zone=true,quest=true,profession=true,
    raid=true,epicmount=true,recap=true,dungeon=true,mount=true,reputation=true,unlock=true,pvp=true,achievement=true,
    battleground=true}
-- An achievement entry's whitelisted ID (#165), or nil.
local function achievementID(e)
    return WoWStatusAchievements.id(e.achievement_id)
end
local fields={level="level",zone="zone",quest="quests",questprogress="quests",profession="professions",
    professionprogress="professions",equipment="gear"}
local function trim(text,limit)
    if type(text)~="string" then return "" end
    text=S.stripEscapes(text):gsub(S.CONTROL_OR_PIPE," ")
    return S.cut(text,limit)
end
local function ownName()
    return (P.ownName() or current.identity.name).."-"..S.stripSpace(WoWStatusAdapter.realmName() or current.identity.realm)
end
function J.eventID(sender,nonce)
    local key=P.senderKey(sender)
    if not key or type(nonce)~="string" or #nonce>64 or not nonce:match("^[%w%-]+$") then return nil end
    return WoWStatusAdapter.client_id..":"..key..":"..nonce
end
local function digest(id)
    local a,b,c=5381,2166136261,104729
    for i=1,#id do local byte=id:byte(i);a=(a*33+byte)%4294967296;b=(b*65599+byte)%4294967296;c=(c*131+byte)%4294967296 end
    return string.format("%08x%08x%06x",a,b,c%16777216)
end
-- An entry's ID never changes, so its digest is computed once.
local digestOf = setmetatable({}, {__mode="k"})
local function digestFor(e)
    local d=digestOf[e]
    if not d then d=digest(e.id);digestOf[e]=d end
    return d
end
local function groupMember(group)
    return current and WoWStatusGroups.selected(current)[group]
end
local function groupSince(group)
    local member=groupMember(group)
    return member and (WoWStatusGroups.historySince(group) or member.joined_at) or S.now()
end
local function peer(group,sender)
    return P.isPeer(group,P.senderKey(sender))
end
local function permitted(entry)
    if entry.kind=="questprogress" then return false end
    -- Private recaps retain empty group scope and belong to this account only.
    if entry.kind=="recap" and not next(entry.groups or {}) then
        if not entry.owner then return false end
        return WoWStatusSharing.ownerOf(db,entry)~=nil
    end
    if entry.kind=="quest" then
        local total=tonumber((entry.text or ""):match("^Completed (%d+) quests!$"))
        if not total or total<100 or total%100~=0 then return false end
    end
    if (entry.kind=="loot" or entry.kind=="equipment") and not WoWStatusLoot.allowed(current and current.settings,entry) then return false end
    if not entry.owner then return WoWStatusSharing.wants(current, entry.kind) end
    local owner=WoWStatusSharing.ownerOf(db,entry)
    if not owner or not owner.settings.enabled then return false end
    local kind=WoWStatusSharing.category(entry.kind)
    if entry.kind~="equipment" and not owner.settings.collection[kind] then return false end
    if fields[entry.kind] and not owner.settings.fields[fields[entry.kind]] then return false end
    return true
end
-- now: realm time, read once by callers that check the whole log.
local function relayable(entry,group,now)
    if entry.kind=="loot" and not (entry.text or ""):match("^Equipped ") then return false end
    if entry.legacy or entry.client~=WoWStatusAdapter.client_id or not sharedKinds[entry.kind] or not entry.groups or not entry.groups[group] or not permitted(entry) then return false end
    local member=groupMember(group)
    if not member or entry.at<groupSince(group) or entry.at<(now or S.now())-AGE then return false end
    if entry.owner then
        local owner=WoWStatusSharing.ownerOf(db,entry)
        if not owner or not owner.settings.in_game or owner.settings.in_game[WoWStatusSharing.category(entry.kind)]==false then return false end
        if entry.kind=="loot" and not WoWStatusLoot.allowed(owner.settings,entry) then return false end
    end
    return true
end
-- Never offer a text that updated peers would reject and report as invalid.
-- Privacy pruning keeps using relayable, so this never drops a group scope.
local function offerable(entry,group,now)
    if entry.kind=="achievement" and not achievementID(entry) then return false end
    return relayable(entry,group,now) and J.validText(entry.kind,entry.text,entry.level)
end
local function rebuild()
    index,digests={},{};I.index,I.digests=index,digests
    table.sort(db.journal.entries,function(a,b) if a.at==b.at then return a.id>b.id end return a.at>b.at end)
    -- Own and received entries are capped separately, newest kept, so received
    -- traffic can never evict this account's own history (#4).
    local private,own,received=0,0,0
    local kept,seen,dropped={},{},{}
    for _, e in ipairs(db.journal.entries) do
        local keep=false
        if not seen[e.id] then
            seen[e.id]=true
            local localOnly=e.owner and not next(e.groups or {})
            if localOnly then private=private+1 end
            if not (localOnly and private>1000) then
                if e.owner then own=own+1 else received=received+1 end
                keep=(e.owner and own or received)<=CAP
            end
        end
        if keep then kept[#kept+1]=e else dropped[#dropped+1]=e end
    end
    db.journal.entries=kept
    for _, e in ipairs(db.journal.entries) do index[e.id]=e;digests[digestFor(e)]=e end
    return dropped
end
-- t is full, or a live packet's cut of it: a prefix of full followed by "...".
local function cutOf(full,t)
    return t==full or (t:sub(-3)=="..." and #full>#t-3 and full:sub(1,#t-3)==t:sub(1,-4))
end
local function sameFacts(a,b)
    return a.kind==b.kind and P.senderKey(a.sender)==P.senderKey(b.sender) and a.at==b.at
end
-- Only the game authenticates a whisper's sender. A catch-up entry is a claim by
-- whoever passed it on (relay, or via when no relay is named), unless that was
-- its author. Live packets and this client's own data are authenticated.
local function relayed(e)
    return e.origin=="catchup" and P.senderKey(e.relay or e.via)~=P.senderKey(e.sender)
end
J.relayed=relayed
-- Another member's entry naming one of this account's characters as its sender.
local function ownCharacter(entry)
    if entry.owner then return false end
    local senderKey=P.senderKey(entry.sender)
    for _, c in pairs(db.characters or {}) do
        if c.identity.client==entry.client then
            for _, name in ipairs({P.characterName(c),c.identity.name.."-"..S.stripSpace(c.identity.realm)}) do
                if P.senderKey(name)==senderKey then return true end
            end
        end
    end
    return false
end
-- The Records page changes only when an entry it can show comes or goes, so a
-- catch-up of other entries skips its whole-log recount (#4).
local function recordsChange(entry,removed,dropped)
    local F=WoWStatusFirsts
    if not F.matters or F.matters(entry) or (removed and F.matters(removed)) then return true end
    for _, e in ipairs(dropped) do if F.matters(e) then return true end end
    return false
end
-- Counts changes to where friends were (a first visit or a death's zone came),
-- so "Where we are" redraws for them and for nothing else.
J.zoneRevision=0
-- Friends' entries new to the log since the Activity page was last opened, by
-- ID, for the minimap tooltip's count (#179). Kept only on this account. IDs
-- that leave the log are dropped at login and whenever they are counted.
-- Entries arriving while the page is open count too: its filters (today,
-- one person, a type) may not list them, and the line says "since opened".
local function markUnseen(entry)
    if entry.owner or entry.legacy or entry.kind=="recap" then return end
    db.journal.unseen[entry.id]=true
end
-- removed: an entry this one replaces, already taken out of the log.
local function insert(entry,removed)
    if entry.kind=="zone" or entry.kind=="death" then J.zoneRevision=J.zoneRevision+1 end
    WoWStatusFlavour.text(entry)
    table.insert(db.journal.entries,entry)
    local dropped=rebuild()
    if I.refresh then I.refresh() end
    if WoWStatusStatusLine then WoWStatusStatusLine.update() end
    if WoWStatusFirsts and recordsChange(entry,removed,dropped) then WoWStatusFirsts.update() end
    if WoWStatusStreaks then WoWStatusStreaks.noted(entry) end
    if WoWStatusBingo then WoWStatusBingo.update() end
end
-- Returns true when the entry is new to the log: a new ID, or one that replaces a
-- relay's claim with other content. False when it repeats a logged event or is refused.
local function add(entry)
    if not db or not entry.id or not permitted(entry) then return false end
    -- WoW Forever: an entry naming only a first name came from an older version.
    if not entry.owner and not P.fullName(entry.sender) then return false end
    entry.groups=entry.groups or {}
    local old=index[entry.id]
    if old and relayed(old) and not relayed(entry) then
        if ownCharacter(entry) then return false end
        -- An authenticated copy replaces a relay's claim on its ID, all fields
        -- included; the claim may even predate the event (issue #3). Queued sends
        -- of the claim stop, as J.tick checks the entry itself. It repeats the
        -- claim (a quiet popup) only when its text is the claim's or a live cut of
        -- it, so a "..." stub claim can't silence an update.
        local same=sameFacts(old,entry)
        if same and (cutOf(old.text,entry.text) or cutOf(entry.text,old.text)) then
            for group in pairs(old.groups) do entry.groups[group]=true end
        end
        for i,e in ipairs(db.journal.entries) do if e==old then table.remove(db.journal.entries,i);break end end
        local new=not (same and cutOf(old.text,entry.text))
        if new then markUnseen(entry) end
        insert(entry,old)
        return new
    end
    if old then
        if not sameFacts(old,entry) or not (cutOf(old.text,entry.text) or cutOf(entry.text,old.text)) then return false end
        if not old.owner then for group in pairs(entry.groups) do old.groups[group]=true end end
        -- A relay's copy never changes what this client saw live, wrote or got
        -- from the author; a live packet can be shorter than such a copy.
        if relayed(entry)==relayed(old) and #entry.text>#old.text then old.text=entry.text end
        if I.refresh then I.refresh() end
        return false
    end
    if ownCharacter(entry) then return false end
    markUnseen(entry)
    insert(entry)
    return true
end
function J.prepare(database)
    local wanted={}
    for _,entry in ipairs(database.journal and database.journal.entries or {}) do
        if entry.owner and entry.kind=="loot" and entry.quality and entry.quality>=3 and not entry.class_id then wanted[entry.id]=entry end
    end
    for _,c in pairs(database.characters or {}) do
        for _,event in ipairs(c.history and c.history.events or {}) do
            if event.kind=="loot" then
                local nonce=P.eventNonce(event)
                local name=P.characterName(c)
                local id=nonce and c.identity.client..":"..P.senderKey(name)..":"..nonce
                local entry=id and wanted[id]
                if entry and event.data.item then
                    WoWStatusLoot.capture(event.data.item,function(info)
                        entry.quality,entry.class_id,entry.equip_loc,entry.item_id=info.quality,info.class_id,info.equip_loc,info.item_id
                        if db==database and WoWStatusLoot.allowed(current.settings,entry) then add(entry) end
                    end)
                end
            end
        end
    end
end
function J.recordLocal(event,backfill)
    if not db or not event or (event.data and event.data.synthetic) or not sharedKinds[event.kind] then return end
    local loot=event.kind=="loot" and WoWStatusLoot.eventInfo(event.data)
    if event.kind=="loot" and not WoWStatusLoot.allowed(current.settings,loot) then return end
    -- An achievement this client cannot name has nothing to show (#165).
    if event.kind=="achievement" and not P.eventText(event) then return end
    local nonce=P.eventNonce(event)
    local id=nonce and J.eventID(ownName(),nonce) or ("archive:"..current.identity.client..":"..event.id)
    local groups={}
    if not backfill and P.canShare(current,event) and (event.kind~="loot" or WoWStatusLoot.allowed(current.settings,loot)) then
        for group in pairs(event.group_ids or {}) do if groupMember(group) then groups[group]=true end end
    end
    add({id=id,client=current.identity.client,sender=ownName(),owner=current.identity.guid,kind=event.kind,
        level=event.kind=="level" and event.data.level or nil,at=event.at,
        text=trim(event.kind=="level" and ("Reached level "..event.data.level.."!") or P.eventText(event) or event.kind,160),
        quality=loot and loot.quality,class_id=loot and loot.class_id,equip_loc=loot and loot.equip_loc,item_id=loot and loot.item_id,
        achievement_id=event.kind=="achievement" and achievementID(event.data) or nil,groups=groups,origin="mine"})
    if event.kind=="death" and not backfill then J.setDetails(id,event.data.zone,event.data.killer) end
    if loot and not backfill then J.setItem(id,J.itemString(event.data.item)) end
    if not backfill and event.kind~="death" and event.kind~="introduction" and WoWStatusFeatures.enabled("with") then
        J.setWith(id,WoWStatusRoster.companions(event.group_ids))
    end
end
-- The item string of a link ("item:16923:2564:0:..."), with its suffix and enchant.
function J.itemString(link)
    local text=S.string(link)
    local item=text and (text:match("|H(item:[%-%d:]+)|h") or text:match("^(item:[%-%d:]+)$"))
    return item and #item<=120 and item or nil
end
-- The full item of an armor entry, for its tooltip: own equips, and friends'
-- from a separate "I" message, which older versions ignore.
function J.setItem(id,item)
    item=J.itemString(item)
    if not db or type(id)~="string" or not item then return false end
    db.journal.details=type(db.journal.details)=="table" and db.journal.details or {}
    local details=db.journal.details
    if not details[id] then
        local count,oldest,oldestAt=0,nil,math.huge
        for key,value in pairs(details) do count=count+1;if (value.at or 0)<oldestAt then oldest,oldestAt=key,value.at or 0 end end
        if count>=300 and oldest then details[oldest]=nil end
        details[id]={at=S.now()}
    end
    details[id].item=item
    return true
end
WoWStatusFeatures.register("with", "Who you played with",
    "Your own log cards name the friends who were in your party at the milestone.")
-- Labs (#243): who from the group was in your party at one of your own
-- milestones, by entry ID, on this computer only. At most 300, oldest dropped.
function J.setWith(id,names)
    if not db or type(id)~="string" or type(names)~="table" or #names==0 then return false end
    db.journal.with=type(db.journal.with)=="table" and db.journal.with or {}
    local with=db.journal.with
    if not with[id] then
        local count,oldest,oldestAt=0,nil,math.huge
        for key,item in pairs(with) do count=count+1;if (item.at or 0)<oldestAt then oldest,oldestAt=key,item.at or 0 end end
        if count>=300 and oldest then with[oldest]=nil end
    end
    with[id]={names=table.concat(names,", "),at=S.now()}
    return true
end
-- " · with Fra" for an own entry that has companions, or "".
function J.withText(e)
    local with=db and type(db.journal.with)=="table" and type(e)=="table" and db.journal.with[e.id]
    if not with or not WoWStatusFeatures.enabled("with") or type(with.names)~="string" then return "" end
    return " · "..T("with").." "..with.names
end
-- Death details (zone, killer) by entry ID: this character's own deaths, and
-- friends' from a separate "K" message, which older versions ignore. Kept apart
-- from the entry, so details may arrive before or after it. At most 300.
function J.setDetails(id,zone,killer)
    if not db or type(id)~="string" then return false end
    local function clean(text)
        text=S.string(text)
        return text and #text<=48 and not text:find(S.CONTROL_OR_PIPE) and text or nil
    end
    zone,killer=clean(zone),clean(killer)
    if not zone and not killer then return false end
    db.journal.details=type(db.journal.details)=="table" and db.journal.details or {}
    local details=db.journal.details
    if not details[id] then
        local count,oldest,oldestAt=0,nil,math.huge
        for key,item in pairs(details) do count=count+1;if (item.at or 0)<oldestAt then oldest,oldestAt=key,item.at or 0 end end
        if count>=300 and oldest then details[oldest]=nil end
    end
    local kept=details[id] and details[id].item
    details[id]={zone=zone,killer=killer,item=kept,at=S.now()}
    if zone then J.zoneRevision=J.zoneRevision+1 end
    if I.refresh then I.refresh() end
    return true
end
-- The zone a first visit names ("Entered Duskwood"), or nil when the client
-- could not read it ("Entered a new zone") or the text is not one.
function J.zoneOf(e)
    local zone=type(e)=="table" and e.kind=="zone" and S.string(e.text) and S.trim(e.text:match("^Entered (.+)$") or "")
    if not zone or zone=="" or zone=="a new zone" or #zone>48 or zone:find(S.CONTROL_OR_PIPE) then return nil end
    return zone
end
function J.details(e)
    local details=db and type(db.journal.details)=="table" and db.journal.details
    return details and type(e)=="table" and details[e.id] or nil
end
-- "Died · Duskwood · killed by Defias Pillager" for a death with details.
function J.deathText(e)
    local text=T(e.text)
    local d=e.kind=="death" and J.details(e)
    if not d then return text end
    if d.zone then text=text.." · "..d.zone end
    if d.killer then text=text.." · "..T("killed by").." "..T(d.killer) end
    return text
end
function J.observe(kind,text,info)
    if kind=="questprogress" then return end
    if kind=="equipment" and not WoWStatusLoot.allowed(current and current.settings,info) then return end
    if not db or not current.settings.enabled or not fields[kind] or not current.settings.fields[fields[kind]] then return end
    local category=({questprogress="quest",professionprogress="profession"})[kind] or kind
    if kind~="equipment" and not current.settings.collection[category] then return end
    current.journal_sequence=(current.journal_sequence or 0)+1
    add({id="local:"..current.identity.client..":"..current.identity.guid..":"..current.epoch..":"..current.journal_sequence,
        client=current.identity.client,sender=ownName(),owner=current.identity.guid,kind=kind,at=S.now(),
        text=trim(text,160),quality=info and info.quality,class_id=info and info.class_id,equip_loc=info and info.equip_loc,item_id=info and info.item_id,groups={},origin="mine"})
end
function J.equipment(slot,item)
    if not slot or slot<1 or slot>19 then return end
    if item~=equipment[slot] then
        local info=WoWStatusLoot.info(item or equipment[slot])
        if info and WoWStatusLoot.allowed(current.settings,info) then
            J.observe("equipment",(item and "Equipped " or "Removed ")..info.name,info)
        end
        equipment[slot]=item
    end
end
-- Single profession skill points are not logged: a card for every point filled
-- the log (cooking especially). Learning a profession and title promotions are
-- still logged as milestones.
function J.professions() end
-- Level achievements that store the date they were earned. The level is
-- checked against the achievement's name, so a wrong or renamed ID is skipped.
local LEVEL_ACHIEVEMENTS={{6,10},{7,20},{8,30},{9,40},{10,50},{11,60},{12,70},{13,80},{4826,85},{6193,90}}
local function achievementDate(month,day,year)
    month,day,year=S.number(month),S.number(day),S.number(year)
    if not (month and day and year) or month<1 or month>12 or day<1 or day>31 then return nil end
    if year<100 then year=2000+year end
    if year<2004 then return nil end
    local at=S.timeOf({year=year,month=month,day=day,hour=12})
    if not at or at>S.now()+86400 then return nil end
    return at
end
local function ownLevel(character,level)
    for _, e in ipairs(db.journal.entries) do
        if e.owner==character.identity.guid and e.client==character.identity.client and e.kind=="level" and not e.imported
            and S.number(e.level)==level then return true end
    end
    for _, event in ipairs(character.history and character.history.events or {}) do
        if event.kind=="level" and event.data and event.data.level==level then return true end
    end
    return false
end
-- History from before installation: the level where tracking began (shown on
-- the Activity page, not logged) and, where the client has achievements, dated
-- level-ups up to that level. These stay in this account's log only: never
-- sent, offered to peers, announced or counted for medals.
function J.backfill(character,level)
    if not db or character~=current or not S.number(level) then return end
    local identity=character.identity
    local sender=ownName()
    if type(character.tracking_start)~="table" then
        local started=character.progress and character.progress.started_at or S.now()
        local lowest=level
        for _, event in ipairs(character.history and character.history.events or {}) do
            local reached=event.kind=="level" and not (event.data and event.data.synthetic) and S.number(event.data and event.data.level)
            if reached and reached-1<lowest then lowest=math.max(1,reached-1) end
        end
        for _, point in ipairs(character.history and character.history.tracking.points or {}) do
            if S.number(point.level) and point.level<lowest then lowest=point.level end
        end
        -- One second earlier, so the marker sorts before the first tracked entry.
        character.tracking_start={level=lowest,at=started-1}
    end
    local start=character.tracking_start
    if not GetAchievementInfo or not character.settings.enabled or not character.settings.fields.level
        or not character.settings.collection.level then return end
    for _, item in ipairs(LEVEL_ACHIEVEMENTS) do
        local id,reached=item[1],item[2]
        if reached<=start.level and not ownLevel(character,reached) then
            local ok,_,name,_,completed,month,day,year,_,_,_,_,_,mine=pcall(GetAchievementInfo,id)
            name=ok and S.string(name)
            if name and S.value(completed)==true and S.value(mine)~=false
                and (" "..name.." "):find("[^%d]"..reached.."[^%d]") then
                local at=achievementDate(month,day,year)
                if at then
                    add({id="achievement:"..identity.client..":"..identity.guid..":"..id,client=identity.client,sender=sender,
                        owner=identity.guid,kind="level",level=reached,at=at,text="Reached level "..reached.."!",
                        groups={},origin="mine",imported="achievement"})
                end
            end
        end
    end
end
local function liveEntry(item)
    local id=J.eventID(item.sender,item.nonce)
    if not id then return nil end
    local groups={}
    if item.group_id then groups[item.group_id]=true end
    return {id=id,client=WoWStatusAdapter.client_id,sender=item.sender,kind=item.kind or "level",level=item.level,
        text=trim(item.level and ("Reached level "..item.level.."!") or item.text or "",160),
        quality=item.quality,class_id=item.class_id,equip_loc=item.equip_loc,item_id=item.item_id,flavour=item.flavour,
        achievement_id=item.kind=="achievement" and achievementID(item) or nil,
        at=item.at or S.now(),groups=groups,origin="live"}
end
-- Logs a live update. Returns true when it is new to the log, which includes
-- replacing a relay's claim on its ID that has other content.
function J.received(item)
    if not db or item.preview then return false end
    local entry=liveEntry(item)
    return entry~=nil and add(entry)
end
-- This character's chat name was learnt (WoW Forever: "Edith Aateigen", where
-- UnitName gave "Edith"). Its own entries take that name, and IDs derived from
-- the old one change to the ID friends compute from the whisper sender, so their
-- copies match. Copies of this account's entries received from others are dropped.
function J.selfRenamed()
    if not db or not current then return end
    J.zoneRevision=J.zoneRevision+1
    local sender=ownName()
    local newKey=P.senderKey(sender)
    if not newKey then return end
    local kept={}
    for _, e in ipairs(db.journal.entries) do
        if e.owner==current.identity.guid and e.client==current.identity.client then
            local oldKey=P.senderKey(e.sender)
            if oldKey and oldKey~=newKey then
                local prefix=e.client..":"..oldKey..":"
                if e.id:sub(1,#prefix)==prefix then e.id=e.client..":"..newKey..":"..e.id:sub(#prefix+1);digestOf[e]=nil end
                e.sender=sender
            end
            kept[#kept+1]=e
        elseif not ownCharacter(e) then kept[#kept+1]=e end
    end
    db.journal.entries=kept;rebuild()
    if I.refresh then I.refresh() end
    if WoWStatusFirsts then WoWStatusFirsts.update() end
end
function J.shared(kind) return sharedKinds[kind]==true end
function J.entries() return db and db.journal.entries or {} end
function J.contains(id) return id and index[id]~=nil end
function J.entry(id) return id and index[id] or nil end
function J.redraw() if I.refresh then I.refresh() end end
function J.groupsChanged()
    if not db then return end
    J.zoneRevision=J.zoneRevision+1
    -- Every pull and queued send starts over, greeting the groups now joined (JournalSync.lua).
    I.syncGroupsChanged()
    local kept={}
    for _, e in ipairs(db.journal.entries) do
        for group in pairs(e.groups or {}) do if not groupMember(group) then e.groups[group]=nil end end
        if e.owner or next(e.groups or {}) then table.insert(kept,e) end
    end
    db.journal.entries=kept;rebuild()
    if I.refresh then I.refresh() end
end
function J.privacyChanged()
    if not db then return end
    J.zoneRevision=J.zoneRevision+1
    local kept,now={},S.now()
    for _, e in ipairs(db.journal.entries) do
        if permitted(e) then
            if e.owner then for g in pairs(e.groups) do if not relayable(e,g,now) then e.groups[g]=nil end end end
            table.insert(kept,e)
        end
    end
    db.journal.entries=kept;rebuild()
    -- Cancel queued payloads/session snapshots before they can disclose revoked data.
    I.syncPrivacyChanged()
    if I.refresh then I.refresh() end
end
function J.init(database,character)
    db,current=database,character;I.db,I.current=db,current
    db.journal=db.journal or {version=1,entries={}}
    if type(db.journal.unseen)~="table" then db.journal.unseen={} end
    index,digests={},{};I.index,I.digests=index,digests
    -- A new catch-up session for this database (JournalSync.lua).
    I.syncInit()
    equipment={}
    for slot=1,19 do equipment[slot]=WoWStatusAdapter.equipment(slot) end
    local kept={}
    for _,e in ipairs(db.journal.entries) do
        if type(e)=="table" and type(e.id)=="string" and type(e.at)=="number" and type(e.text)=="string" and permitted(e)
            and (e.owner or P.fullName(e.sender)) then e.groups=e.groups or {};kept[#kept+1]=e end
    end
    db.journal.entries=kept;rebuild();J.groupsChanged()
    local unseen={}
    for id,flag in pairs(db.journal.unseen) do if flag==true and index[id] then unseen[id]=true end end
    db.journal.unseen=unseen
    -- Once: remove the skill-point cards earlier versions logged.
    if not db.journal.profession_points_removed then
        local cleaned={}
        for _,e in ipairs(db.journal.entries) do if e.kind~="professionprogress" then cleaned[#cleaned+1]=e end end
        db.journal.entries=cleaned;rebuild()
        db.journal.profession_points_removed=true
    end
    db.journal.migrated=db.journal.migrated or {}
    local migrationKey=character.identity.client..":"..character.identity.guid
    if not db.journal.migrated[migrationKey] then
        local history=character.history and character.history.events or {}
        for i=math.max(1,#history-499),#history do J.recordLocal(history[i],true) end
        db.journal.migrated[migrationKey]=true
    end
    if not db.journal.imported_activity then
        for _, item in ipairs(db.popups and db.popups.activity or {}) do
            local text=trim(item.level and ("Reached level "..item.level.."!") or item.text or "",160)
            local groups={};if item.group_id and groupMember(item.group_id) then groups[item.group_id]=true end
            add({id="legacy:"..digest(item.sender..":"..item.at..":"..(item.kind or "level")..":"..text),
                client=character.identity.client,sender=item.sender,at=item.original_at or item.at,kind=item.kind or "level",
                level=item.level,text=text,groups=groups,legacy=true,origin="legacy"})
        end
        db.journal.imported_activity=true
    end
    local register=C_ChatInfo and C_ChatInfo.RegisterAddonMessagePrefix or RegisterAddonMessagePrefix
    if register then pcall(register,PREFIX) end
    if WoWStatusFirsts then WoWStatusFirsts.update() end
end
-- A friend muted with "Hide completely" (#169): their entries stay in the log
-- (and are relayed as before), but no page shows or counts them.
local function hiddenSender(entry)
    return not entry.owner and WoWStatusMutes~=nil and WoWStatusMutes.hidden(entry.sender)
end
function J.visible(entry) return db~=nil and (entry.sample==true or (permitted(entry) and not hiddenSender(entry))) end
-- Friends' newest entries (not recaps or previews), newest first, at most
-- limit of them, for the minimap tooltip (#179). The log is kept newest first.
function J.latestFriends(limit)
    local list={}
    for _,e in ipairs(J.entries()) do
        if #list>=limit then break end
        if not e.owner and e.kind~="recap" and J.visible(e) then list[#list+1]=e end
    end
    return list
end
-- How many friends' entries arrived since the Activity page was last opened,
-- leaving out anything muted, hidden or no longer shared.
function J.unseenCount()
    if not db then return 0 end
    local count=0
    for id in pairs(db.journal.unseen) do
        local e=index[id]
        if not e then db.journal.unseen[id]=nil
        elseif J.visible(e) then count=count+1 end
    end
    return count
end
-- Opening the Activity page sees everything new, as the tooltip line says;
-- not while the tour (#64) fills it with samples instead of the log.
function J.markSeen()
    if db and not (WoWStatusGuide and WoWStatusGuide.sampleEntries()) then db.journal.unseen={} end
end
-- A private recap has no group scopes and is never sent or offered to peers.
function J.recordRecap(character,at,text,flavour)
    if not db or type(text)~="string" or text=="" then return false end
    local identity=character.identity
    return add({id="recap:"..identity.client..":"..identity.guid..":"..at,client=identity.client,
        sender=P.characterName(character),owner=identity.guid,kind="recap",at=at,
        text=trim(text,160),flavour=flavour,groups={},origin="mine"})
end
-- Reaction whispers ("GZ!", "F", "Congrats!" ... from the buttons on friends'
-- notifications, English or Nynorsk) are linked to this character's matching
-- event of the last 15 minutes, and shown on its log card ("GZ! from Mira").
local REACTION_KINDS={["GZ!"]={level=true},["Eg ynskjer deg hjarteleg til lukke med det nye nivået!"]={level=true},["F"]={death=true},["Git Good"]={death=true},
    ["Eg tek av meg hjelmen og bøyer hovudet i sorg."]={death=true},["Øv deg litt meir, så døyr du kanskje sjeldnare!"]={death=true},
    ["Welcome!"]={introduction=true},["Velkomen!"]={introduction=true}}
local POSITIVE={profession=true,dungeon=true,raid=true,mount=true,epicmount=true,reputation=true,unlock=true,pvp=true,
    quest=true,loot=true,achievement=true}
local REACTION_WINDOW=900
function J.reaction(text,sender)
    text,sender=S.string(text),S.string(sender)
    if not db or not current or not text or not sender or #text>160 or P.isSelf(sender) then return false end
    local kinds,zone=REACTION_KINDS[text],text:match("^Enjoy (.+)!$") or text:match("^Kos deg i (.+)!$")
    if text=="Congrats!" or text=="Gratulerer!" then kinds=POSITIVE end
    -- "Congrats on the new gear!" and the like, in English or Nynorsk, for that kind only.
    for kind,congrats in pairs(P.CONGRATS or {}) do
        if text==congrats or text==WoWStatusLocale.NN[congrats] then kinds={[kind]=true} end
    end
    if text:match("^Congrats on level %d+!$") or text:match("^Gratulerer med nivå %d+!$") then kinds={level=true} end
    -- The random Nynorsk lines: GZ! for level-ups, F for deaths, "{zone}" lines for zones.
    local pools=WoWStatusLocale.POOLS or {}
    for _,line in ipairs(pools["GZ!"] or {}) do if text==line then kinds={level=true} end end
    for _,line in ipairs(pools.F or {}) do if text==line then kinds={death=true} end end
    for _,line in ipairs(pools.Enjoy or {}) do
        local pattern="^"..line:gsub("[%^%$%(%)%%%.%[%]%*%+%-%?]","%%%0"):gsub("{zone}","(.+)").."$"
        local found=text:match(pattern)
        if found then zone,kinds=found,{zone=true} end
    end
    -- A line in one of the reaction voices (any personality, either language).
    if not kinds and WoWStatusPersonalities and WoWStatusPersonalities.matchReaction then
        local key,value=WoWStatusPersonalities.matchReaction(text)
        if key=="gz" or key=="level" then kinds={level=true}
        elseif key=="f" or key=="gitgood" then kinds={death=true}
        elseif key=="welcome" then kinds={introduction=true}
        elseif key=="enjoy" then zone=value
        elseif key=="congrats" then kinds=POSITIVE
        elseif key and key:sub(1,9)=="congrats_" then kinds={[key:sub(10)]=true} end
    end
    if zone then kinds={zone=true} end
    if not kinds then return false end
    -- Only group members react through the buttons.
    local member=false
    for group in pairs(WoWStatusGroups.selected(current)) do if peer(group,sender) then member=true end end
    if not member then return false end
    -- Muted friends (#169) are never read aloud; a hidden one's reactions are
    -- kept but not shown (J.reactionsText), so unmuting brings them back.
    local mode=WoWStatusMutes and WoWStatusMutes.mode(sender) or "show"
    local now=S.now()
    for _,e in ipairs(db.journal.entries) do
        if e.owner==current.identity.guid and e.client==current.identity.client and kinds[e.kind]
            and now-(e.at or 0)<=REACTION_WINDOW and (not zone or e.text=="Entered "..zone) then
            e.reactions=type(e.reactions)=="table" and e.reactions or {}
            local key=P.senderKey(sender)
            local count=0
            for _ in pairs(e.reactions) do count=count+1 end
            if key and (e.reactions[key] or count<20) then
                e.reactions[key]={name=sender:match("^[^-]+") or sender,text=text,at=now}
                if I.refresh then I.refresh() end
                -- A voiced Nynorsk line is read aloud (Forever), within the listener's limits.
                -- Never in quiet hours (#180): someone may be asleep nearby.
                if WoWStatusVoices and mode=="show" and not WoWStatusPopups.quietHoursActive() then WoWStatusVoices.heard(text) end
                return true
            end
            return false
        end
    end
    return false
end
-- The words you whispered about a friend's entry, or nil.
function J.sentReaction(e)
    if type(e)~="table" then return nil end
    return S.string(e.whispered) or (S.string(e.reacted) and T(e.reacted)) or nil
end
-- "GZ! from Mira, Bob · F from Eve", in the order they arrived.
function J.reactionsText(e)
    if type(e)~="table" or type(e.reactions)~="table" then return nil end
    local list={}
    for key,r in pairs(e.reactions) do
        if not (WoWStatusMutes and WoWStatusMutes.hidden(key)) then list[#list+1]=r end
    end
    if #list==0 then return nil end
    table.sort(list,function(a,b) return (a.at or 0)<(b.at or 0) end)
    local byText,order={},{}
    for _,r in ipairs(list) do
        if not byText[r.text] then byText[r.text]={};order[#order+1]=r.text end
        table.insert(byText[r.text],(tostring(r.name):gsub("|","||")))
    end
    local parts={}
    for _,text in ipairs(order) do
        parts[#parts+1]=T(text):gsub("|","||").." "..T("from").." "..table.concat(byText[text],", ")
    end
    return table.concat(parts," · ")
end
-- What JournalSync.lua and ActivityLogPage.lua use from the log.
I.sharedKinds, I.achievementID, I.digest, I.digestFor = sharedKinds, achievementID, digest, digestFor
I.groupMember, I.groupSince, I.peer, I.offerable, I.relayed, I.add =
    groupMember, groupSince, peer, offerable, relayed, add
