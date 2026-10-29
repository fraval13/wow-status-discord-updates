-- Persistent account log and bounded, group-scoped peer anti-entropy.
-- No server, remote code, executable serialization or arbitrary chat input.
WoWStatusJournal = {}
local J, S, P = WoWStatusJournal, WoWStatusSafe, WoWStatusPopups
local db, current, index, digests = nil,nil,{},{}
local requests, sessions, sendQueue, cursors, rates = {},{},{},{},{}
local serial,lastSend=0,0
local jobs,queuedJobs,contacted,hellos,seenHello={},{},{},{},{}
local loginUntil,loginNonce=0,nil
local pumpJobs
local PREFIX, CAP, AGE, PAGE = "WoWStatusLog",2000,7*86400,6
local panel, refresh
local equipment, professionRanks, lastQuery = {}, {}, {}
local sharedKinds={level=true,loot=true,death=true,zone=true,quest=true,profession=true,
    dungeon=true,mount=true,reputation=true,unlock=true,pvp=true}
local fields={level="level",zone="zone",quest="quests",questprogress="quests",profession="professions",
    professionprogress="professions",equipment="gear"}
local function trim(text,limit)
    if type(text)~="string" then return "" end
    text=text:gsub("[%c|]"," ")
    if #text>limit then text=text:sub(1,limit-3):gsub("[\194-\244][\128-\191]*$","").."..." end
    return text
end
local function ownName()
    return (WoWStatusAdapter.playerName() or current.identity.name).."-"..(WoWStatusAdapter.realmName() or current.identity.realm):gsub("%s","")
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
local function groupMember(group)
    return current and WoWStatusGroups.selected(current)[group]
end
local function peer(group,sender)
    local key=P.senderKey(sender)
    for _, name in ipairs(P.peers(group)) do if P.senderKey(name)==key then return true end end
    return false
end
local function permitted(entry)
    if (entry.kind=="loot" or entry.kind=="equipment") and not WoWStatusLoot.allowed(current and current.settings,entry) then return false end
    if not entry.owner then return true end
    local owner
    for _, c in pairs(db.characters or {}) do if c.identity.guid==entry.owner and c.identity.client==entry.client then owner=c;break end end
    if not owner or not owner.settings.enabled then return false end
    local kind=({questprogress="quest",professionprogress="profession"})[entry.kind] or entry.kind
    if entry.kind~="equipment" and not owner.settings.collection[kind] then return false end
    if fields[entry.kind] and not owner.settings.fields[fields[entry.kind]] then return false end
    if kind=="introduction" and not owner.settings.introduction_confirmed then return false end
    return true
end
local function relayable(entry,group)
    if entry.legacy or entry.client~=WoWStatusAdapter.client_id or not sharedKinds[entry.kind] or not entry.groups or not entry.groups[group] or not permitted(entry) then return false end
    local member=groupMember(group)
    if not member or entry.at<(member.joined_at or time()) or entry.at<time()-AGE then return false end
    if entry.owner then
        local owner
        for _, c in pairs(db.characters) do if c.identity.guid==entry.owner and c.identity.client==entry.client then owner=c;break end end
        if not owner or not owner.settings.in_game or owner.settings.in_game[entry.kind]==false then return false end
        if entry.kind=="loot" and not WoWStatusLoot.allowed(owner.settings,entry) then return false end
    end
    return true
