-- One place for the small facts every "may this be recorded, shown, sent or
-- relayed" decision needs (#225): which collection switch an event kind
-- answers to, and which character owns a log entry. Pure functions of their
-- arguments; nothing here reads or writes saved data.
WoWStatusSharing = {}
local Sh = WoWStatusSharing

-- Kinds that share another kind's switch. The progress kinds are local
-- bookkeeping for quests and professions and follow those switches too.
local CATEGORY = {raid = "dungeon", epicmount = "mount", questprogress = "quest", professionprogress = "profession"}
function Sh.category(kind) return CATEGORY[kind] or kind end

-- The character (from the account's saved characters) that wrote a log entry.
function Sh.ownerOf(db, entry)
    for _, c in pairs(db and db.characters or {}) do
        if c.identity and c.identity.guid == entry.owner and c.identity.client == entry.client then return c end
    end
end
