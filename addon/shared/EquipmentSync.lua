-- Group-scoped equipment recovery and live invalidation. Capture time and the
-- owner's persistent revision travel unchanged through relays; arrival is not
-- freshness. Only complete snapshots become visible or eligible for relaying.
WoWStatusEquipmentSync = {}
local G, S, E = WoWStatusEquipmentSync, WoWStatusSafe, WoWStatusEquipment
local db, current, transport
local jobs, hello, offers, pending, answered, dirty = {}, {}, {}, {}, {}, {}
local MAX_CACHE, MAX_JOBS, MAX_PENDING = 256, 64, 4
local CLASSES = {WARRIOR=true, PALADIN=true, HUNTER=true, ROGUE=true, PRIEST=true, DEATHKNIGHT=true,
    SHAMAN=true, MAGE=true, WARLOCK=true, MONK=true, DRUID=true, DEMONHUNTER=true, EVOKER=true}
local function now() return S.now() end
local function key(name) return WoWStatusRoster.key(name) end
local function id() return db.roster.id end
local function touring() return WoWStatusGuide and WoWStatusGuide.touring() end
local function selected(group) return current and WoWStatusGroups.contains(current, group) end
local function recordKey(owner, name) return owner .. ":" .. (key(name) or "") end
local function count(map) local n=0; for _ in pairs(map) do n=n+1 end; return n end
local function validID(value) return type(value)=="string" and #value==16 and value:match("^[0-9a-f]+$") end
local function cache() return db.roster.equipment_cache end
local function trim(map, maximum)
    while count(map) > maximum do
        local oldest, at
        for k, value in pairs(map) do
            local stamp = type(value)=="table" and S.number(value.at) or S.number(value)
            if not at or (stamp or 0) < at then oldest, at = k, stamp or 0 end
        end
        if not oldest then break end
        map[oldest] = nil
    end
end
local function notify()
    if WoWStatusProfile and WoWStatusProfile.refreshEquipment then WoWStatusProfile.refreshEquipment() end
    if WoWStatusMainWindow and WoWStatusMainWindow.active()=="overview" and WoWStatusOverview then WoWStatusOverview.render() end
end
-- Revisions are comparable only within one owner ID. Capture time breaks ties
-- and orders snapshots after an owner has reset their addon identity.
function G.newer(a, b)
    if not b then return true end
    if a.owner == b.owner and a.revision ~= b.revision then return a.revision > b.revision end
    return a.at > b.at
end
local function same(a,b) return a and b and a.owner==b.owner and a.revision==b.revision and a.hidden==b.hidden end
local function peers(group)
    local list = WoWStatusPopups.peers(group)
    if #list==0 and WoWStatusRoster.recentMembers then list=WoWStatusRoster.recentMembers(group) end
    return list