end
local function rebuild()
    index,digests={},{}
    table.sort(db.journal.entries,function(a,b) if a.at==b.at then return a.id>b.id end return a.at>b.at end)
    local private=0
    local kept,seen={},{}
    for _, e in ipairs(db.journal.entries) do
        if not seen[e.id] then
            seen[e.id]=true
            if e.owner and not next(e.groups or {}) then private=private+1 end
            if not (e.owner and not next(e.groups or {}) and private>1000) then kept[#kept+1]=e end
        end
    end
    db.journal.entries=kept
    while #db.journal.entries>CAP do table.remove(db.journal.entries) end
    for _, e in ipairs(db.journal.entries) do index[e.id]=e;digests[digest(e.id)]=e end
end
local function add(entry)
    if not db or not entry.id or not permitted(entry) then return false end
    local old=index[entry.id]
    if old then
        -- A live legacy packet can have a shorter display string than its log copy.
        if old.kind~=entry.kind or P.senderKey(old.sender)~=P.senderKey(entry.sender) or old.at~=entry.at then return false end
        for group in pairs(entry.groups or {}) do if not old.owner then old.groups[group]=true end end
        if #entry.text>#old.text then old.text=entry.text end
        if refresh then refresh() end
        return false
    end
    if not entry.owner then
        for _, c in pairs(db.characters or {}) do
            local name=c.identity.name.."-"..c.identity.realm:gsub("%s","")
            if P.senderKey(name)==P.senderKey(entry.sender) and c.identity.client==entry.client then return false end
        end
    end
    entry.groups=entry.groups or {}
    table.insert(db.journal.entries,entry);rebuild()
    if refresh then refresh() end
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
                local epoch,sequence=event.id:match(":(%d+%-%d+):(%d+)$")
                local name=c.identity.name.."-"..c.identity.realm:gsub("%s","")
                local id=epoch and c.identity.client..":"..P.senderKey(name)..":"..epoch.."-"..sequence
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
    local nonce=current.epoch.."-"..current.sequence
    if backfill then
        local epoch,seq=event.id:match(":(%d+%-%d+):(%d+)$")
        nonce=epoch and epoch.."-"..seq or nil
    end
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
    if kind=="equipment" and not WoWStatusLoot.allowed(current and current.settings,info) then return end
    if not db or not current.settings.enabled or not fields[kind] or not current.settings.fields[fields[kind]] then return end
    local category=({questprogress="quest",professionprogress="profession"})[kind] or kind
    if kind~="equipment" and not current.settings.collection[category] then return end
    current.journal_sequence=(current.journal_sequence or 0)+1
    add({id="local:"..current.identity.client..":"..current.identity.guid..":"..current.epoch..":"..current.journal_sequence,
        client=current.identity.client,sender=ownName(),owner=current.identity.guid,kind=kind,at=time(),
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
function J.professions(observed)
    if not observed then return end
    for _, p in ipairs(observed) do
        if professionRanks[p.name] and p.skill>professionRanks[p.name] then
            J.observe("professionprogress",p.name..": "..p.skill.." / "..p.max_skill)
        end
        professionRanks[p.name]=p.skill
    end
end
function J.received(item)
    if not db or item.preview then return end
    local id=J.eventID(item.sender,item.nonce)
    if not id then return end
    local groups={}
    if item.group_id then groups[item.group_id]=true end
    add({id=id,client=WoWStatusAdapter.client_id,sender=item.sender,kind=item.kind or "level",level=item.level,
        text=trim(item.level and ("Reached level "..item.level.."!") or item.text or "",160),
        quality=item.quality,class_id=item.class_id,equip_loc=item.equip_loc,item_id=item.item_id,
        at=item.at or item.received_at or time(),groups=groups,origin="live"})
end
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
    local kept={}
    for _, e in ipairs(db.journal.entries) do
        if permitted(e) then
            if e.owner then for g in pairs(e.groups) do if not relayable(e,g) then e.groups[g]=nil end end end
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
    if #text>1024 then return nil end
    local values,pos={},1
    for _=1,11 do
        local first,last,number=text:find("^(%d+):",pos)
        if not first or #number>4 then return nil end
        local count=tonumber(number)
        if count>300 or last+count>#text then return nil end
        values[#values+1]=text:sub(last+1,last+count);pos=last+count+1
    end
    if pos~=#text+1 then return nil end
    local id,client,sender,at,kind,level,detail=values[1],values[2],values[3],tonumber(values[4]),values[5],values[6],values[7]
    if client~=WoWStatusAdapter.client_id or not sharedKinds[kind] or #id>220 or #sender>120 or not P.senderKey(sender)
        or not at or at~=math.floor(at) or at<time()-AGE or at>time()+300 or #detail>160 or detail:find("[%c|]") then return nil end
    local prefix=client..":"..P.senderKey(sender)..":"
    if id:sub(1,#prefix)~=prefix or not id:sub(#prefix+1):match("^[%w%-]+$") or #id-#prefix>64 then return nil end
    if kind=="level" then
        level=tonumber(level)
        if not level or level~=math.floor(level) or level<2 or level>WoWStatusAdapter.max_level then return nil end
    elseif level~="" then return nil else level=nil end
    local e={id=id,client=client,sender=sender,at=at,kind=kind,level=level,text=detail,groups={},origin="catchup",
        quality=tonumber(values[8]),class_id=tonumber(values[9]),equip_loc=values[10],item_id=tonumber(values[11])}
    if kind=="loot" and (not e.item_id or not WoWStatusLoot.allowed(current.settings,e)) then return nil end
    if kind~="loot" and (values[8]~="" or values[9]~="" or values[10]~="" or values[11]~="") then return nil end
    return e
end
local function queue(group,target,body,id)
    local text="J2 "..group.." "..body
    if #text>243 or #sendQueue>=512 then return false end
    sendQueue[#sendQueue+1]={group=group,target=target,text=text,id=id,query=body:match("^Q ([%w%-]+)")}
    return true
end
local function token()
    serial=serial+1;db.journal.request_serial=serial;return time().."-"..serial
end
local function lootMask()
    local rarities=current.settings.loot_rarities or {rare=true,epic=true,legendary=true}
    return (rarities.rare and 1 or 0)+(rarities.epic and 2 or 0)+(rarities.legendary and 4 or 0)
end
local function requestPage(group,target,offset,pages,retries)
    local t=token()
    local member=groupMember(group)
    if not member then return end
    local cutoff=math.max(member.joined_at or time(),time()-AGE)
    requests[t]={group=group,target=target,key=P.senderKey(target),at=time(),offset=offset,pages=pages or 0,cutoff=cutoff,pending={},parts={},retries=retries or 0}
    queue(group,target,"Q "..t.." "..offset.." "..cutoff.." "..lootMask())
end
local function advance(t)
    local r=requests[t]
    if not r or not r.nextOffset or next(r.pending) then return end
    requests[t]=nil
    local key=r.group..":"..r.key
    cursors[key]=r.more and r.nextOffset or 0
    if r.more and r.pages<math.ceil(CAP/PAGE) then requestPage(r.group,r.target,r.nextOffset,r.pages+1,r.retries)
    elseif pumpJobs then pumpJobs() end
end
local function enqueueJob(group,target,retries)
    local key=group..":"..P.senderKey(target)
    if queuedJobs[key] or #jobs>=512 then return end
    for _,r in pairs(requests) do if r.group==group and r.key==P.senderKey(target) then return end end
    jobs[#jobs+1]={group=group,target=target,retries=retries or 0};queuedJobs[key]=true
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
    if op=="H" then
        if body~=WoWStatusAdapter.client_id then return false end
        local helloKey=group..":"..key
        if seenHello[helloKey]==t then return true end
        seenHello[helloKey]=t;enqueueJob(group,sender);return true
    end
    if op=="Q" then
        local offset,cutoff,mask=body:match("^(%d+) (%d+) ([0-7])$")
        offset,cutoff,mask=tonumber(offset),tonumber(cutoff),tonumber(mask)
        if not offset or offset>CAP or not cutoff or cutoff>time()+300 then return false end
        local rateKey=group..":"..key
        if rates[rateKey] and time()-rates[rateKey]<2 then return false end
        rates[rateKey]=time()
        for sessionKey,session in pairs(sessions) do
            if session.group==group and session.key==key then sessions[sessionKey]=nil end
        end
        local n=0;for _ in pairs(sessions) do n=n+1 end;if n>=32 then return false end
        cutoff=math.max(cutoff,time()-AGE,groupMember(group).joined_at or time())
        local eligible={}
        for _,e in ipairs(db.journal.entries) do
            local weight=({[3]=1,[4]=2,[5]=4})[e.quality]
            local wanted=e.kind~="loot" or (weight and math.floor(mask/weight)%2==1)
            if wanted and e.at>=cutoff and relayable(e,group) then eligible[#eligible+1]=e end
        end
        local offer,list={},{}
        for i=offset+1,math.min(offset+PAGE,#eligible) do local d=digest(eligible[i].id);offer[d]=eligible[i].id;list[#list+1]=d end
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
        local wanted,seen,n={}, {}, 0
        if list~="-" then
            for d in list:gmatch("[^,]+") do
                n=n+1
                if #d~=22 or seen[d] or n>PAGE then return false end
                seen[d]=true
                local existing=digests[d]
                if not existing or not existing.groups[group] then wanted[#wanted+1]=d end
            end
        end
        r.inventory=true;r.nextOffset=offset;r.more=more=="1"
        if r.more and offset<=r.offset then return false end
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
            if e and relayable(e,group) then
                local encoded=pack(e):gsub(".",function(c) return string.format("%02x",c:byte()) end)
                local total=math.ceil(#encoded/140)
                for part=1,total do
                    queue(group,sender,"D "..t.." "..d.." "..part.."/"..total.." "..encoded:sub((part-1)*140+1,part*140),e.id)
                end
            end
        end
        return true
    elseif op=="D" then
        if not r or r.group~=group or r.key~=key then return false end
        local d,part,total,data=body:match("^([a-f0-9]+) (%d+)/(%d+) ([a-f0-9]+)$")
        part,total=tonumber(part),tonumber(total)
        if not d or #d~=22 or not r.pending[d] or not part or not total or total<1 or total>16 or part<1 or part>total or #data>140 or #data%2~=0 then return false end
        local chunks=r.parts[d] or {total=total};r.parts[d]=chunks
        if chunks.total~=total or (chunks[part] and chunks[part]~=data) then return false end
        chunks[part]=data
        for i=1,total do if not chunks[i] then return true end end
        local decoded=table.concat(chunks):gsub("..",function(pair) return string.char(tonumber(pair,16)) end)
        local e=unpackEntry(decoded)
        if not e or digest(e.id)~=d or e.at<r.cutoff then return false end
        -- Forwarded identities are claims by the relay, not authenticated origins.
        e.groups[group]=true;e.via=sender
        add(e);r.pending[d]=nil;r.parts[d]=nil;advance(t)
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
    for k,at in pairs(rates) do if now-at>120 then rates[k]=nil end end
    J.sync()
    if InCombatLockdown and InCombatLockdown() then return end
    local clock=GetTime and GetTime() or now
    if clock-lastSend<.5 or #sendQueue==0 or WoWStatusAdapter.chatRestricted() then return end
    local item=sendQueue[1]
    local queryKey=item.group..":"..P.senderKey(item.target)
    if item.query and lastQuery[queryKey] and clock-lastQuery[queryKey]<2.1 then return end
    table.remove(sendQueue,1)
    if not groupMember(item.group) or not peer(item.group,item.target) then return end
    if item.id and (not index[item.id] or not relayable(index[item.id],item.group)) then return end
    local send=C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
    if send then
        lastSend=clock
        if item.query then
            lastQuery[queryKey]=clock
            if requests[item.query] then requests[item.query].at=now;requests[item.query].sent=true end
        end
        pcall(send,PREFIX,item.text,"WHISPER",item.target)
    end
end
function J.init(database,character)
    db,current=database,character
    db.journal=db.journal or {version=1,entries={}}
    index,digests={},{};requests,sessions,sendQueue,cursors,rates={},{},{},{},{}
    serial=db.journal.request_serial or 0
    equipment,professionRanks,lastQuery={},{},{}
    for slot=1,19 do equipment[slot]=WoWStatusAdapter.equipment(slot) end
    for _, p in ipairs(character.progress and character.progress.professions or {}) do professionRanks[p.name]=p.skill end
    lastSend=0;loginNonce=token()
    jobs,queuedJobs,contacted,hellos,seenHello={},{},{},{},{}
    local kept={}
    for _,e in ipairs(db.journal.entries) do if type(e)=="table" and type(e.id)=="string" and type(e.at)=="number" and type(e.text)=="string" and permitted(e) then e.groups=e.groups or {};kept[#kept+1]=e end end
    db.journal.entries=kept;rebuild();J.groupsChanged();loginUntil=time()+60
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
end
local function label(parent,font,x,y,width)
    local f=parent:CreateFontString(nil,"OVERLAY",font);f:SetPoint("TOPLEFT",x,y);f:SetWidth(width);f:SetJustifyH("LEFT");return f
end
local function visibleEntries()
    local list={}
    for _,e in ipairs(J.entries()) do
        if permitted(e) and (panel.filter=="all" or (panel.filter=="mine")==not not e.owner) then list[#list+1]=e end
    end
    return list
end
local function render()
    if not panel then return end
    local list=visibleEntries();panel.entriesList=list
    panel.empty:SetShown(#list==0)
    panel.child:SetHeight(math.max(360,#list*112))
    local first=math.floor(panel.scroll:GetVerticalScroll()/112)+1
    for slot,row in ipairs(panel.rows) do
        local i=first+slot-1;local e=list[i]
        if e then
            row:ClearAllPoints();row:SetPoint("TOPLEFT",0,-(i-1)*112)
            local texture,r,g,b,heading=WoWStatusPresentation.theme(e)
            row.icon:SetTexture(texture);row.accent:SetColorTexture(r,g,b,1);row.heading:SetTextColor(r,g,b)
            row.heading:SetText(heading)
            row.message:SetText(((e.sender:match("^[^-]+") or e.sender):gsub("|","||")).." — "..e.text:gsub("|","||"))
            local scope=e.owner and "Your activity" or (e.origin=="catchup" and "Caught up via "..(e.via or "a group member") or e.origin=="legacy" and "Saved group update" or "Live group update")
            row.detail:SetText(WoWStatusHistory.oslo(e.at).." · "..scope)
            row.event_id=e.id;row.entry=e;row:Show()
        else row.event_id=nil;row:Hide() end
    end

end
refresh=function()
    if not panel then return end
    local offset=panel.scroll:GetVerticalScroll()
    local anchor=panel.entriesList and panel.entriesList[math.floor(offset/112)+1]
    if offset>0 and anchor then
        for i,e in ipairs(visibleEntries()) do
            if e.id==anchor.id then panel.scroll:SetVerticalScroll((i-1)*112+offset%112);break end
        end
    end
    render()
end
function J.show()
    if not db then return end
    if not panel then
        panel=CreateFrame("Frame","WoWStatusActivityLog",UIParent);panel:SetSize(780,610);panel:SetPoint("CENTER")
        panel:SetFrameStrata("FULLSCREEN_DIALOG");panel:EnableMouse(true);panel:SetMovable(true);panel:RegisterForDrag("LeftButton")
        panel:SetScript("OnDragStart",panel.StartMoving);panel:SetScript("OnDragStop",panel.StopMovingOrSizing)
        local bg=panel:CreateTexture(nil,"BACKGROUND");bg:SetAllPoints();bg:SetColorTexture(.025,.035,.065,.98)
        label(panel,"GameFontNormalLarge",24,-20,720):SetText("WoW Status — activity log")
        panel.scroll=CreateFrame("ScrollFrame",nil,panel,"UIPanelScrollFrameTemplate")
        panel.scroll:SetPoint("TOPLEFT",24,-66);panel.scroll:SetSize(710,480)
        panel.child=CreateFrame("Frame",nil,panel.scroll);panel.child:SetSize(686,420);panel.scroll:SetScrollChild(panel.child)
        panel.empty=label(panel.child,"GameFontHighlightLarge",24,-180,620)
        panel.empty:SetJustifyH("CENTER");panel.empty:SetText("No activity yet")
        panel.rows={};panel.filter="all"
        for i=1,6 do
            local row=CreateFrame("Frame",nil,panel.child);row:SetSize(680,104)
            local background=row:CreateTexture(nil,"BACKGROUND");background:SetAllPoints();background:SetColorTexture(.04,.05,.08,.98)
            row.accent=row:CreateTexture(nil,"OVERLAY");row.accent:SetPoint("TOPLEFT");row.accent:SetSize(680,3)
            row.icon=row:CreateTexture(nil,"ARTWORK");row.icon:SetPoint("TOPLEFT",14,-22);row.icon:SetSize(56,56)
            row.heading=label(row,"GameFontNormalLarge",88,-12,570)
            row.message=label(row,"GameFontHighlightLarge",88,-36,570);row.message:SetHeight(42)
            row:EnableMouse(true)
            row:SetScript("OnEnter",function(self)
                if GameTooltip and self.entry then
                    GameTooltip:SetOwner(self,"ANCHOR_RIGHT");GameTooltip:SetText(self.entry.sender)
                    GameTooltip:AddLine(self.entry.text,1,1,1,true)
                    GameTooltip:AddLine("Event ID: "..self.entry.id,.6,.6,.6,true);GameTooltip:Show()
                end
            end)
            row:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
            row.detail=label(row,"GameFontHighlightSmall",88,-80,570)
            panel.rows[i]=row
        end
        if panel.scroll.HookScript then panel.scroll:HookScript("OnVerticalScroll",render)
        else panel.scroll:SetScript("OnVerticalScroll",render) end
        local buttons={{"All",function() panel.filter="all" end},{"Mine",function() panel.filter="mine" end},
            {"Friends",function() panel.filter="friends" end},{"Close",function() panel:Hide() end}}
        for i,b in ipairs(buttons) do
            local widget=CreateFrame("Button",nil,panel,"UIPanelButtonTemplate");widget:SetPoint("TOPLEFT",24+(i-1)*182,-556);widget:SetSize(160,30);widget:SetText(b[1])
            widget:SetScript("OnClick",function() b[2]();panel.scroll:SetVerticalScroll(0);render() end)
        end
        table.insert(UISpecialFrames,"WoWStatusActivityLog")
    end
    render();panel:Show()
end
local frame=CreateFrame("Frame")
frame:RegisterEvent("CHAT_MSG_ADDON")
frame:SetScript("OnEvent",function(_,_,prefix,message,distribution,sender)
    if S.string(prefix)==PREFIX then J.receive(S.string(message),S.string(sender),S.string(distribution)) end
end)
local elapsed=0
frame:SetScript("OnUpdate",function(_,delta) elapsed=elapsed+delta;if elapsed>=.25 then elapsed=0;J.tick() end end)
