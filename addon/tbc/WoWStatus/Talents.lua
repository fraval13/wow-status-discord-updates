-- Read-only talent snapshots. Only the owner's public, committed talent data
-- is captured; viewing a friend's build never changes the viewer's talents.
WoWStatusTalents = {}
local M, S = WoWStatusTalents, WoWStatusSafe
local T, TF = WoWStatusLocale.T, WoWStatusLocale.F
local db, current, send
local pending, asked, answered, jobs = {}, {}, {}, {}
local capabilities,helloAt={},{}
local lastPartAt,jobCursor=-2,0
local MAX_NODES, MAX_BYTES, CHUNK, MAX_PARTS = 384, 16384, 144, 128
-- Four full replies, paced every two seconds in an instance, need up to
-- 4 * 128 * 2 seconds; leave room for the shared transport queue as well.
local TRANSFER_AGE=1200
local function number(v, low, high)
    v=S.number(v)
    return v and v==math.floor(v) and v>=low and v<=high and v or nil
end
local function size(map) local n=0; for _ in pairs(map) do n=n+1 end; return n end
local function key(name) return WoWStatusRoster.key(name) end
local function trim(map, maximum)
    while size(map)>maximum do
        local oldest,at
        for k,v in pairs(map) do local stamp=type(v)=="table" and v.at or v; if not at or stamp<at then oldest,at=k,stamp end end
        if not oldest then break end; map[oldest]=nil
    end
end
local function hex(text) return (text:gsub(".",function(c) return string.format("%02x",c:byte()) end)) end
local function unhex(text, maximum)
    if type(text)~="string" or #text>maximum*2 or #text%2~=0 or text:find("[^0-9a-f]") then return nil end
    local value=text:gsub("..",function(c) return string.char(tonumber(c,16)) end)
    return not value:find(S.CONTROL_OR_PIPE) and value or nil