end
local function send(op, group, peer, values, owner)
    if not selected(group) or touring() then return false end
    local words={op,group,id()}
    for _, value in ipairs(values or {}) do words[#words+1]=tostring(value) end
    return transport(group, peer, table.concat(words," "), owner)
end
local function ownRecord(character)
    local identity, info = character.identity, character.roster_info
    if not identity or identity.client~=WoWStatusAdapter.client_id or type(info)~="table" then return nil end
    local name=WoWStatusPopups.characterName(character)
    if not S.string(name) or #name>64 or not WoWStatusPopups.fullName(name) then return nil end
    local allowed=db.roster.share and not character.hide_from_list and character.settings
        and character.settings.fields and character.settings.fields.gear
    local old=character.equipment_notice
    if not allowed and not old then return nil end -- Never disclose an unshared character.
    local snapshot=allowed and character.equipment_profile
    if allowed and not snapshot then return nil end
    local revision=S.number(character.equipment_revision) or 0
    if old and old.hidden~=(not allowed) then
        revision=math.max(revision,old.revision or 0)+1
        character.equipment_revision=revision
        if snapshot then snapshot.revision=revision end
    end
    revision=math.max(1,revision)
    local at=snapshot and snapshot.at or (old and old.hidden and old.at) or math.floor(now())
    local groups=old and old.groups or {}
    character.equipment_notice={revision=revision,at=at,hidden=not allowed,groups=groups}
    return {owner=id(),name=name,revision=revision,at=at,hidden=not allowed,race=info.race,sex=info.sex,
        class=info.class,level=info.level,snapshot=snapshot,groups=groups,own=character}
end
local function metadata(record,group,peer)
    if record.own and not record.hidden then record.groups[group]=true end
    if record.hidden and record.own and not record.groups[group] then return true end
    if not record.hidden and (not record.race or not record.sex or not record.class or not record.level) then return true end
    return send("H",group,peer,{record.owner,record.name:gsub(" ","_"),record.revision,record.at,
        record.hidden and 1 or 0,record.hidden and "-" or record.race,record.hidden and "-" or record.sex,
        record.hidden and "-" or record.class,record.hidden and "-" or record.level},record.own and not record.hidden and record.own or nil)
end
local function records(group)
    local list={}
    for _, character in pairs(db.characters or {}) do
        if character==current then E.capture(character) end
        local record=ownRecord(character)
        if record and (not record.hidden or record.groups[group]) then list[#list+1]=record end
    end
    for _, record in pairs(cache()) do
        if record.owner~=id() and not record.withdrawn and not WoWStatusRoster.isHidden(record.name) and record.groups and record.groups[group] then list[#list+1]=record end
    end
    table.sort(list,function(a,b)
        if (a.own~=nil)~=(b.own~=nil) then return a.own~=nil end
        if a.at~=b.at then return a.at>b.at end
        return recordKey(a.owner,a.name)<recordKey(b.owner,b.name)
    end)
    return list
end
local function inventory(group,peer)
    local k="inventory:"..group..":"..(key(peer) or "")
    if not jobs[k] and count(jobs)>=MAX_JOBS then return false end
    jobs[k]={group=group,peer=peer,records=records(group),index=1,at=time()}
    return true
end
function G.hello(group,peer,force)
    if not db or touring() or WoWStatusPopups.isSelf(peer) then return end
    local k=group..":"..(key(peer) or "")
    if not force and hello[k] then return end
    local ready=inventory(group,peer)
    if ready and send("J",group,peer,{}) then hello[k]=time() end
end
function G.sync()
    if not db or touring() then return end
    for group in pairs(WoWStatusGroups.selected(current)) do
        for _, peer in ipairs(peers(group)) do G.hello(group,peer,true) end
    end
end
function G.changed(character,gearChanged)
    if not db or not character then return end
    local at=time()+(gearChanged and 1 or 60)
    local before=dirty[character]
    dirty[character]=before and math.min(before,at) or at
    WoWStatusRoster.render()
    notify()
end
function G.privacyChanged()
    if not db then return end
    E.capture(current)
    for _, character in pairs(db.characters or {}) do ownRecord(character); dirty[character]=time() end
end
function G.withdraw(owner)
    if not db then return end
    for k,record in pairs(cache()) do
        if record.owner==owner then
            record.withdrawn=true
            offers[k]=nil
            for token,request in pairs(pending) do if request.record==k then pending[token]=nil end end
        end
    end
    notify()
end
local function store(record,group)
    local k=recordKey(record.owner,record.name)
    local old=cache()[k]
    if old and not same(record,old) and not G.newer(record,old) then return false end
    if old and same(record,old) and old.at>record.at then
        record.at=old.at
        if record.snapshot then record.snapshot.at=old.at end
    end
    record.groups=old and old.groups or {}
    record.groups[group]=true
    cache()[k]=record
    trim(cache(),MAX_CACHE)
    WoWStatusRoster.storeEquipment(record,group)
    notify()
    return true
end
function G.get(name)
    if not db or touring() then return nil end
    if WoWStatusRoster.isHidden(name) then return nil,true,true end
    local best
    for _, record in pairs(cache()) do
        if key(record.name)==key(name) then
            for group in pairs(record.groups or {}) do
                if selected(group) and (not best or G.newer(record,best)) then best=record end
            end
        end
    end
    if best then
        if best.withdrawn then return nil,true,true end
        return best.snapshot,best.hidden,true
    end
end
function G.waiting(name)
    for _, offer in pairs(offers) do if key(offer.meta.name)==key(name) and offer.need then return true end end
    return false
end
function G.refresh(name)
    if not db or touring() then return nil end
    for _, offer in pairs(offers) do
        if key(offer.meta.name)==key(name) then
            local source=offer.sources[1]
            if source and (not source.asked or time()-source.asked>=60) then
                source.asked=time()
                send("J",source.group,source.peer,{})
            end
            return true
        end
    end
end
local function parseMetadata(words)
    if #words~=12 or not validID(words[4]) or not words[5] or #words[5]>64
        or words[5]:find(S.CONTROL_OR_PIPE) or not words[5]:match("^[^%-]+%-[^%-]+$") then return nil end
    local revision,at=tonumber(words[6]),E.part("t",words[7])
    if not revision or not words[6]:match("^%d+$") or revision<1 or revision>=1e12 or not at
        or (words[8]~="0" and words[8]~="1") then return nil end
    local meta={owner=words[4],name=words[5]:gsub("_"," "),revision=revision,at=at,hidden=words[8]=="1"}
    if not meta.hidden then
        local sex,level=tonumber(words[10]),tonumber(words[12])
        if not words[9]:match("^[A-Za-z][A-Za-z]+$") or #words[9]>24 or (sex~=2 and sex~=3)
            or not CLASSES[words[11]] or not level or level~=math.floor(level) or level<1
            or level>(WoWStatusAdapter.max_level or 60) then return nil end
        meta.race,meta.sex,meta.class,meta.level=words[9],sex,words[11],level
    elseif words[9]~="-" or words[10]~="-" or words[11]~="-" or words[12]~="-" then return nil end
    return meta
end
function G.receive(words,sender)
    if not db or touring() then return false end
    local op,group,pid=words[1],words[2],words[3]
    if not selected(group) or not validID(pid) or pid==id() then return false end
    if op=="J" and #words==3 then
        local before=current.equipment_profile and current.equipment_profile.revision
        E.capture(current)
        if current.equipment_profile and current.equipment_profile.revision~=before then dirty[current]=time() end
        local k="inventory:"..group..":"..(key(sender) or "")
        if answered[k] and time()-answered[k]<15 then return false end
        answered[k]=time(); trim(answered,128)
        return inventory(group,sender)
    end
    if op=="H" then
        local meta=parseMetadata(words)
        if not meta or meta.owner==id() then return false end
        local k=recordKey(meta.owner,meta.name)
        local old,offer=cache()[k],offers[k]
        if old and old.withdrawn and not meta.hidden and pid~=meta.owner then return false end
        if old and not same(meta,old) and not G.newer(meta,old) then return false end
        if offer and not same(meta,offer.meta) and not G.newer(meta,offer.meta) then return false end
        if meta.hidden then
            for token,request in pairs(pending) do if request.record==k then pending[token]=nil end end
            offers[k]=nil
            return store(meta,group)
        end
        if same(meta,old) and old.snapshot then
            if pid==meta.owner then old.withdrawn=nil end
            if meta.at>old.at then old.at,old.snapshot.at=meta.at,meta.at end
            old.groups[group]=true
            notify()
            -- Remember a provider so an explicit refresh can ask for new stats.
        end
        if not offer or not same(meta,offer.meta) then
            for token,request in pairs(pending) do if request.record==k then pending[token]=nil end end
            offer={meta=meta,sources={},at=time(),need=not (same(meta,old) and old.snapshot)}
            offers[k]=offer; trim(offers,MAX_CACHE)
        end
        offer.at=time()
        if meta.at>offer.meta.at then offer.meta.at=meta.at end
        local found=false
        for _, source in ipairs(offer.sources) do
            if source.group==group and key(source.peer)==key(sender) then source.at=time(); found=true end
        end
        if not found and (#offer.sources<4 or pid==meta.owner) then
            local source={group=group,peer=sender,pid=pid,at=time()}
            if pid==meta.owner then
                if #offer.sources>=4 then table.remove(offer.sources) end
                table.insert(offer.sources,1,source)
            else offer.sources[#offer.sources+1]=source end
        end
        notify()
        return true
    end
    if op=="F" and #words==7 then
        local token,owner,name,revision=words[4],words[5],words[6],tonumber(words[7])
        if #token~=8 or not token:match("^[0-9a-f]+$") or not validID(owner) or not name or #name>64
            or name:find(S.CONTROL_OR_PIPE) or not name:match("^[^%-]+%-[^%-]+$") or not revision
            or not words[7]:match("^%d+$") or revision<1 or revision>=1e12 then return false end
        name=name:gsub("_"," ")
        local record
        if owner==id() then
            for _, character in pairs(db.characters or {}) do
                if key(WoWStatusPopups.characterName(character))==key(name) then
                    if character==current then E.capture(character) end
                    record=ownRecord(character); break
                end
            end
        else
            local candidate=cache()[recordKey(owner,name)]
            if candidate and candidate.groups[group] and not WoWStatusRoster.isHidden(name) then record=candidate end
        end
        if not record then return false end
        if record.hidden or record.revision~=revision then metadata(record,group,sender); return true end
        local k="data:"..group..":"..(key(sender) or "")..":"..recordKey(owner,name)
        local rate=k..":"..revision
        if answered[rate] and time()-answered[rate]<15 then return false end
        if not jobs[k] and count(jobs)>=MAX_JOBS then return false end
        if not record.snapshot then return false end
        answered[rate]=time(); trim(answered,128)
        local parts=E.parts(record.snapshot)
        local average=S.number(record.snapshot.average_item_level)
        parts[#parts+1]={"l",average and tostring(math.floor(average*100)) or "-"}
        jobs[k]={group=group,peer=sender,parts=parts,token=token,index=1,at=time(),own=record.own}
        return true
    end
    if op=="T" and #words==6 then
        local token,part=words[4],words[5]
        local request=pending[token]
        if not request or request.pid~=pid or request.group~=group or key(request.peer)~=key(sender)
            or time()-request.at>=180 then return false end
        local value=E.part(part,words[6])
        if value==nil or value==false or part=="x" or part=="n" then return false end
        if request.parts[part] then return true end
        request.parts[part],request.count,request.last=value,request.count+1,time()
        if request.count<24 then return true end
        pending[token]=nil
        local offer=offers[request.record]
        if not offer or not same(offer.meta,request.meta) then return false end
        local snapshot={at=math.max(request.parts.t,offer.meta.at),revision=request.meta.revision,items={},stats={}}
        snapshot.average_item_level=type(request.parts.l)=="number" and request.parts.l/100 or nil
        for slot=0,19 do snapshot.items[slot]=request.parts[tostring(slot)] end
        for _, block in ipairs({"a","b"}) do for field,n in pairs(request.parts[block]) do snapshot.stats[field]=n end end
        local meta=request.meta
        meta.snapshot,meta.at=snapshot,snapshot.at
        offer.need=false
        return store(meta,group)
    end
    return false
end
function G.tick()
    if not db or touring() then return end
    local stamp=time()
    for token,request in pairs(pending) do
        if not selected(request.group) or stamp-request.at>=180 or (request.count==0 and stamp-request.at>=30) then pending[token]=nil end
    end
    for character,due in pairs(dirty) do
        if stamp>=due then
            dirty[character]=nil
            local record=ownRecord(character)
            if record then
                for group in pairs(WoWStatusGroups.selected(current)) do
                    for _, peer in ipairs(peers(group)) do
                        local k="change:"..group..":"..(key(peer) or "")..":"..recordKey(record.owner,record.name)
                        if jobs[k] or count(jobs)<MAX_JOBS then jobs[k]={group=group,peer=peer,records={record},index=1,at=stamp}
                        else dirty[character]=stamp+2 end
                    end
                end
            end
        end
    end
    -- Responses take priority over inventories, and only a small window enters
    -- the shared send queue. The remaining work stays as bounded compact jobs.
    for pass=1,2 do
        for k,job in pairs(jobs) do
            if not selected(job.group) or stamp-job.at>300 then jobs[k]=nil
            elseif (job.parts~=nil)==(pass==1) and WoWStatusRoster.equipmentQueueSize()<32 then
                local ok
                if job.parts then
                    local part=job.parts[job.index]
                    ok=part and send("T",job.group,job.peer,{job.token,part[1],part[2]},job.own)
                else
                    local record=job.records[job.index]
                    ok=record and metadata(record,job.group,job.peer)
                end
                if ok then job.index=job.index+1 end
                if job.index>#(job.parts or job.records) then jobs[k]=nil end
            end
        end
    end
    local busy={}
    for _,request in pairs(pending) do busy[request.record]=true end
    if count(pending)>=MAX_PENDING then return end
    for k,offer in pairs(offers) do
        if offer.need and not busy[k] and WoWStatusRoster.equipmentQueueSize()<32 then
            for offset=0,#offer.sources-1 do
                local index=((offer.next or 1)+offset-1)%#offer.sources+1
                local source=offer.sources[index]
                local online=stamp-source.at<300
                if not online and selected(source.group) then
                    for _,peer in ipairs(peers(source.group)) do if key(peer)==key(source.peer) then online=true; break end end
                end
                if selected(source.group) and online and (not source.last or stamp-source.last>=30) then
                    local token=string.format("%08x",math.random(0,1073741823))
                    if send("F",source.group,source.peer,{token,offer.meta.owner,offer.meta.name:gsub(" ","_"),offer.meta.revision}) then
                        source.last=stamp
                        offer.next=index%#offer.sources+1
                        pending[token]={record=k,meta=offer.meta,pid=source.pid,peer=source.peer,group=source.group,
                            at=stamp,last=stamp,parts={},count=0}
                    end
                    break
                end
            end
        end
        if count(pending)>=MAX_PENDING then break end
    end
end
function G.init(database,character,sender)
    db,current,transport=database,character,sender
    jobs,hello,offers,pending,answered,dirty={},{},{},{},{},{}
    db.roster.equipment_cache=type(db.roster.equipment_cache)=="table" and db.roster.equipment_cache or {}
    trim(cache(),MAX_CACHE)
end
