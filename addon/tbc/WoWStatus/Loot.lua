-- Stable item class/slot IDs, never localized type names or guessed rarity.
WoWStatusLoot = {}
local L,S = WoWStatusLoot,WoWStatusSafe
local slots={INVTYPE_HEAD=true,INVTYPE_NECK=true,INVTYPE_SHOULDER=true,INVTYPE_BODY=true,
    INVTYPE_CHEST=true,INVTYPE_ROBE=true,INVTYPE_WAIST=true,INVTYPE_LEGS=true,INVTYPE_FEET=true,
    INVTYPE_WRIST=true,INVTYPE_HAND=true,INVTYPE_FINGER=true,INVTYPE_TRINKET=true,INVTYPE_CLOAK=true,
    INVTYPE_SHIELD=true,INVTYPE_HOLDABLE=true,INVTYPE_TABARD=true,INVTYPE_RELIC=true}
function L.defaults(settings)
    if not settings.loot_rarities then settings.loot_rarities={rare=true,epic=true,legendary=true} end
end
function L.allowed(settings,info)
    if not info or type(info.item_id)~="number" or info.item_id<1 or info.item_id>1000000000 or info.item_id~=math.floor(info.item_id) or info.class_id~=4 or not slots[info.equip_loc] then return false end
    local key=({[3]="rare",[4]="epic",[5]="legendary"})[info.quality]
    if not key then return false end
    return not settings or not settings.loot_rarities or settings.loot_rarities[key]==true
end
function L.info(link)
    if type(link)~="string" and type(link)~="number" then return nil end
    local getter=C_Item and C_Item.GetItemInfo or GetItemInfo
    local ok,name,full,quality,_,_,_,_,_,equip,_,_,class = pcall(getter or function() end,link)
    name,full,quality,equip,class=S.string(name),S.string(full),S.number(quality),S.string(equip),S.number(class)
    local instant=C_Item and C_Item.GetItemInfoInstant or GetItemInfoInstant
    local id
    if instant then
        local valid,itemID,_,_,location,_,itemClass=pcall(instant,link)
        if valid then id=S.number(itemID);equip=equip or S.string(location);class=class or S.number(itemClass) end
    end
    if not id then id=type(link)=="number" and link or tonumber(link:match("item:(%d+)")) end
    if not ok or not name or not full or not quality or not class or not equip or not id then return nil end
    return {item=full,item_id=id,quality=quality,class_id=class,equip_loc=equip,name=name}
end
function L.eventInfo(data)
    if data.class_id and data.equip_loc and data.item_id then return data end
    return L.info(data.item)
end
local pending={}
function L.capture(link,callback)
    local info=L.info(link)
    if info then callback(info);return end
    local count=0;for _ in pairs(pending) do count=count+1 end
    if pending[link] then
        if #pending[link].callbacks<8 then table.insert(pending[link].callbacks,callback) end
    elseif count<32 then pending[link]={at=time(),callbacks={callback}} end
end
local frame=CreateFrame("Frame")
pcall(frame.RegisterEvent,frame,"GET_ITEM_INFO_RECEIVED")
local function retry()
    for link,item in pairs(pending) do
        if time()-item.at>30 then pending[link]=nil
        else local info=L.info(link);if info then pending[link]=nil;for _,callback in ipairs(item.callbacks) do callback(info) end end end
    end
end
frame:SetScript("OnEvent",retry)
local elapsed=0
frame:SetScript("OnUpdate",function(_,delta) elapsed=elapsed+delta;if elapsed>=1 then elapsed=0;retry() end end)
