-- Persistent account log and bounded, group-scoped peer anti-entropy.
-- No server, remote code, executable serialization or arbitrary chat input.
WoWStatusJournal = {}
local J, S, P = WoWStatusJournal, WoWStatusSafe, WoWStatusPopups
local T = WoWStatusLocale.T
local db, current, index, digests = nil,nil,{},{}
local requests, sessions, sendQueue, cursors, rates = {},{},{},{},{}
local serial,lastSend=0,0
-- The game allows each prefix 10 addon messages, regained at 1 a second, and
-- returns a throttle result past that; whispers outside instances are exempt.
-- In an instance the log waits for that allowance, and everywhere it checks
-- the result: a throttled packet stays first in the queue and is sent again
-- after a pause (#9).
local ALLOWANCE=10
local allowance,allowanceAt,holdUntil,pacing=ALLOWANCE,0,0,{}
local jobs,queuedJobs,contacted,hellos,seenHello={},{},{},{},{}
local loginUntil,loginNonce=0,nil
local pumpJobs
-- CAP bounds this account's own entries and, separately, received entries (#4).
local PREFIX, CAP, AGE, PAGE = "WoWStatusLog",2000,7*86400,6
-- Catch-up one member can deliver per login session: at most RELAY_CAP new
-- entries fetched from it, at most SENDER_CAP of them naming one other member (#4).
local RELAY_CAP, SENDER_CAP = 300, 100
-- A member's hello starts a pull at most once per HELLO_INTERVAL seconds of game
-- uptime in one group; a newer hello within it waits for the interval and for
-- any running pull from that member to end (#4).
local HELLO_INTERVAL = 600
local budgets = {}
local panel, refresh
local equipment, lastQuery = {}, {}
local sharedKinds={introduction=true,level=true,loot=true,death=true,zone=true,quest=true,profession=true,
    raid=true,epicmount=true,recap=true,dungeon=true,mount=true,reputation=true,unlock=true,pvp=true}
local fields={level="level",zone="zone",quest="quests",questprogress="quests",profession="professions",
    professionprogress="professions",equipment="gear"}
local function trim(text,limit)
    if type(text)~="string" then return "" end
    text=S.stripEscapes(text):gsub(S.CONTROL_OR_PIPE," ")
    if #text>limit then text=text:sub(1,limit-3):gsub("[\194-\244][\128-\191]*$","").."..." end
    return text
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
        for _, c in pairs(db.characters or {}) do
            if c.identity.guid==entry.owner and c.identity.client==entry.client then return true end
        end
        return false
    end
    if entry.kind=="quest" then
        local total=tonumber((entry.text or ""):match("^Completed (%d+) quests!$"))
        if not total or total<100 or total%100~=0 then return false end
    end
    if (entry.kind=="loot" or entry.kind=="equipment") and not WoWStatusLoot.allowed(current and current.settings,entry) then return false end
    if not entry.owner then return true end
    local owner
    for _, c in pairs(db.characters or {}) do if c.identity.guid==entry.owner and c.identity.client==entry.client then owner=c;break end end
    if not owner or not owner.settings.enabled then return false end
    local kind=({raid="dungeon",epicmount="mount",questprogress="quest",professionprogress="profession"})[entry.kind] or entry.kind
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
        local owner
        for _, c in pairs(db.characters) do if c.identity.guid==entry.owner and c.identity.client==entry.client then owner=c;break end end
        if not owner or not owner.settings.in_game or owner.settings.in_game[({raid="dungeon",epicmount="mount"})[entry.kind] or entry.kind]==false then return false end
        if entry.kind=="loot" and not WoWStatusLoot.allowed(owner.settings,entry) then return false end
    end
    return true
end
-- Never offer a text that updated peers would reject and report as invalid.
-- Privacy pruning keeps using relayable, so this never drops a group scope.
local function offerable(entry,group,now)
    return relayable(entry,group,now) and J.validText(entry.kind,entry.text,entry.level)
end
local function rebuild()
    index,digests={},{}
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
-- removed: an entry this one replaces, already taken out of the log.
local function insert(entry,removed)
    WoWStatusFlavour.text(entry)
    table.insert(db.journal.entries,entry)
    local dropped=rebuild()
    if refresh then refresh() end
    if WoWStatusStatusLine then WoWStatusStatusLine.update() end
    if WoWStatusFirsts and recordsChange(entry,removed,dropped) then WoWStatusFirsts.update() end
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
        insert(entry,old)
        return not (same and cutOf(old.text,entry.text))
    end
    if old then
        if not sameFacts(old,entry) or not (cutOf(old.text,entry.text) or cutOf(entry.text,old.text)) then return false end
        if not old.owner then for group in pairs(entry.groups) do old.groups[group]=true end end
        -- A relay's copy never changes what this client saw live, wrote or got
        -- from the author; a live packet can be shorter than such a copy.
        if relayed(entry)==relayed(old) and #entry.text>#old.text then old.text=entry.text end
        if refresh then refresh() end
        return false
    end
    if ownCharacter(entry) then return false end
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
    local nonce=P.eventNonce(event)
    local id=nonce and J.eventID(ownName(),nonce) or ("archive:"..current.identity.client..":"..event.id)
    local groups={}
    if not backfill and P.canShare(current,event) and (event.kind~="loot" or WoWStatusLoot.allowed(current.settings,loot)) then
        for group in pairs(event.group_ids or {}) do if groupMember(group) then groups[group]=true end end
    end
    add({id=id,client=current.identity.client,sender=ownName(),owner=current.identity.guid,kind=event.kind,
        level=event.kind=="level" and event.data.level or nil,at=event.at,
        text=trim(event.kind=="level" and ("Reached level "..event.data.level.."!") or P.eventText(event) or event.kind,160),
        quality=loot and loot.quality,class_id=loot and loot.class_id,equip_loc=loot and loot.equip_loc,item_id=loot and loot.item_id,groups=groups,origin="mine"})
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
    local ok,at=pcall(time,{year=year,month=month,day=day,hour=12})
    at=ok and S.number(at)
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
    if refresh then refresh() end
    if WoWStatusFirsts then WoWStatusFirsts.update() end
end
function J.shared(kind) return sharedKinds[kind]==true end
function J.entries() return db and db.journal.entries or {} end
function J.contains(id) return id and index[id]~=nil end
function J.groupsChanged()
    if not db then return end
    requests,sessions,sendQueue,cursors={},{},{},{}
    local kept={}
    for _, e in ipairs(db.journal.entries) do
        for group in pairs(e.groups or {}) do if not groupMember(group) then e.groups[group]=nil end end
        if e.owner or next(e.groups or {}) then table.insert(kept,e) end
    end
    db.journal.entries=kept;rebuild()
    jobs,queuedJobs,contacted,hellos={},{},{},{};loginUntil=time()+60
    if refresh then refresh() end
end
function J.privacyChanged()
    if not db then return end
    local kept,now={},S.now()
    for _, e in ipairs(db.journal.entries) do
        if permitted(e) then
            if e.owner then for g in pairs(e.groups) do if not relayable(e,g,now) then e.groups[g]=nil end end end
            table.insert(kept,e)
        end
    end
    db.journal.entries=kept;rebuild()
    -- Cancel queued payloads/session snapshots before they can disclose revoked data.
    requests,sessions,sendQueue,jobs,queuedJobs={},{},{},{},{}
    if refresh then refresh() end
end
local function pack(e)
    local values={e.id,e.client,e.sender,tostring(e.at),e.kind,e.level and tostring(e.level) or "",e.text,e.quality and tostring(e.quality) or "",e.class_id and tostring(e.class_id) or "",e.equip_loc or "",e.item_id and tostring(e.item_id) or ""}
    local parts={}
    for _, value in ipairs(values) do parts[#parts+1]=#value..":"..value end
    return table.concat(parts)
end
local function unpackEntry(text)
    if #text>1024 then return nil,"invalid" end
    local values,pos={},1
    for _=1,11 do
        local first,last,number=text:find("^(%d+):",pos)
        if not first or #number>4 then return nil,"invalid" end
        local count=tonumber(number)
        if count>300 or last+count>#text then return nil,"invalid" end
        values[#values+1]=text:sub(last+1,last+count);pos=last+count+1
    end
    if pos~=#text+1 then return nil,"invalid" end
    local id,client,sender,at,kind,level,detail=values[1],values[2],values[3],tonumber(values[4]),values[5],values[6],values[7]
    -- Version differences and stale history are ordinary drops, never accusations.
    if client~=WoWStatusAdapter.client_id or not sharedKinds[kind] then return nil end
    if #id>220 or #sender>120 or not P.senderKey(sender) or not at or at~=math.floor(at)
        or #detail>160 or detail:find(S.CONTROL_OR_PIPE) then return nil,"invalid" end
    if S.outside(at,AGE,300) then return nil end
    local prefix=client..":"..P.senderKey(sender)..":"
    if id:sub(1,#prefix)~=prefix or not id:sub(#prefix+1):match("^[%w%-]+$") or #id-#prefix>64 then return nil,"invalid" end
    if kind=="level" then
        level=tonumber(level)
        if not level or level~=math.floor(level) or level<2 or level>WoWStatusAdapter.max_level then return nil,"invalid" end
    elseif level~="" then return nil,"invalid" else level=nil end
    if not J.validText(kind,detail,level) then return nil,"invalid" end
    local e={id=id,client=client,sender=sender,at=at,kind=kind,level=level,text=detail,groups={},origin="catchup",
        quality=tonumber(values[8]),class_id=tonumber(values[9]),equip_loc=values[10],item_id=tonumber(values[11])}
    if kind=="loot" and (not detail:match("^Equipped ") or not e.item_id or not WoWStatusLoot.allowed(current.settings,e)) then return nil end
    if kind~="loot" and (values[8]~="" or values[9]~="" or values[10]~="" or values[11]~="") then return nil end
    return e
end
-- entry: the log entry a D/V packet carries; it is sent only while still logged.
local function queue(group,target,body,entry,expires)
    local text="J2 "..group.." "..body
    if #text>243 or #sendQueue>=512 then return false end
    sendQueue[#sendQueue+1]={group=group,target=target,text=text,entry=entry,expires=expires,query=body:match("^Q ([%w%-]+)")}
    return true
end
local function token()
    serial=serial+1;db.journal.request_serial=serial;return time().."-"..serial
end
-- A template's name slot carries the sender's own localized game name (zone,
-- item, mount, faction, spell, PvP rank). A receiver on another client language
-- cannot check it, so it only has to be non-blank.
local function named(detail,prefix)
    return detail:sub(1,#prefix)==prefix and detail:find(S.NONSPACE,#prefix+1)~=nil
end
local PROFESSION_RANKS={"Apprentice","Journeyman","Expert","Artisan","Master","New profession rank"}
-- "<profession>: <rank> (<max> max)". A long localized profession name can push
-- the suffix past the 48-byte packet limit; the sender then cuts it and appends
-- "...", so a cut text only has to be a prefix of a valid suffix. The cut keeps at
-- least 41 bytes (48 minus "..." minus one 4-byte character), so a short text
-- ending in "..." was never cut.
local function rankUp(detail)
    local rest=detail:match("^"..S.NONSPACE..".-: (.+)$")
    if not rest then return false end
    local cut=#detail>=44 and detail:sub(-3)=="..." and rest:sub(1,-4)
    for _,rank in ipairs(PROFESSION_RANKS) do
        local head=rank.." ("
        if rest:sub(1,#head)==head and rest:sub(#head+1):match("^[%d?]+ max%)$") then return true end
        if cut then
            if #cut<=#head then
                if head:sub(1,#cut)==cut then return true end
            elseif cut:sub(1,#head)==head then
                local tail=cut:sub(#head+1)
                if tail:match("^[%d?]*$") or tail:match("^[%d?]+ m?a?x?$") then return true end
            end
        end
    end
    return false
end
-- Fixed-format facts must not become arbitrary free-text announcements: every
-- shared kind matches only the texts this addon itself produces (P.eventText,
-- Milestones, the adapter's pvpText and the loot/dungeon packet conversions).
-- Plausible forged gameplay cannot be authenticated by a peer-only addon.
function J.validText(kind,detail,level)
    if type(detail)~="string" then return false end
    if kind=="level" then return detail=="Reached level "..tostring(level).."!" end
    if kind=="introduction" then return detail=="Joined the group" or detail=="Joined the WoW Status group" end
    if kind=="death" then return detail=="Died" or detail:match("^Total deaths: %d+$")~=nil end
    if kind=="quest" then return detail:match("^Completed %d+ quests!$")~=nil end
    if kind=="zone" then return named(detail,"Entered ") end
    if kind=="profession" then return named(detail,"Learned ") or rankUp(detail) end
    -- Local logs also keep "Looted"; only "Equipped" is ever shared or shown.
    if kind=="loot" then return named(detail,"Equipped ") or named(detail,"Looted ") end
    if kind=="dungeon" then return named(detail,"First clear: ") end
    if kind=="raid" then return named(detail,"First raid boss: ") end
    if kind=="epicmount" then return named(detail,"First epic mount: ") end
    if kind=="recap" then return WoWStatusRecaps and WoWStatusRecaps.validShared(detail) or false end
    if kind=="mount" then return detail=="First mount ride recorded!" or named(detail,"First mount: ") end
    if kind=="reputation" then
        return named(detail,"Honored with ") or named(detail,"Revered with ") or named(detail,"Exalted with ")
    end
    if kind=="unlock" then return named(detail,"Unlocked ") end
    if kind=="pvp" then
        -- Sender and receiver run the same edition, so the adapter decides the form.
        if WoWStatusAdapter.pvpText then
            local rank=tonumber(detail:match("^Reached honor level ([1-9]%d*)$"))
            return rank~=nil and rank<=(WoWStatusAdapter.max_pvp_rank or 0)
        end
        return named(detail,"Promoted to ")
    end
    return false
end
-- Invalid log data is dropped without a word. The "is a really bad boy" warning
-- popup and its group report ("W") were removed: different versions validate a
-- few texts differently, and the warning wrongly accused players in live play.
function J.reportInvalid() return false end
local function lootMask()
    local rarities=current.settings.loot_rarities or {rare=true,epic=true,legendary=true}
    return (rarities.rare and 1 or 0)+(rarities.epic and 2 or 0)+(rarities.legendary and 4 or 0)
end
local function requestPage(group,target,offset,pages,retries)
    local t=token()
    local member=groupMember(group)
    if not member then return end
    -- Never ahead of realm time: a responder drops cutoffs over 300 s ahead.
    local now=S.now()
    local cutoff=math.min(math.max(groupSince(group),now-AGE),now)
    requests[t]={group=group,target=target,key=P.senderKey(target),at=time(),offset=offset,pages=pages or 0,cutoff=cutoff,pending={},parts={},via={},retries=retries or 0}
    queue(group,target,"Q "..t.." "..offset.." "..cutoff.." "..lootMask())
end
-- What one member (by sender key) has delivered by catch-up this session:
-- the new entries fetched from it (each counted once) and per-sender claims.
local function budget(key)
    local b=budgets[key]
    if not b then b={fetched=0,seen={},claims={}};budgets[key]=b end
    return b
end
local function advance(t)
    local r=requests[t]
    if not r or not r.nextOffset or next(r.pending) then return end
    requests[t]=nil
    local key=r.group..":"..r.key
    -- Paging continues past a spent share: later pages can still hold free
    -- fetches, such as an author's own copy replacing a relay's claim (#3).
    if r.more and r.pages<math.ceil(CAP/PAGE) then
        cursors[key]=r.nextOffset
        requestPage(r.group,r.target,r.nextOffset,r.pages+1,r.retries)
    else
        -- The next pull starts from the newest entries again, also after the page
        -- limit: a responder can offer 2*CAP, but entries older than the newest
        -- CAP or so would not outlast this log's own received cap.
        cursors[key]=0
        if pumpJobs then pumpJobs() end
    end
end
-- A requested entry is done, stored or dropped; the page advances once all are.
local function finish(r,t,d)
    r.pending[d]=nil;r.parts[d]=nil;r.via[d]=nil;advance(t)
end
-- Whether a pull from this member in this group is queued or running.
local function pulling(group,key)
    if queuedJobs[group..":"..key] then return true end
    for _,r in pairs(requests) do if r.group==group and r.key==key then return true end end
    return false
end
local function enqueueJob(group,target,retries)
    if pulling(group,P.senderKey(target)) or #jobs>=512 then return end
    jobs[#jobs+1]={group=group,target=target,retries=retries or 0};queuedJobs[group..":"..P.senderKey(target)]=true
end
pumpJobs=function()
    local active=0;for _ in pairs(requests) do active=active+1 end
    while active<2 and #jobs>0 do
        local job=table.remove(jobs,1)
        local key=job.group..":"..P.senderKey(job.target);queuedJobs[key]=nil
        if groupMember(job.group) and peer(job.group,job.target) then
            requestPage(job.group,job.target,cursors[key] or 0,0,job.retries);active=active+1
        end
    end
end
-- Discovery is bounded to login/group-setup time. A login hello also makes an
-- already-online peer pull from the arriving client's saved copy, in reverse.
-- The Sync button: greet everyone online again, as at login, with a new nonce.
-- Members still start a pull at most once per HELLO_INTERVAL (#4).
function J.syncNow()
    if not db then return false end
    contacted,loginUntil,loginNonce={},time()+60,token()
    J.sync()
    return true
end
function J.sync()
    if not db then return end
    if time()<=loginUntil then
        local groups={};for g in pairs(WoWStatusGroups.selected(current)) do groups[#groups+1]=g end;table.sort(groups)
        for _,group in ipairs(groups) do
            local peers=P.peers(group);table.sort(peers)
            for _,target in ipairs(peers) do
                local key=group..":"..P.senderKey(target)
                if not contacted[key] and #hellos<512 then
                    contacted[key]=true;hellos[#hellos+1]={group=group,target=target}
                end
            end
        end
    end
    if #hellos>0 and #sendQueue<32 then
        local hello=table.remove(hellos,1)
        if groupMember(hello.group) and peer(hello.group,hello.target) then
            queue(hello.group,hello.target,"H "..loginNonce.." "..WoWStatusAdapter.client_id)
            enqueueJob(hello.group,hello.target)
        end
    end
    pumpJobs()
end
function J.receive(message,sender,distribution)
    if not db or distribution~="WHISPER" or type(message)~="string" or #message>243 then return false end
    local group,op,t,body=message:match("^J2 ([a-f0-9]+) (%u) ([%w%-]+) (.*)$")
    if not group or not WoWStatusGroups.valid(group) or not groupMember(group) or #t>32 or not peer(group,sender) then return false end
    local key=P.senderKey(sender)
    -- Reports from older versions are ignored; nothing is shown for them.
    if op=="W" then return false end
    if op=="H" then
        if body~=WoWStatusAdapter.client_id then return false end
        local helloKey=group..":"..key
        local last=seenHello[helloKey]
        if last and last.nonce==t then return true end
        -- A new hello from the same member and group starts a pull only so often.
        -- Within the interval it waits, and J.tick starts one pull later (#4).
        -- Game uptime, unlike time(), can't jump when the PC clock is changed.
        local uptime=GetTime and GetTime() or time()
        if last and uptime-last.at<HELLO_INTERVAL then
            last.nonce,last.waiting=t,sender;return false
        end
        seenHello[helloKey]={nonce=t,at=uptime,group=group};enqueueJob(group,sender);return true
    end
    if op=="Q" then
        local offset,cutoff,mask=body:match("^(%d+) (%d+) ([0-7])$")
        offset,cutoff,mask=tonumber(offset),tonumber(cutoff),tonumber(mask)
        -- Own and received entries are capped separately, so up to 2*CAP are offered.
        if not offset or offset>2*CAP or not cutoff or S.outside(cutoff,math.huge,300) then return false end
        local rateKey=group..":"..key
        if rates[rateKey] and time()-rates[rateKey]<2 then return false end
        rates[rateKey]=time()
        for sessionKey,session in pairs(sessions) do
            if session.group==group and session.key==key then sessions[sessionKey]=nil end
        end
        local n=0;for _ in pairs(sessions) do n=n+1 end;if n>=32 then return false end
        local now=S.now()
        cutoff=math.max(cutoff,now-AGE,groupSince(group))
        local eligible={}
        for _,e in ipairs(db.journal.entries) do
            local weight=({[3]=1,[4]=2,[5]=4})[e.quality]
            local wanted=e.kind~="loot" or (weight and math.floor(mask/weight)%2==1)
            if wanted and e.at>=cutoff and offerable(e,group,now) then eligible[#eligible+1]=e end
        end
        local offer,list={},{}
        for i=offset+1,math.min(offset+PAGE,#eligible) do local d=digestFor(eligible[i]);offer[d]=eligible[i].id;list[#list+1]=d end
        local cursor=math.min(offset+PAGE,#eligible)
        sessions[group..":"..key..":"..t]={at=time(),offer=offer,used=false,group=group,key=key}
        queue(group,sender,"I "..t.." "..cursor.." "..(cursor<#eligible and "1" or "0").." "..(#list>0 and table.concat(list,",") or "-"))
        return true
    end
    local r=requests[t]
    if op=="I" then
        if not r or r.group~=group or r.key~=key or r.inventory then return false end
        local offset,more,list=body:match("^(%d+) ([01]) ([a-f0-9,%-]+)$")
        offset=tonumber(offset)
        if not offset or offset<r.offset or offset>r.offset+PAGE then return false end
        local wanted,charged,seen,n={},{},{},0
        local spent=budget(key)
        if list~="-" then
            for d in list:gmatch("[^,]+") do
                n=n+1
                if #d~=22 or seen[d] or n>PAGE then return false end
                seen[d]=true
                local existing=digests[d]
                if not existing then
                    -- A new entry uses this member's share for the session once, even
                    -- if fetched again for another group or a retry. Past the share,
                    -- fetch no more new entries from it this session (#4).
                    if spent.seen[d] then wanted[#wanted+1]=d
                    elseif spent.fetched+#charged<RELAY_CAP then wanted[#wanted+1]=d;charged[#charged+1]=d end
                -- Also fetch a logged entry for this group's scope, or the author's own
                -- copy of an entry only a relay vouched for; neither adds an entry.
                elseif not existing.groups[group] or (relayed(existing) and P.senderKey(existing.sender)==key) then
                    wanted[#wanted+1]=d
                end
            end
        end
        r.inventory=true;r.nextOffset=offset;r.more=more=="1"
        if r.more and offset<=r.offset then return false end
        for _, d in ipairs(charged) do spent.seen[d]=true end
        spent.fetched=spent.fetched+#charged
        for _, d in ipairs(wanted) do r.pending[d]=true end
        if #wanted>0 then queue(group,sender,"G "..t.." "..table.concat(wanted,",")) end
        advance(t);return true
    elseif op=="G" then
        local session=sessions[group..":"..key..":"..t]
        if not session or session.used or time()-session.at>120 or not body:match("^[a-f0-9,]+$") then return false end
        local ids={};for d in body:gmatch("[^,]+") do if #d~=22 or not session.offer[d] or #ids>=PAGE then return false end;ids[#ids+1]=d end
        session.used=true
        for _, d in ipairs(ids) do
            local e=index[session.offer[d]]
            if e and offerable(e,group) then
                -- For an entry this client caught up itself, name the member it came
                -- from (checked by this client's game), so provenance survives the
                -- next hop. Never forward an unchecked via claim. Older clients ignore V.
                local from=e.origin=="catchup" and (e.relay or e.via)
                if from then queue(group,sender,"V "..t.." "..d.." "..from,e) end
                local encoded=pack(e):gsub(".",function(c) return string.format("%02x",c:byte()) end)
                local total=math.ceil(#encoded/140)
                for part=1,total do
                    queue(group,sender,"D "..t.." "..d.." "..part.."/"..total.." "..encoded:sub((part-1)*140+1,part*140),e)
                end
            end
        end
        return true
    elseif op=="V" then
        if not r or r.group~=group or r.key~=key then return false end
        local d,from=body:match("^([a-f0-9]+) ("..S.NONSPACE.."+)$")
        if not d or #d~=22 or not r.pending[d] or not P.senderKey(from) then return false end
        r.via[d]=from
        return true
    elseif op=="D" then
        if not r or r.group~=group or r.key~=key then return false end
        local d,part,total,data=body:match("^([a-f0-9]+) (%d+)/(%d+) ([a-f0-9]+)$")
        part,total=tonumber(part),tonumber(total)
        if not d or #d~=22 or not r.pending[d] or not part or not total or total<1 or total>16 or part<1 or part>total or #data>140 or #data%2~=0 then return false end
        local chunks=r.parts[d] or {total=total};r.parts[d]=chunks
        if chunks.total~=total or (chunks[part] and chunks[part]~=data) then J.reportInvalid(group,sender);return false end
        chunks[part]=data
        for i=1,total do if not chunks[i] then return true end end
        local decoded=table.concat(chunks):gsub("..",function(pair) return string.char(tonumber(pair,16)) end)
        local e,problem=unpackEntry(decoded)
        -- A dropped entry still finishes, so one bad entry can't stall the pull.
        if not e then if problem=="invalid" then J.reportInvalid(group,sender) end;finish(r,t,d);return false end
        if digest(e.id)~=d then J.reportInvalid(group,sender);finish(r,t,d);return false end
        if e.at<r.cutoff then finish(r,t,d);return false end
        -- A member adds at most SENDER_CAP new entries naming one other member per
        -- session; its own entries count only toward RELAY_CAP (#4).
        local claimed,claims=P.senderKey(e.sender),budget(key).claims
        if claimed~=key and not index[e.id] then
            if (claims[claimed] or 0)>=SENDER_CAP then finish(r,t,d);return false end
            claims[claimed]=(claims[claimed] or 0)+1
        end
        -- Forwarded identities are claims by the relay, not authenticated origins.
        -- via: who the sender says it got the entry from (the sender itself if it
        -- does not say). relay: the sender, checked by the game, when that differs.
        e.groups[group]=true;e.via=sender
        local from=r.via[d]
        -- Keep the game's spelling of the sender's name, even if V names it.
        if from and P.senderKey(from)~=key then e.via,e.relay=from,sender end
        add(e);finish(r,t,d)
        return true
    end
    return false
end
function J.tick()
    if not db then return end
    local now=time()
    for t,r in pairs(requests) do
        if now-r.at>(r.sent and 120 or 300) then
            requests[t]=nil
            if r.retries<1 then enqueueJob(r.group,r.target,r.retries+1) end
        end
    end
    for k,s in pairs(sessions) do if now-s.at>120 then sessions[k]=nil end end
    local uptime=GetTime and GetTime() or now
    for _,h in pairs(seenHello) do
        if h.waiting and uptime-h.at>=HELLO_INTERVAL and not pulling(h.group,P.senderKey(h.waiting)) then
            enqueueJob(h.group,h.waiting);h.at,h.waiting=uptime,nil
        end
    end
    for k,at in pairs(rates) do if now-at>120 then rates[k]=nil end end
    -- Log sync is not held for combat: addon whispers are not combat-protected,
    -- and WoW Forever can report a UI lockdown outside combat, which stopped sync.
    -- Real messaging restrictions are still checked through chatRestricted().
    J.sync()
    local clock=GetTime and GetTime() or now
    allowance=math.min(ALLOWANCE,allowance+math.max(0,clock-allowanceAt));allowanceAt=clock
    if clock<holdUntil or clock-lastSend<.5 or #sendQueue==0 or WoWStatusAdapter.chatRestricted() then return end
    if allowance<1 and S.call(IsInInstance) then return end
    local item=sendQueue[1]
    local queryKey=item.group..":"..P.senderKey(item.target)
    if item.query and lastQuery[queryKey] and clock-lastQuery[queryKey]<2.1 then return end
    -- A query whose request already timed out is not sent: its retry is queued.
    local drop=(item.expires and (now>item.expires or not current.settings.enabled))
        or (item.query and not requests[item.query])
        or not groupMember(item.group) or not peer(item.group,item.target)
        or (item.entry and (index[item.entry.id]~=item.entry or not offerable(item.entry,item.group)))
    local send=C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
    if drop or not send then table.remove(sendQueue,1);return end
    lastSend,allowance=clock,math.max(0,allowance-1)
    P.whispered(item.target)
    local result=P.sendResult(pcall(send,PREFIX,item.text,"WHISPER",item.target))
    local wait=P.retryWait(result,item,pacing,clock)
    if wait then allowance,holdUntil=0,clock+wait;return end
    table.remove(sendQueue,1)
    if item.query then
        lastQuery[queryKey]=clock
        if requests[item.query] then requests[item.query].at=now;requests[item.query].sent=true end
    end
end
function J.init(database,character)
    db,current=database,character
    db.journal=db.journal or {version=1,entries={}}
    index,digests={},{};requests,sessions,sendQueue,cursors,rates={},{},{},{},{}
    serial=db.journal.request_serial or 0
    equipment,lastQuery={},{}
    for slot=1,19 do equipment[slot]=WoWStatusAdapter.equipment(slot) end
    lastSend,allowance,allowanceAt,holdUntil,pacing=0,ALLOWANCE,0,0,{};loginNonce=token()
    jobs,queuedJobs,contacted,hellos,seenHello,budgets={},{},{},{},{},{}
    local kept={}
    for _,e in ipairs(db.journal.entries) do
        if type(e)=="table" and type(e.id)=="string" and type(e.at)=="number" and type(e.text)=="string" and permitted(e)
            and (e.owner or P.fullName(e.sender)) then e.groups=e.groups or {};kept[#kept+1]=e end
    end
    db.journal.entries=kept;rebuild();J.groupsChanged();loginUntil=time()+60
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
local function label(parent,font,x,y,width)
    local f=parent:CreateFontString(nil,"OVERLAY",font);f:SetPoint("TOPLEFT",x,y);f:SetWidth(width);f:SetJustifyH("LEFT");return f
end
-- The tour (#64) shows sample entries instead of the real log, display only.
function J.displayEntries()
    local samples=WoWStatusGuide and WoWStatusGuide.sampleEntries()
    return samples or J.entries()
end
-- Display-only rows marking where each of this account's characters on this
-- client began tracking, when that was after level 1.
local function trackingMarkers()
    local list={}
    for _, c in pairs(db.characters or {}) do
        local start=c.tracking_start
        if type(start)=="table" and S.number(start.level) and start.level>1 and S.number(start.at)
            and c.identity.client==WoWStatusAdapter.client_id and c.settings.enabled then
            list[#list+1]={id="tracking:"..c.identity.client..":"..c.identity.guid,client=c.identity.client,
                sender=P.characterName(c),owner=c.identity.guid,kind="tracking",
                at=start.at,text="Tracking started at level "..start.level,groups={},origin="mine"}
        end
    end
    return list
end
-- Type filter groups for the Activity page: label and the entry kinds it shows.
J.TYPES={
    {"Level-ups",{level=true}}, {"Deaths",{death=true}}, {"Zones",{zone=true}}, {"Quests",{quest=true}},
    {"Professions",{profession=true,professionprogress=true}}, {"Dungeons and raids",{dungeon=true,raid=true}},
    {"Mounts",{mount=true,epicmount=true}}, {"Armor",{loot=true,equipment=true}}, {"Reputation",{reputation=true}},
    {"Class abilities",{unlock=true}}, {"PvP",{pvp=true}}, {"Joins",{introduction=true}}, {"Recaps",{recap=true}},
}
local function visibleEntries()
    local list={}
    local samples=WoWStatusGuide and WoWStatusGuide.sampleEntries()
    local kinds=panel.typeFilter and J.TYPES[panel.typeFilter] and J.TYPES[panel.typeFilter][2]
    for _,e in ipairs(J.displayEntries()) do
        local wanted=(panel.filter=="all" or panel.filter=="character" or (panel.filter=="mine")==not not e.owner)
            and (not panel.character or P.senderKey(e.sender)==panel.character)
            and (not kinds or kinds[e.kind])
        if (e.sample or permitted(e)) and wanted then list[#list+1]=e end
    end
    if not samples and not panel.character and not kinds and (panel.filter=="all" or panel.filter=="mine") then
        for _, marker in ipairs(trackingMarkers()) do list[#list+1]=marker end
        table.sort(list,function(a,b) if a.at==b.at then return a.id>b.id end return a.at>b.at end)
    end
    return list
end
local function render()
    if not panel then return end
    local list=visibleEntries();panel.entriesList=list
    panel.empty:SetShown(#list==0)
    -- What the type and person filters show, with Show all to clear them.
    local parts={}
    if panel.typeFilter and J.TYPES[panel.typeFilter] then parts[#parts+1]=T(J.TYPES[panel.typeFilter][1]) end
    if panel.character then parts[#parts+1]=(panel.characterName or "?"):gsub("|","||") end
    panel.showing:SetText(#parts>0 and (T("Showing:").." |cffffd100"..table.concat(parts," · ").."|r") or "")
    panel.showAll:SetShown(#parts>0)
    panel.typeButton:SetText(T("Type:").." "..(panel.typeFilter and T(J.TYPES[panel.typeFilter][1]) or T("All")))
    panel.personButton:SetText(T("Person:").." "..(panel.character and (panel.characterName or "?"):gsub("|","||") or T("All")))
    panel.child:SetHeight(math.max(360,#list*132))
    local first=math.floor(panel.scroll:GetVerticalScroll()/132)+1
    for slot,row in ipairs(panel.rows) do
        local i=first+slot-1;local e=list[i]
        if e then
            row:ClearAllPoints();row:SetPoint("TOPLEFT",0,-(i-1)*132)
            local texture,r,g,b,heading=WoWStatusPresentation.theme(e)
            row.icon:SetTexture(texture);row.accent:SetColorTexture(r,g,b,1);row.heading:SetTextColor(r,g,b)
            row.heading:SetText(T(heading))
            local who=(not e.owner and not e.sample and WoWStatusRoster and WoWStatusRoster.displayName)
                and WoWStatusRoster.displayName(e.sender) or (e.sender:match("^[^-]+") or e.sender)
            row.message:SetText(who:gsub("|","||").." — "..T(e.text):gsub("|","||"))
            local scope=e.imported=="achievement" and T("From your achievements (date only)") or e.owner and T("Your activity")
                or (e.origin=="catchup" and (T("Caught up via").." "..(e.via or T("a group member"))..(e.relay and (", "..T("passed on by").." "..e.relay) or ""))
                or e.origin=="legacy" and T("Saved group update") or T("Live group update"))
            row.flavour:SetText(WoWStatusFlavour.text(e))
            local when=WoWStatusHistory.oslo(e.at)
            if e.imported then when=when:sub(1,10) end
            local reacted=J.reactionsText(e)
            row.detail:SetText(when.." · "..scope..(reacted and ("  |cffffd100"..reacted.."|r") or ""))
            row.event_id=e.id;row.entry=e;row:Show()
        else row.event_id=nil;row:Hide() end
    end

end
refresh=function()
    if not panel then return end
    local offset=panel.scroll:GetVerticalScroll()
    local anchor=panel.entriesList and panel.entriesList[math.floor(offset/132)+1]
    if offset>0 and anchor then
        for i,e in ipairs(visibleEntries()) do
            if e.id==anchor.id then panel.scroll:SetVerticalScroll((i-1)*132+offset%132);break end
        end
    end
    render()
end
-- The people in the log, for the Person filter: {label, value=sender key}.
local function people()
    local list,seen={},{}
    for _,e in ipairs(J.displayEntries()) do
        local key=P.senderKey(e.sender)
        if key and not seen[key] and (e.sample or permitted(e)) then
            seen[key]=true
            local shown=(not e.owner and WoWStatusRoster and WoWStatusRoster.displayName) and WoWStatusRoster.displayName(e.sender)
                or (e.sender:match("^[^-]+") or e.sender)
            list[#list+1]={label=shown:gsub("|","||"),value=key,name=e.sender:match("^[^-]+") or e.sender}
        end
    end
    table.sort(list,function(a,b) return S.lowerASCII(a.label)<S.lowerASCII(b.label) end)
    return list
end
local function build(parent)
    panel=CreateFrame("Frame","WoWStatusActivityLog",parent);panel:SetAllPoints(parent)
    panel.scroll=CreateFrame("ScrollFrame",nil,panel,"UIPanelScrollFrameTemplate")
    panel.scroll:SetPoint("TOPLEFT",24,-4);panel.scroll:SetSize(710,470)
    panel.child=CreateFrame("Frame",nil,panel.scroll);panel.child:SetSize(686,420);panel.scroll:SetScrollChild(panel.child)
    panel.empty=label(panel.child,"GameFontHighlightLarge",24,-180,620)
    panel.empty:SetJustifyH("CENTER");panel.empty:SetText(T("No activity yet"))
    panel.rows={};panel.filter="all"
    for i=1,6 do
        local row=WoWStatusUI.box(panel.child,680,124)
        row.accent=row:CreateTexture(nil,"OVERLAY");row.accent:SetPoint("TOPLEFT",4,-4);row.accent:SetSize(672,2)
        row.iconFrame=WoWStatusUI.icon(row,60);row.iconFrame:SetPoint("TOPLEFT",12,-20);row.icon=row.iconFrame.texture
        row.heading=label(row,"GameFontNormalLarge",88,-12,570)
        row.message=label(row,"GameFontHighlightLarge",88,-36,570);row.message:SetHeight(42)
        row:EnableMouse(true)
        row:SetScript("OnEnter",function(self)
            if GameTooltip and self.entry then
                GameTooltip:SetOwner(self,"ANCHOR_RIGHT");GameTooltip:SetText(self.entry.sender)
                GameTooltip:AddLine(self.entry.text,1,1,1,true)
                GameTooltip:AddLine(T("Event ID:").." "..self.entry.id,.6,.6,.6,true);GameTooltip:Show()
            end
        end)
        row:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
        row.flavour=label(row,"GameFontHighlightSmall",88,-80,570)
        row.detail=label(row,"GameFontHighlightSmall",88,-102,570)
        panel.rows[i]=row
    end
    if panel.scroll.HookScript then panel.scroll:HookScript("OnVerticalScroll",render)
    else panel.scroll:SetScript("OnVerticalScroll",render) end
    local buttons={{"All","all"},{"Mine","mine"},{"Friends","friends"}}
    for i,b in ipairs(buttons) do
        local widget=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");widget:SetPoint("TOPLEFT",24+(i-1)*114,-490);widget:SetSize(106,30);widget:SetText(T(b[1]))
        widget:SetScript("OnClick",function() panel.filter=b[2];panel.scroll:SetVerticalScroll(0);render() end)
    end
    -- Type and Person filters, combined with the buttons above.
    panel.typeButton=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.typeButton:SetPoint("TOPLEFT",372,-490);panel.typeButton:SetSize(176,30)
    panel.typeButton:SetScript("OnClick",function(self)
        local items={{label=T("All"),value=0}}
        for i,t in ipairs(J.TYPES) do items[#items+1]={label=T(t[1]),value=i} end
        WoWStatusUI.menu(self,items,function(value)
            panel.typeFilter=value~=0 and value or nil;panel.scroll:SetVerticalScroll(0);render()
        end)
    end)
    panel.personButton=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.personButton:SetPoint("TOPLEFT",556,-490);panel.personButton:SetSize(176,30)
    panel.personButton:SetScript("OnClick",function(self)
        local list,items=people(),{{label=T("All"),value=""}}
        for _,item in ipairs(list) do items[#items+1]={label=item.label,value=item.value} end
        WoWStatusUI.menu(self,items,function(value)
            panel.character,panel.characterName=value~="" and value or nil,nil
            for _,item in ipairs(list) do if item.value==value then panel.characterName=item.name end end
            panel.scroll:SetVerticalScroll(0);render()
        end)
    end)
    panel.showing=label(panel,"GameFontHighlight",24,-528,420)
    panel.showAll=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");panel.showAll:SetPoint("TOPLEFT",450,-522);panel.showAll:SetSize(110,24)
    panel.showAll:SetText(T("Show all"));panel.showAll:Hide()
    panel.showAll:SetScript("OnClick",function()
        panel.filter,panel.typeFilter,panel.character,panel.characterName="all",nil,nil,nil
        panel.scroll:SetVerticalScroll(0);render()
    end)
    return panel
end
-- The log is the Activity page of the main window (#57).
WoWStatusMainWindow.register("activity","Activity",build,function() render() end)
function J.show()
    if not db then return end
    WoWStatusMainWindow.show("activity")
end
-- Open the Activity page showing only one character's entries.
function J.showCharacter(name)
    if not db or not P.senderKey(name) then return false end
    WoWStatusMainWindow.show("activity")
    panel.filter,panel.character,panel.characterName="all",P.senderKey(name),name:match("^[^-]+") or name
    panel.scroll:SetVerticalScroll(0);render()
    return true
end
-- Open the Activity page scrolled to one entry (used by the Overview links).
function J.focus(id)
    if not db or not index[id] then return false end
    WoWStatusMainWindow.show("activity")
    panel.filter="all"
    for i,e in ipairs(visibleEntries()) do
        if e.id==id then panel.scroll:SetVerticalScroll((i-1)*132);render();return true end
    end
    panel.scroll:SetVerticalScroll(0);render()
    return false
end
function J.visible(entry) return db~=nil and (entry.sample==true or permitted(entry)) end
-- A private recap has no group scopes and is never sent or offered to peers.
function J.recordRecap(character,at,text,flavour)
    if not db or type(text)~="string" or text=="" then return false end
    local identity=character.identity
    return add({id="recap:"..identity.client..":"..identity.guid..":"..at,client=identity.client,
        sender=P.characterName(character),owner=identity.guid,kind="recap",at=at,
        text=trim(text,160),flavour=flavour,groups={},origin="mine"})
end
local frame=CreateFrame("Frame")
-- Reaction whispers ("GZ!", "F", "Congrats!" ... from the buttons on friends'
-- notifications, English or Nynorsk) are linked to this character's matching
-- event of the last 15 minutes, and shown on its log card ("GZ! from Mira").
local REACTION_KINDS={["GZ!"]={level=true},["F"]={death=true},["Git Good"]={death=true},
    ["Welcome!"]={introduction=true},["Velkomen!"]={introduction=true}}
local POSITIVE={profession=true,dungeon=true,raid=true,mount=true,epicmount=true,reputation=true,unlock=true,pvp=true,
    quest=true,loot=true}
local REACTION_WINDOW=900
function J.reaction(text,sender)
    text,sender=S.string(text),S.string(sender)
    if not db or not current or not text or not sender or #text>64 or P.isSelf(sender) then return false end
    local kinds,zone=REACTION_KINDS[text],text:match("^Enjoy (.+)!$") or text:match("^Kos deg i (.+)!$")
    if text=="Congrats!" or text=="Gratulerer!" then kinds=POSITIVE end
    if zone then kinds={zone=true} end
    if not kinds then return false end
    -- Only group members react through the buttons.
    local member=false
    for group in pairs(WoWStatusGroups.selected(current)) do if peer(group,sender) then member=true end end
    if not member then return false end
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
                if refresh then refresh() end
                return true
            end
            return false
        end
    end
    return false
end
-- "GZ! from Mira, Bob · F from Eve", in the order they arrived.
function J.reactionsText(e)
    if type(e)~="table" or type(e.reactions)~="table" then return nil end
    local list={}
    for _,r in pairs(e.reactions) do list[#list+1]=r end
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
frame:RegisterEvent("CHAT_MSG_ADDON")
pcall(frame.RegisterEvent,frame,"CHAT_MSG_WHISPER")
frame:SetScript("OnEvent",function(_,event,prefix,message,distribution,sender)
    if event=="CHAT_MSG_WHISPER" then J.reaction(prefix,message);return end
    if S.string(prefix)==PREFIX then J.receive(S.string(message),S.string(sender),S.string(distribution)) end
end)
local elapsed=0
frame:SetScript("OnUpdate",function(_,delta) elapsed=elapsed+delta;if elapsed>=.25 then elapsed=0;J.tick() end end)