end
local function split(text, separator)
    local list={}
    for word in (text..separator):gmatch("(.-)"..separator) do list[#list+1]=word end
    return list
end
local function icon(value)
    value=S.texture(value)
    if type(value)=="number" then return number(value,1,1000000000) and tostring(value) end
    if type(value)=="string" and #value<=100 and value:match("^[A-Za-z0-9_\\/]+$") then return value end
end
local function spellInfo(id)
    if C_Spell and C_Spell.GetSpellInfo then
        local info=S.call(C_Spell.GetSpellInfo,id)
        if type(info)=="table" then return S.string(info.name),S.texture(info.iconID),number(info.spellID,1,1000000000) end
    end
    if type(GetSpellInfo)=="function" then
        local ok,name,_,texture,_,_,_,spell=pcall(GetSpellInfo,id)
        if ok then return S.string(name),S.texture(texture),number(spell,1,1000000000) end
    end
end
local function own(name)
    if not db then return nil end
    for _,c in pairs(db.characters or {}) do
        if c.identity and c.identity.client==WoWStatusAdapter.client_id and key(WoWStatusPopups.characterName(c))==key(name) then return c end
    end
end
local function modern()
    if not C_ClassTalents or not C_Traits then return nil end
    local config=number(S.call(C_ClassTalents.GetActiveConfigID),1,1000000000)
    if not config then return nil end
    if C_Traits.ConfigHasStagedChanges and S.call(C_Traits.ConfigHasStagedChanges,config)~=false then return nil end
    local info=S.call(C_Traits.GetConfigInfo,config)
    if type(info)~="table" then return nil end
    local getSpec=(C_SpecializationInfo and C_SpecializationInfo.GetSpecialization) or GetSpecialization
    local index=number(S.call(getSpec),1,10)
    local getInfo=(C_SpecializationInfo and C_SpecializationInfo.GetSpecializationInfo) or GetSpecializationInfo
    local spec,title=S.call(getInfo,index)
    local build={mode="modern",spec=number(spec,1,1000000) or 0,labels={S.string(title) or ""},nodes={},edges={}}
    local seen={}
    local trees=S.value(info.treeIDs)
    if type(trees)~="table" then return nil end
    for _,tree in ipairs(trees) do
        local ids=S.call(C_Traits.GetTreeNodes,tree)
        if type(ids)~="table" or #ids>2048 then return nil end
        for _,id in ipairs(ids) do
            local node=S.call(C_Traits.GetNodeInfo,config,id)
            if type(node)~="table" then return nil end
            if issecretvalue and issecretvalue(node.isVisible) then return nil end
            if S.value(node.isVisible)~=false then
                local active=S.value(node.activeEntry)
                local entryID=type(active)=="table" and number(active.entryID,1,1000000000)
                    or (type(S.value(node.entryIDs))=="table" and number(node.entryIDs[1],1,1000000000))
                local entry=entryID and S.call(C_Traits.GetEntryInfo,config,entryID)
                local def=type(entry)=="table" and number(entry.definitionID,1,1000000000)
                def=def and S.call(C_Traits.GetDefinitionInfo,def)
                local spell=type(def)=="table" and number(def.spellID,1,1000000000) or 0
                local _,texture=spellInfo(spell)
                texture=type(def)=="table" and S.texture(def.overrideIcon) or texture
                local rank=number(node.currentRank,0,255) or (type(active)=="table" and number(active.rank,0,255)) or number(node.ranksPurchased,0,255)
                local maximum=number(node.maxRanks,0,255) or (type(entry)=="table" and number(entry.maxRanks,0,255))
                local x,y=S.number(node.posX),S.number(node.posY)
                if not number(id,1,1000000000) or not x or not y or math.abs(x)>1000000 or math.abs(y)>1000000 or not rank or not maximum then return nil end
                if not seen[id] then
                    build.nodes[#build.nodes+1]={id=id,spell=spell or 0,icon=icon(texture) or "Interface\\Icons\\INV_Misc_QuestionMark",
                        x=math.floor(x),y=math.floor(y),rank=rank,max=math.max(rank,maximum),tree=1,spent=number(node.ranksPurchased,0,255) or rank,name=""}
                    seen[id]=true
                    if type(S.value(node.visibleEdges))=="table" then
                        for _,edge in ipairs(node.visibleEdges) do
                            edge=S.value(edge)
                            local target=type(edge)=="table" and number(edge.targetNode,1,1000000000)
                            if target and #build.edges<512 then build.edges[#build.edges+1]={id,target} end
                        end
                    end
                end
            end
        end
    end
    for i=#build.edges,1,-1 do if not seen[build.edges[i][2]] then table.remove(build.edges,i) end end
    return #build.nodes>0 and #build.nodes<=MAX_NODES and build or nil
end
local function classic()
    local tabs=number(S.call(GetNumTalentTabs),1,3)
    if not tabs or type(GetTalentInfo)~="function" then return nil end
    local build={mode="classic",spec=0,labels={},nodes={},edges={}}
    local grid, prerequisites={},{}
    for tab=1,tabs do
        local title=S.string(S.call(GetTalentTabInfo,tab,false,false))
        local count=number(S.call(GetNumTalents,tab,false,false),0,100)
        if not title or #title>80 or not count then return nil end
        build.labels[tab]=title
        for index=1,count do
            local ok,name,texture,tier,column,rank,maximum=pcall(GetTalentInfo,tab,index,false,false)
            name,texture=S.string(name),icon(texture)
            tier,column,rank,maximum=number(tier,1,15),number(column,1,5),number(rank,0,255),number(maximum,1,255)
            if not ok or not name or #name>120 or not texture or not tier or not column or not rank or not maximum or rank>maximum then return nil end
            local _,_,spell=spellInfo(name)
            local id=tab*1000+index
            build.nodes[#build.nodes+1]={id=id,spell=spell or 0,icon=texture,x=(tab-1)*5+column,y=tier,rank=rank,max=maximum,tree=tab,spent=rank,name=spell and "" or name}
            grid[tab..":"..tier..":"..column]=id
            if type(GetTalentPrereqs)=="function" then
                local result={pcall(GetTalentPrereqs,tab,index,false,false)}
                if result[1] then
                    for at=2,13,3 do
                        local row,col=number(result[at],1,15),number(result[at+1],1,5)
                        if row and col then prerequisites[#prerequisites+1]={tab,row,col,id} end
                    end
                end
            end
        end
    end
    for _,p in ipairs(prerequisites) do local from=grid[p[1]..":"..p[2]..":"..p[3]]; if from then build.edges[#build.edges+1]={from,p[4]} end end
    return #build.nodes>0 and #build.nodes<=MAX_NODES and build or nil
end
function M.encode(build)
    local labels,nodes,edges={},{},{}
    for _,label in ipairs(build.labels) do labels[#labels+1]=hex(label) end
    for _,n in ipairs(build.nodes) do
        nodes[#nodes+1]=table.concat({n.id,n.spell,n.icon,n.x,n.y,n.rank,n.max,n.tree,n.spent,hex(n.name or "")},",")
    end
    for _,e in ipairs(build.edges) do edges[#edges+1]=e[1]..","..e[2] end
    return table.concat({"1",build.mode,build.class,build.spec,build.level,table.concat(labels,":"),table.concat(nodes,";"),table.concat(edges,";")},"|")
end
function M.decode(text)
    if type(text)~="string" or #text>MAX_BYTES then return nil end
    local words=split(text,"|")
    if #words~=8 or words[1]~="1" or (words[2]~="classic" and words[2]~="modern") then return nil end
    local build={mode=words[2],class=number(tonumber(words[3]),1,13),spec=number(tonumber(words[4]),0,1000000),
        level=number(tonumber(words[5]),1,1000),labels={},nodes={},edges={}}
    if not build.class or not build.spec or not build.level then return nil end
    for _,label in ipairs(split(words[6],":")) do
        label=unhex(label,80); if not label or #build.labels>=3 then return nil end; build.labels[#build.labels+1]=label
    end
    local seen={}
    for _,line in ipairs(split(words[7],";")) do
        local w=split(line,",")
        if #w~=10 or #build.nodes>=MAX_NODES then return nil end
        local n={id=number(tonumber(w[1]),1,1000000000),spell=number(tonumber(w[2]),0,1000000000),icon=icon(w[3]),
            x=number(tonumber(w[4]),-1000000,1000000),y=number(tonumber(w[5]),-1000000,1000000),
            rank=number(tonumber(w[6]),0,255),max=number(tonumber(w[7]),1,255),tree=number(tonumber(w[8]),1,3),
            spent=number(tonumber(w[9]),0,255),name=unhex(w[10],120)}
        if not n.id or seen[n.id] or not n.spell or not n.icon or not n.x or not n.y or not n.rank or not n.max
            or n.rank>n.max or not n.tree or n.tree>#build.labels or not n.spent or n.spent>n.max or not n.name then return nil end
        seen[n.id]=true; build.nodes[#build.nodes+1]=n
    end
    if words[8]~="" then
        for _,line in ipairs(split(words[8],";")) do
            local a,b=line:match("^(%d+),(%d+)$"); a,b=tonumber(a),tonumber(b)
            if not a or not seen[a] or not seen[b] or a==b or #build.edges>=512 then return nil end
            build.edges[#build.edges+1]={a,b}
        end
    end
    return #build.nodes>0 and build or nil
end
function M.capture(character)
    if not db or character~=current or (WoWStatusGuide and WoWStatusGuide.touring()) then return character and character.talent_profile end
    if not (character.settings and character.settings.fields and character.settings.fields.gear) then character.talent_profile=nil; return nil end
    local build
    if WoWStatusAdapter.client_id=="retail" or WoWStatusAdapter.client_id=="forever" then build=modern() else build=classic() end
    local _,_,class=S.call(UnitClass,"player")
    local level=WoWStatusAdapter.level()
    if not build or not number(class,1,13) or not level then return character.talent_profile end
    build.class,build.level=class,level
    local encoded=M.encode(build)
    if not M.decode(encoded) then return character.talent_profile end
    local old=character.talent_profile
    if old and old.encoded==encoded then return old end
    build.at,build.encoded=math.floor(S.now()),encoded
    character.talent_profile=build
    return build
end
function M.forget(owner,name)
    if not db then return end
    for k,r in pairs(db.roster.talent_cache) do if r.owner==owner and (not name or key(r.name)==key(name)) then db.roster.talent_cache[k]=nil end end
    for token,r in pairs(pending) do if r.owner==owner and (not name or key(r.name)==key(name)) then pending[token]=nil end end
end
function M.get(name)
    local character=own(name)
    if character then
        if not character.settings.fields.gear then return nil,"off" end
        if character==current then M.capture(character) end
        if not character.talent_profile then return nil,character==current and "unavailable" or "login" end
        return character.talent_profile
    end
    if not db or WoWStatusRoster.isHidden(name) then return nil,"off" end
    local _,hidden=WoWStatusRoster.equipment(name)
    if hidden then return nil,"off" end
    local best
    for _,r in pairs(db.roster.talent_cache) do
        if key(r.name)==key(name) then
            for group in pairs(r.groups or {}) do
                if WoWStatusGroups.contains(current,group) and (not best or r.at>best.at) then best=r end
            end
        end
    end
    return best and best.snapshot,best and best.reason
end
function M.waiting(name)
    for _,r in pairs(pending) do if key(r.name)==key(name) then return true end end
    return false
end
function M.request(name)
    if not db or (WoWStatusGuide and WoWStatusGuide.touring()) then return false end
    local character=own(name)
    if character then if character==current then M.capture(character) end; return true end
    if WoWStatusRoster.isHidden(name) or size(pending)>=4 then return false end
    local wanted=key(name)
    for pid,player in pairs(db.roster.players or {}) do
        local c=player.characters and player.characters[wanted or ""]
        local requestKey=pid..":"..(wanted or "")
        if c and (not asked[requestKey] or S.uptime()-asked[requestKey]>=30) then
            for group in pairs(player.groups or {}) do
                if WoWStatusGroups.contains(current,group) then
                    local peers=WoWStatusPopups.peers(group)
                    if #peers==0 then peers=WoWStatusRoster.recentMembers(group) end
                    for _,peer in ipairs(peers) do
                        if player.characters[key(peer) or ""] then
                            local token=string.format("%08x",math.random(0,1073741823))
                            if send(group,peer,table.concat({"B",group,db.roster.id,"R",c.name:gsub(" ","_"),token}," ")) then
                                for old,r in pairs(pending) do if r.owner==pid and key(r.name)==wanted then pending[old]=nil end end
                                pending[token]={owner=pid,name=c.name,group=group,peer=key(peer),at=S.uptime(),parts={},count=0}
                                asked[requestKey]=S.uptime();trim(asked,128);return true
                            end
                        end
                    end
                end
            end
        end
    end
    return false
end
local function refresh()
    if WoWStatusProfile and WoWStatusProfile.refreshEquipment then WoWStatusProfile.refreshEquipment() end
end
-- Advertise protocol support before sending continuous location traffic.
function M.hello(group,peer,reply)
    if not db or (WoWStatusGuide and WoWStatusGuide.touring()) or WoWStatusPopups.isSelf(peer) then return false end
    local k=group..":"..(key(peer) or "")
    if helloAt[k] and S.uptime()-helloAt[k]<(reply and 5 or 120) then return false end
    if send(group,peer,table.concat({"B",group,db.roster.id,"C"}," ")) then
        helloAt[k]=S.uptime();trim(helloAt,128);return true
    end
    return false
end
function M.canMap(group,peer)
    local c=capabilities[group..":"..(key(peer) or "")]
    return c~=nil and S.uptime()-c.at<180
end
function M.receive(w,sender)
    if not db or (WoWStatusGuide and WoWStatusGuide.touring()) then return false end
    local op,group,pid=w[4],w[2],w[3]
    if op=="C" and #w==4 then
        capabilities[group..":"..(key(sender) or "")]={owner=pid,at=S.uptime()}
        trim(capabilities,128);M.hello(group,sender,true);return true
    end
    if op=="R" and #w==6 then
        local name,token=w[5],w[6]
        if #name>64 or name:find(S.CONTROL_OR_PIPE) or not name:match("^[^%-]+%-[^%-]+$") or not token:match("^[0-9a-f]+$") or #token~=8 then return false end
        name=name:gsub("_"," ")
        local c=own(name);if not c then return false end
        local rate=(key(sender) or "")..":"..(key(name) or "")
        if answered[rate] and S.uptime()-answered[rate]<15 then return false end
        if not db.roster.share or c.hide_from_list or not c.settings.fields.gear then
            local ok=send(group,sender,table.concat({"B",group,db.roster.id,"X",token,"off"}," "))
            if ok then answered[rate]=S.uptime();trim(answered,128) end;return ok
        end
        local build=c==current and M.capture(c) or c.talent_profile
        if not build or not build.encoded or not M.decode(build.encoded) then
            local ok=send(group,sender,table.concat({"B",group,db.roster.id,"X",token,"unavailable"}," "))
            if ok then answered[rate]=S.uptime();trim(answered,128) end;return ok
        end
        if size(jobs)>=4 then return false end
        answered[rate]=S.uptime();trim(answered,128)
        local parts=math.ceil(#build.encoded/CHUNK)
        if parts<1 or parts>MAX_PARTS then return false end
        jobs[(key(sender) or "")..":"..token]={group=group,peer=sender,token=token,owner=c,body=build.encoded,stamp=build.at,parts=parts,index=1,at=S.uptime()}
        return true
    end
    local token=w[5]
    local r=token and pending[token]
    if not r or r.owner~=pid or r.group~=group or r.peer~=key(sender) or S.uptime()-r.at>TRANSFER_AGE then return false end
    if op=="X" and #w==6 and (w[6]=="off" or w[6]=="unavailable") then
        pending[token]=nil
        db.roster.talent_cache[pid..":"..key(r.name)]={owner=pid,name=r.name,at=S.now(),groups={[group]=true},reason=w[6]}
        trim(db.roster.talent_cache,64);refresh();return true
    end
    if op~="D" or #w~=9 then return false end
    local part,total,stamp=number(tonumber(w[6]),1,MAX_PARTS),number(tonumber(w[7]),1,MAX_PARTS),number(tonumber(w[8]),1,100000000000)
    local body=w[9]
    if not part or not total or part>total or not stamp or stamp>S.now()+300 or #body>CHUNK or body:find(S.CONTROL) then return false end
    if r.total and (r.total~=total or r.stamp~=stamp) then pending[token]=nil;return false end
    r.total,r.stamp=total,stamp
    if r.parts[part] then return r.parts[part]==body end
    r.parts[part],r.count=body,r.count+1
    if r.count<total then return true end
    pending[token]=nil
    local text=table.concat(r.parts)
    local build=M.decode(text)
    if not build then return false end
    build.at,build.encoded=stamp,text
    local k=pid..":"..key(r.name)
    local old=db.roster.talent_cache[k]
    if old and old.snapshot and old.at>stamp then return false end
    local groups=old and old.groups or {};groups[group]=true
    db.roster.talent_cache[k]={owner=pid,name=r.name,at=stamp,snapshot=build,groups=groups}
    trim(db.roster.talent_cache,64);refresh();return true
end
function M.tick()
    if not db or (WoWStatusGuide and WoWStatusGuide.touring()) then return end
    local expired=false
    for token,r in pairs(pending) do
        local initial=M.canMap(r.group,r.peer) and 120 or 30
        if S.uptime()-r.at>TRANSFER_AGE or (r.count==0 and S.uptime()-r.at>initial) or not WoWStatusGroups.contains(current,r.group) then pending[token]=nil;expired=true end
    end
    if expired then refresh() end
    local ready={}
    for k,job in pairs(jobs) do
        if S.uptime()-job.at>TRANSFER_AGE or not WoWStatusGroups.contains(current,job.group) or not db.roster.share or job.owner.hide_from_list or not job.owner.settings.fields.gear then jobs[k]=nil
        else ready[#ready+1]=k end
    end
    table.sort(ready)
    -- One fragment per second leaves room for gear and milestone traffic;
    -- instanced addon traffic has a lower native budget, so use two seconds.
    local interval=S.call(IsInInstance)==true and 2 or 1
    if #ready==0 or S.uptime()-lastPartAt<interval or WoWStatusRoster.equipmentQueueSize()>=32 then return end
    jobCursor=jobCursor%#ready+1
    local k=ready[jobCursor]
    local job=jobs[k]
    local fragment=job.body:sub((job.index-1)*CHUNK+1,job.index*CHUNK)
    if send(job.group,job.peer,table.concat({"B",job.group,db.roster.id,"D",job.token,job.index,job.parts,job.stamp,fragment}," "),"gear",job.owner) then
        lastPartAt=S.uptime();job.index=job.index+1;if job.index>job.parts then jobs[k]=nil end
    end
end
function M.init(database,character,transport)
    db,current,send=database,character,transport
    pending,asked,answered,jobs={},{},{},{}
    capabilities,helloAt={},{};lastPartAt,jobCursor=-2,0
    db.roster.talent_cache=type(db.roster.talent_cache)=="table" and db.roster.talent_cache or {}
    for k,r in pairs(db.roster.talent_cache) do
        if type(r)~="table" or not S.number(r.at) or type(r.groups)~="table" or type(r.name)~="string" or type(r.owner)~="string" then db.roster.talent_cache[k]=nil
        elseif r.snapshot then
            local snapshot=type(r.snapshot)=="table" and M.decode(r.snapshot.encoded)
            if not snapshot then db.roster.talent_cache[k]=nil
            else snapshot.at,snapshot.encoded=r.at,r.snapshot.encoded;r.snapshot=snapshot end
        end
    end
    trim(db.roster.talent_cache,64);M.capture(current)
end
function M.build(parent)
    local UI=WoWStatusUI
    local box=UI.box(parent,710,100)
    UI.header(box,T("Talents"),12,-10,550)
    box.status=UI.text(box,"GameFontHighlightSmall",12,-36,550)
    box.refresh=CreateFrame("Button",nil,box,"UIPanelButtonTemplate")
    box.refresh:SetPoint("TOPRIGHT",-12,-10);box.refresh:SetSize(130,24);box.refresh:SetText(T("Refresh talents"))
    box.refresh:SetScript("OnClick",function() if box.character then M.request(box.character);refresh() end end)
    box.canvas=CreateFrame("Frame",nil,box);box.canvas:SetPoint("TOPLEFT",12,-72);box.canvas:SetSize(686,1)
    box.nodes,box.lines,box.labels={},{},{}
    return box
end
function M.render(box,name)
    local UI=WoWStatusUI
    box.character=name
    local build,reason=M.get(name)
    local status=build and (T("Last reported:").." "..WoWStatusHistory.localTime(build.at))
        or T(M.waiting(name) and "Requesting talents…" or reason=="off" and "Equipment sharing is off."
            or reason=="login" and "Log into this character to capture its talents."
            or reason=="unavailable" and "Talents are not available for this character yet."
            or "No talent snapshot yet. Their owner needs the updated addon.")
    box.status:SetText(status)
    for _,node in ipairs(box.nodes) do node:Hide() end
    for _,line in ipairs(box.lines) do line:Hide() end
    for _,label in ipairs(box.labels) do label:Hide() end
    if not build then box:SetHeight(86);return 86 end
    local minX,maxX,minY,maxY=math.huge,-math.huge,math.huge,-math.huge
    local points=0
    for _,n in ipairs(build.nodes) do minX,maxX=math.min(minX,n.x),math.max(maxX,n.x);minY,maxY=math.min(minY,n.y),math.max(maxY,n.y);points=points+n.spent end
    local height=build.mode=="classic" and math.max(420,(maxY-minY+1)*48+40) or math.max(440,math.min(1400,(maxY-minY)/math.max(1,maxX-minX)*630+80))
    box.canvas:SetHeight(height)
    local byID={}
    for i,n in ipairs(build.nodes) do
        local node=box.nodes[i]
        if not node then
            node=CreateFrame("Button",nil,box.canvas);node:SetSize(28,28)
            node.icon=node:CreateTexture(nil,"ARTWORK");node.icon:SetAllPoints()
            node.rank=UI.text(node,"GameFontNormalSmall",-5,-25,38,"CENTER")
            local function tooltip(self)
                if not GameTooltip or not self.data then return end
                GameTooltip:SetOwner(self,"ANCHOR_RIGHT")
                local shown=self.data.spell>0 and GameTooltip.SetSpellByID and pcall(GameTooltip.SetSpellByID,GameTooltip,self.data.spell)
                if not shown then GameTooltip:SetText(self.data.name~="" and self.data.name or T("Talent node")) end
                GameTooltip:AddLine(TF("Rank %d of %d",self.data.rank,self.data.max),1,.82,0);GameTooltip:Show()
            end
            node:SetScript("OnEnter",tooltip);node:SetScript("OnClick",tooltip)
            node:SetScript("OnLeave",function() if GameTooltip then GameTooltip:Hide() end end)
            box.nodes[i]=node
        end
        local x=(n.x-minX)/math.max(1,maxX-minX)*630+14
        local y=(n.y-minY)/math.max(1,maxY-minY)*(height-70)+24
        node:ClearAllPoints();node:SetPoint("TOPLEFT",x,-y);node.data=n
        local _,texture=spellInfo(n.spell)
        node.icon:SetTexture(tonumber(n.icon) or n.icon or texture)
        UI.call(node.icon,"SetDesaturated",n.rank==0);node.icon:SetAlpha(n.rank>0 and 1 or .45)
        node.rank:SetText(n.rank.."/"..n.max);node:Show();byID[n.id]=node
    end
    for i,label in ipairs(build.labels) do
        local text=box.labels[i]
        if not text then text=UI.text(box.canvas,"GameFontNormal",0,0,210,"CENTER");box.labels[i]=text end
        text:ClearAllPoints();text:SetPoint("TOPLEFT",(i-1)*228,0);text:SetText(label:gsub("|","||"));text:Show()
    end
    if box.canvas.CreateLine then
        for i,e in ipairs(build.edges) do
            if byID[e[1]] and byID[e[2]] then
                local line=box.lines[i] or box.canvas:CreateLine(nil,"BACKGROUND");box.lines[i]=line
                line:SetThickness(1);line:SetColorTexture(.65,.5,.18,.8)
                line:SetStartPoint("CENTER",byID[e[1]]);line:SetEndPoint("CENTER",byID[e[2]]);line:Show()
            end
        end
    end
    box.status:SetText(status.." · "..TF("%d talent points",points))
    box:SetHeight(height+88);return height+88
end
local driver=CreateFrame("Frame")
local dirty,elapsed=false,0
for _,event in ipairs({"PLAYER_ENTERING_WORLD","PLAYER_TALENT_UPDATE","CHARACTER_POINTS_CHANGED","ACTIVE_TALENT_GROUP_CHANGED","TRAIT_CONFIG_UPDATED","ACTIVE_COMBAT_CONFIG_CHANGED"}) do
    if not C_EventUtils or not C_EventUtils.IsEventValid or S.call(C_EventUtils.IsEventValid,event)==true then pcall(driver.RegisterEvent,driver,event) end
end
driver:SetScript("OnEvent",function() dirty=true end)
driver:SetScript("OnUpdate",function(_,delta)
    elapsed=elapsed+delta;if elapsed<1 then return end;elapsed=0
    if dirty and current then dirty=false;M.capture(current);refresh() end
end)
