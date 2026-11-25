-- One place for the small facts every "may this be recorded, shown, sent or
-- relayed" decision needs (#225): which collection switch an event kind
-- answers to, and which character owns a log entry. Pure functions of their
-- arguments; nothing here reads or writes saved data.
WoWStatusSharing = {}
local Sh = WoWStatusSharing

-- Kinds that share another kind's switch. The progress kinds are local
-- bookkeeping for quests and professions and follow those switches too.
local CATEGORY = {raid = "dungeon", epicmount = "mount", questprogress = "quest", professionprogress = "profession",
    battleground = "pvp"}
function Sh.category(kind) return CATEGORY[kind] or kind end

-- Announcement choices apply to sending and receiving for this character.
-- A missing choice retains the existing default; character details and the
-- master sending switch do not opt friends out of reception.
function Sh.wants(character, kind)
    local choices = character and character.settings and character.settings.in_game
    return not choices or choices[Sh.category(kind)] ~= false
end

-- The character (from the account's saved characters) that wrote a log entry.
function Sh.ownerOf(db, entry)
    for _, c in pairs(db and db.characters or {}) do
        if c.identity and c.identity.guid == entry.owner and c.identity.client == entry.client then return c end
    end
end
