-- "Share it" (#67): whisper the download link to a friend who lacks the addon.
-- Only ever sent by the player's own click or command, at most once per
-- person per hour (account-wide, so switching characters does not reset it).
WoWStatusShare = {}
local SH, S = WoWStatusShare, WoWStatusSafe
SH.URL = "https://wow.frankvalde.com"
SH.MESSAGE = "I'm using WoW Status to share progress with friends - get it at " .. SH.URL
SH.INTERVAL = 3600
local db, say
local MENUS = {"MENU_UNIT_PLAYER", "MENU_UNIT_FRIEND", "MENU_UNIT_PARTY", "MENU_UNIT_RAID_PLAYER",
    "MENU_UNIT_BN_FRIEND", "MENU_UNIT_GUILD", "MENU_UNIT_COMMUNITIES_GUILD_MEMBER", "MENU_UNIT_CHAT_ROSTER"}

local function sent()
    db.share = type(db.share) == "table" and db.share or {}
    db.share.sent = type(db.share.sent) == "table" and db.share.sent or {}
    local now = time()
    for key, at in pairs(db.share.sent) do
        if type(at) ~= "number" or at > now or now - at >= SH.INTERVAL then db.share.sent[key] = nil end
    end
    return db.share.sent
end

-- A character name with an optional realm: no spaces, pipes or control bytes.
function SH.normalize(name)
    name = S.string(name)
    name = name and S.trim(name)
    if not name or name == "" or #name > 64 or name:find(S.CONTROL_OR_PIPE) or name:find(S.SPACE)
        or name:find("[%%%[%]{}<>\"'`,;:!?/\\=+*&$#@~^()]") then return nil end
    local character, realm = name:match("^([^%-]+)%-?(.*)$")
    if not character or (realm ~= "" and realm:find("%-")) then return nil end
    return name
end

-- Returns true when the whisper was handed to the game.
function SH.send(rawName)
    if not db then return false end
    local name = SH.normalize(rawName)
    if not name then say("Usage: /wstatus share <character name>"); return false end
    local key = WoWStatusCaseFold(name)
    local list = sent()
    if list[key] then
        say("You already shared WoW Status with " .. name .. " in the last hour.")
        return false
    end
    if WoWStatusAdapter.chatRestricted and WoWStatusAdapter.chatRestricted() then
        say("Chat is restricted right now; try again later.")
        return false
    end
    local send = WoWStatusAdapter.chatSender and WoWStatusAdapter.chatSender()
    if not send then say("Whispers are not available in this client."); return false end
    local ok, result = pcall(send, SH.MESSAGE, "WHISPER", nil, name)
    if not ok or S.value(result) == false then say("The whisper to " .. name .. " could not be sent."); return false end
    list[key] = time()
    say("Shared the WoW Status link with " .. name .. ".")
    return true
end

local function menuName(contextData)
    if type(contextData) ~= "table" then return nil end
    local name, server = S.string(contextData.name), S.string(contextData.server)
    if name and server and server ~= "" and not name:find("%-") then name = name .. "-" .. server end
    return name
end

-- Right-click menus exist only on clients with the modern Menu API. Elsewhere
-- /wstatus share <name> is the way to share.
local menusAdded = false
function SH.init(saved, notify)
    db, say = saved, notify
    sent()
    if menusAdded or not (Menu and Menu.ModifyMenu) then return end
    menusAdded = true
    for _, tag in ipairs(MENUS) do
        pcall(Menu.ModifyMenu, tag, function(_, root, contextData)
            local name = menuName(contextData)
            if not name or not SH.normalize(name) or not root or not root.CreateButton then return end
            if contextData.isSelf or (UnitIsUnit and contextData.unit and S.call(UnitIsUnit, contextData.unit, "player") == true) then return end
            if root.CreateDivider then root:CreateDivider() end
            root:CreateButton("Share WoW Status", function() SH.send(name) end)
        end)
    end
end
