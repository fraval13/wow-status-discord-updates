-- Bounded, group-scoped peer anti-entropy: catching up on the log with the
-- other members online, and the J2 wire format it uses. Part of
-- WoWStatusJournal; see JournalStore.lua, which loads first.
local J, S, P = WoWStatusJournal, WoWStatusSafe, WoWStatusPopups
local I = J.internal
local PREFIX, CAP, AGE, PAGE = I.PREFIX, I.CAP, I.AGE, I.PAGE
local sharedKinds, achievementID, digest, digestFor = I.sharedKinds, I.achievementID, I.digest, I.digestFor
local groupMember, groupSince, peer, offerable, relayed, add =
    I.groupMember, I.groupSince, I.peer, I.offerable, I.relayed, I.add
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
-- Catch-up one member can deliver per login session: at most RELAY_CAP new
-- entries fetched from it, at most SENDER_CAP of them naming one other member (#4).
local RELAY_CAP, SENDER_CAP = 300, 100
-- A member's hello starts a pull at most once per HELLO_INTERVAL seconds of game
-- uptime in one group; a newer hello within it waits for the interval and for
-- any running pull from that member to end (#4).
local HELLO_INTERVAL = 600
local budgets = {}
local lastQuery = {}
-- An achievement travels as its ID alone: the receiver names it itself (#165).
local function pack(e)
    local text=e.kind=="achievement" and tostring(achievementID(e) or "") or e.text
    local values={e.id,e.client,e.sender,tostring(e.at),e.kind,e.level and tostring(e.level) or "",text,e.quality and tostring(e.quality) or "",e.class_id and tostring(e.class_id) or "",e.equip_loc or "",e.item_id and tostring(e.item_id) or ""}
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
    -- An unknown or malformed achievement ID is an ordinary drop (#165).
    local achievement
    if kind=="achievement" then
        achievement=WoWStatusAchievements.id(detail)
        detail=achievement and WoWStatusAchievements.text(achievement)
        if not detail then return nil end
    end
    if not J.validText(kind,detail,level) then return nil,"invalid" end
    local e={id=id,client=client,sender=sender,at=at,kind=kind,level=level,text=detail,groups={},origin="catchup",
        quality=tonumber(values[8]),class_id=tonumber(values[9]),equip_loc=values[10],item_id=tonumber(values[11]),
        achievement_id=achievement}
    if kind=="loot" and (not detail:match("^Equipped ") or not e.item_id or not WoWStatusLoot.allowed(I.current.settings,e)) then return nil end
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
    serial=serial+1;I.db.journal.request_serial=serial;return S.now().."-"..serial
end
-- JournalStore.lua calls these when the log changes under the catch-up.
-- J.init: a new session for the database just loaded.
function I.syncInit()
    requests,sessions,sendQueue,cursors,rates={},{},{},{},{}
    serial=I.db.journal.request_serial or 0
    lastQuery={}
    lastSend,allowance,allowanceAt,holdUntil,pacing=0,ALLOWANCE,0,0,{};loginNonce=token()
    jobs,queuedJobs,contacted,hellos,seenHello,budgets={},{},{},{},{},{}
end
-- J.groupsChanged: start over, greeting the members of the groups now joined.
function I.syncGroupsChanged()
    requests,sessions,sendQueue,cursors={},{},{},{}
    jobs,queuedJobs,contacted,hellos={},{},{},{};loginUntil=S.uptime()+60
end
-- J.privacyChanged: nothing queued may disclose what was just made private.
function I.syncPrivacyChanged()
    requests,sessions,sendQueue,jobs,queuedJobs={},{},{},{},{}
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
    if kind=="death" then
        return detail=="Died" or detail==WoWStatusProgress.HARDCORE_DEATH or detail:match("^Total deaths: %d+$")~=nil
    end
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
    -- The name is always this client's own lookup of a whitelisted ID (#165).
    if kind=="achievement" then return named(detail,"Earned achievement: ") end
    -- One match, one line: "Won Warsong Gulch" or "Lost Warsong Gulch".
    if kind=="battleground" then return WoWStatusBattlegrounds.validText(detail) end
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
    local rarities=I.current.settings.loot_rarities or {rare=true,epic=true,legendary=true}
    return (rarities.rare and 1 or 0)+(rarities.epic and 2 or 0)+(rarities.legendary and 4 or 0)
end
local function requestPage(group,target,offset,pages,retries)
    local t=token()
    local member=groupMember(group)
    if not member then return end
    -- Never ahead of realm time: a responder drops cutoffs over 300 s ahead.
    local now=S.now()
    local cutoff=math.min(math.max(groupSince(group),now-AGE),now)
    requests[t]={group=group,target=target,key=P.senderKey(target),at=S.now(),offset=offset,pages=pages or 0,cutoff=cutoff,pending={},parts={},via={},retries=retries or 0}
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
    if not I.db then return false end
    contacted,loginUntil,loginNonce={},S.uptime()+60,token()
    J.sync()
    return true
end
function J.sync()
    if not I.db then return end
    if S.uptime()<=loginUntil then
        local groups={};for g in pairs(WoWStatusGroups.selected(I.current)) do groups[#groups+1]=g end;table.sort(groups)
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
    if not I.db or distribution~="WHISPER" or type(message)~="string" or #message>243 then return false end
    local group,op,t,body=message:match("^J2 ([a-f0-9]+) (%u) ([%w%-]+) (.*)$")
    -- An addon message carrying the group's ID (see WoWStatusPopups.vouch).
    if group and WoWStatusGroups.valid(group) and groupMember(group) and P.vouch then P.vouch(group,sender) end
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
        -- Game uptime, unlike the PC clock, can't jump when that clock is changed.
        local uptime=S.uptime()
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
        if rates[rateKey] and S.now()-rates[rateKey]<2 then return false end
        rates[rateKey]=S.now()
        for sessionKey,session in pairs(sessions) do
            if session.group==group and session.key==key then sessions[sessionKey]=nil end
        end
        local n=0;for _ in pairs(sessions) do n=n+1 end;if n>=32 then return false end
        local now=S.now()
        cutoff=math.max(cutoff,now-AGE,groupSince(group))
        local eligible={}
        for _,e in ipairs(I.db.journal.entries) do
            local weight=({[3]=1,[4]=2,[5]=4})[e.quality]
            local wanted=e.kind~="loot" or (weight and math.floor(mask/weight)%2==1)
            if wanted and e.at>=cutoff and offerable(e,group,now) then eligible[#eligible+1]=e end
        end
        local offer,list={},{}
        for i=offset+1,math.min(offset+PAGE,#eligible) do local d=digestFor(eligible[i]);offer[d]=eligible[i].id;list[#list+1]=d end
        local cursor=math.min(offset+PAGE,#eligible)
        sessions[group..":"..key..":"..t]={at=S.now(),offer=offer,used=false,group=group,key=key}
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
                local existing=I.digests[d]
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
        if not session or session.used or S.now()-session.at>120 or not body:match("^[a-f0-9,]+$") then return false end
        local ids={};for d in body:gmatch("[^,]+") do if #d~=22 or not session.offer[d] or #ids>=PAGE then return false end;ids[#ids+1]=d end
        session.used=true
        for _, d in ipairs(ids) do
            local e=I.index[session.offer[d]]
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
        if claimed~=key and not I.index[e.id] then
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
    if not I.db then return end
    local now=S.now()
    for t,r in pairs(requests) do
        if now-r.at>(r.sent and 120 or 300) then
            requests[t]=nil
            if r.retries<1 then enqueueJob(r.group,r.target,r.retries+1) end
        end
    end
    for k,s in pairs(sessions) do if now-s.at>120 then sessions[k]=nil end end
    local uptime=S.uptime()
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
    local clock=S.uptime()
    allowance=math.min(ALLOWANCE,allowance+math.max(0,clock-allowanceAt));allowanceAt=clock
    if clock<holdUntil or clock-lastSend<.5 or #sendQueue==0 or WoWStatusAdapter.chatRestricted() then return end
    if allowance<1 and S.call(IsInInstance) then return end
    local item=sendQueue[1]
    local queryKey=item.group..":"..P.senderKey(item.target)
    if item.query and lastQuery[queryKey] and clock-lastQuery[queryKey]<2.1 then return end
    -- A query whose request already timed out is not sent: its retry is queued.
    local drop=(item.expires and (now>item.expires or not I.current.settings.enabled))
        or (item.query and not requests[item.query])
        or not groupMember(item.group) or not peer(item.group,item.target)
        or (item.entry and (I.index[item.entry.id]~=item.entry or not offerable(item.entry,item.group)))
    local send=C_ChatInfo and C_ChatInfo.SendAddonMessage or SendAddonMessage
    if drop or not send then table.remove(sendQueue,1);return end
    lastSend,allowance=clock,math.max(0,allowance-1)
    P.whispered(item.target)
    local result=P.sendResult(pcall(send,PREFIX,item.text,"WHISPER",item.target))
    -- The packet's kind only: its second word names the group (#188).
    if I.db.debug==true then
        S.debug("log send "..(item.text:match("^"..S.NONSPACE.."+ "..S.NONSPACE.."+ ("..S.NONSPACE.."+)") or "?").." to "..tostring(item.target)..": "..tostring(result))
    end
    local wait=P.retryWait(result,item,pacing,clock)
    if wait then allowance,holdUntil=0,clock+wait;return end
    table.remove(sendQueue,1)
    if item.query then
        lastQuery[queryKey]=clock
        if requests[item.query] then requests[item.query].at=now;requests[item.query].sent=true end
    end
end
local frame=CreateFrame("Frame")
frame:RegisterEvent("CHAT_MSG_ADDON")
pcall(frame.RegisterEvent,frame,"CHAT_MSG_WHISPER")
frame:SetScript("OnEvent",function(_,event,prefix,message,distribution,sender)
    if event=="CHAT_MSG_WHISPER" then J.reaction(prefix,message);return end
    if S.string(prefix)==PREFIX then J.receive(S.string(message),S.string(sender),S.string(distribution)) end
end)
local elapsed=0
frame:SetScript("OnUpdate",function(_,delta) elapsed=elapsed+delta;if elapsed>=.25 then elapsed=0;J.tick() end end)
