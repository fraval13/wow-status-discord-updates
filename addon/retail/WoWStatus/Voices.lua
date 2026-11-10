-- Spoken reactions (WoW Forever). A friend's Nynorsk reaction whisper (GZ!, F,
-- Congrats! in a reaction voice) is read aloud in that voice from clips recorded
-- in advance (docs/voices/README.md). VoiceData.lua, shipped only with Forever,
-- lists the voiced lines; without it this file does nothing. Nothing is sent:
-- the sender only favours voiced lines, and the receiver decides what plays.
-- By default every voiced reaction is read: clips never overlap, so one that
-- arrives while another plays waits its turn in a short queue (MAX_QUEUE). A
-- player may choose an interval (1-60 minutes) instead; reactions inside it stay
-- text-only.
WoWStatusVoices = {}
local V, S = WoWStatusVoices, WoWStatusSafe
V.DEFAULT_INTERVAL = 0
V.MAX_QUEUE = 10
V.MAX_INTERVAL = 60
V.INTERVALS = {0, 1, 2, 3, 5, 10, 15, 20, 30, 45, 60}
-- Sender side, Nynorsk only: how often a reaction uses a voiced line when the
-- player has turned "always send a voiced reaction" off (it is on by default,
-- and then every reaction with a voiced line uses one), and how many of those
-- come from the lines inside the addon (the rest need the pack).
V.VOICED_SHARE = .9
V.SAMPLE_SHARE = .25
local SAMPLE_PATH = "Interface\\AddOns\\WoWStatus\\Sounds\\Voices\\"
local PACK_PATH = "Interface\\AddOns\\WoWStatus_Voices\\Sounds\\"

local function data()
    return type(WoWStatusVoiceData) == "table" and type(WoWStatusVoiceData.lines) == "table"
        and WoWStatusVoiceData or nil
end
function V.available() return data() ~= nil end
function V.packInstalled() return type(WoWStatusVoicePack) == "table" end
-- The CurseForge build of Forever carries every clip itself (scripts/voices.py
-- bundle marks it): then nothing needs the separate pack.
function V.bundled()
    local d = data()
    return d ~= nil and d.bundled == true
end
-- Whether a clip of this tier is on disk: in the addon, or in the pack.
local function canPlay(tier) return tier == 1 or V.bundled() or V.packInstalled() end
function V.packVersion() return V.packInstalled() and tonumber(WoWStatusVoicePack.version) or nil end
function V.packURL()
    local d = data()
    return d and type(d.pack) == "table" and d.pack.url or nil
end

-- Account-wide settings in WoWStatusDB.voices; defaults are stored as nothing.
local function settings()
    if type(WoWStatusDB) ~= "table" then return {} end
    if type(WoWStatusDB.voices) ~= "table" then WoWStatusDB.voices = {} end
    return WoWStatusDB.voices
end
function V.enabled() return settings().enabled ~= false end
function V.setEnabled(on)
    if on then settings().enabled = nil else settings().enabled = false end
    return true
end
local function validInterval(value)
    value = tonumber(value)
    return value and value >= 0 and value <= V.MAX_INTERVAL and value == math.floor(value) and value or nil
end
-- Sender side: always whisper a voiced line when the reaction has one (default).
function V.alwaysVoiced() return settings().always_voiced ~= false end
function V.setAlwaysVoiced(on)
    if on then settings().always_voiced = nil else settings().always_voiced = false end
    return true
end
function V.interval() return validInterval(settings().interval) or V.DEFAULT_INTERVAL end
function V.setInterval(value)
    value = validInterval(value)
    if not value then return false end
    settings().interval = value ~= V.DEFAULT_INTERVAL and value or nil
    return true
end
-- The game volume slider a clip follows. Dialog (the default) is scaled by the
-- Master and Dialog sliders; Master by the Master slider alone, so it is the
-- loudest choice for players who keep Dialog low.
V.DEFAULT_CHANNEL = "Dialog"
V.CHANNELS = {{"Dialog", "Dialog"}, {"SFX", "Sound effects"}, {"Master", "Master (loudest)"}}
local function validChannel(value)
    for _, entry in ipairs(V.CHANNELS) do if entry[1] == value then return value end end
end
function V.channel() return validChannel(settings().channel) or V.DEFAULT_CHANNEL end
function V.setChannel(value)
    value = validChannel(value)
    if not value then return false end
    settings().channel = value ~= V.DEFAULT_CHANNEL and value or nil
    return true
end
function V.channelLabel(value)
    value = validChannel(value) or V.channel()
    for _, entry in ipairs(V.CHANNELS) do
        if entry[1] == value then return WoWStatusLocale.T(entry[2]) end
    end
end
function V.intervalLabel(value)
    value = value or V.interval()
    if value == 0 then return WoWStatusLocale.T("Every reaction") end
    return WoWStatusLocale.F("%d min", value)
end

-- Sender side --------------------------------------------------------------

-- Voiced line numbers for a voice and reaction key, split by where they ship.
local picks = {}
local function voicedIndexes(voice, key)
    local d = data()
    local entries = d and d.lines[voice] and d.lines[voice][key]
    if not entries then return nil end
    local cacheKey = voice .. "\0" .. key
    if not picks[cacheKey] then
        local sample, pack = {}, {}
        for index, entry in pairs(entries) do table.insert(entry[2] == 1 and sample or pack, index) end
        table.sort(sample); table.sort(pack) -- pairs() order is not stable
        picks[cacheKey] = {sample = sample, pack = pack}
    end
    return picks[cacheKey]
end
-- The recorded zone names of a voice (zones[name] = {said, asked}).
local function zonesOf(voice)
    local d = data()
    return d and type(d.zones) == "table" and d.zones[voice] or nil
end
-- The Nynorsk line to whisper for a reaction: a voiced one when there is one
-- (always by default, else usually). A zone line (value is the zone) counts as
-- voiced only when the voice has that zone.
function V.pick(voice, key, count, value)
    local found = voicedIndexes(voice, key)
    if found and key == "enjoy" then
        local zones = zonesOf(voice)
        if not (type(value) == "string" and zones and zones[value]) then found = nil end
    end
    if not found or (not V.alwaysVoiced() and math.random() >= V.VOICED_SHARE) then return math.random(count) end
    local list = found.pack
    if #found.sample > 0 and (#list == 0 or math.random() < V.SAMPLE_SHARE) then list = found.sample end
    local index = #list > 0 and list[math.random(#list)]
    if not index or index > count then return math.random(count) end
    return index
end

-- Receiver side ------------------------------------------------------------

-- Exact Nynorsk lines, and level and zone lines (text before and after the slot).
local exact, slots
local function buildIndex()
    exact, slots = {}, {}
    local d, P = data(), WoWStatusPersonalities
    if not d or not P then return end
    local voices = {}
    for voice in pairs(d.lines) do voices[#voices + 1] = voice end
    table.sort(voices) -- one owner for a line two voices share
    for _, voice in ipairs(voices) do
        local _, nn = P.reactionBanks(voice)
        for key, entries in pairs(nn and d.lines[voice] or {}) do
            for index, entry in pairs(entries) do
                local line = nn[key] and nn[key][index]
                local slot = line and (line:find("{level}", 1, true) and "{level}"
                    or line:find("{zone}", 1, true) and "{zone}")
                if slot then
                    local at = line:find(slot, 1, true)
                    local rule = {line:sub(1, at - 1), line:sub(at + #slot), voice, entry, slot}
                    -- A line that opens with its zone plays the zone first; "{zone}?" asks it.
                    rule.first = at == 1
                    rule.asked = rule.first and rule[2]:sub(1, 1) == "?"
                    slots[#slots + 1] = rule
                elseif line and not exact[line] then
                    exact[line] = {voice, entry}
                end
            end
        end
    end
    table.sort(slots, function(a, b) return #a[1] + #a[2] > #b[1] + #b[2] end)
end
-- A received text's voice and clip entry, then the level (a level line) or the
-- zone {name, first, asked} (a zone line).
function V.lookup(text)
    if type(text) ~= "string" or not data() then return nil end
    if not exact then buildIndex() end
    local found = exact[text]
    if found then return found[1], found[2] end
    for _, rule in ipairs(slots) do
        local before, after = rule[1], rule[2]
        if #text > #before + #after and text:sub(1, #before) == before
            and (after == "" or text:sub(-#after) == after) then
            local middle = text:sub(#before + 1, #text - #after)
            if rule[5] == "{level}" then
                if middle:match("^%d+$") then return rule[3], rule[4], tonumber(middle) end
            else
                return rule[3], rule[4], nil, {name = middle, first = rule.first, asked = rule.asked}
            end
        end
    end
end

local busyUntil, generation, queue = 0, 0, {}
local function clock() return S.number(S.call(GetTime)) or time() end
local function play(file)
    local willPlay = S.call(PlaySoundFile, file, V.channel())
    return willPlay and true or false
end
local function clipFile(clip, tier) return ((tier == 1 or V.bundled()) and SAMPLE_PATH or PACK_PATH) .. clip .. ".ogg" end

local drain
-- Play a clip and its tail (a level's number or a zone, always in the pack):
-- the tail follows the line, or comes first when tailFirst is set. Returns false
-- if nothing played. When it ends, the next queued reaction (if any) plays.
local function speak(clip, tier, tail, tailFirst)
    local d = data()
    local one, two = {clip, tier, 3}, tail and {tail, 2, 1}
    if two and tailFirst then one, two = two, one end
    if not play(clipFile(one[1], one[2])) then return false end
    local length = tonumber(d.seconds[one[1]]) or one[3]
    if two then
        local after = length + (tonumber(d.gap) or .12)
        if C_Timer and C_Timer.After then C_Timer.After(after, function() play(clipFile(two[1], two[2])) end) end
        length = after + (tonumber(d.seconds[two[1]]) or two[3])
    end
    busyUntil = clock() + length
    generation = generation + 1
    local mine = generation
    if C_Timer and C_Timer.After then
        C_Timer.After(length, function()
            if mine ~= generation then return end
            busyUntil = 0
            drain()
        end)
    end
    return true
end

-- Play the queued reactions in order once nothing is playing.
drain = function()
    if not V.available() or not V.enabled() then queue = {}; return end
    while #queue > 0 and clock() >= busyUntil do
        local item = table.remove(queue, 1)
        if speak(item[1], item[2], item[3], item[4]) then return end
    end
end
function V.queued() return #queue end

-- A friend's reaction has been accepted (Journal): read it aloud if it is voiced,
-- the voices are on and the interval (if any) has passed. While another clip
-- plays it is queued instead; a full queue drops it to text only.
function V.heard(text)
    if not V.available() or not V.enabled() then return false end
    local voice, entry, level, zone = V.lookup(text)
    if not voice then return false end
    local clip, tier = entry[1], entry[2]
    if not canPlay(tier) then return false end
    local tail
    if level then
        local numbers = data().numbers[voice]
        tail = numbers and numbers[level]
        if not tail or not canPlay(2) then return false end
    elseif zone then
        -- A zone this voice has not recorded (or another client language) stays text.
        local found = (zonesOf(voice) or {})[zone.name]
        tail = found and found[zone.asked and 2 or 1]
        if not tail or not canPlay(2) then return false end
    end
    local last, now = tonumber(settings().last_at), S.now()
    if last and now >= last and now - last < V.interval() * 60 then return false end
    if clock() < busyUntil then
        if #queue >= V.MAX_QUEUE then return false end
        queue[#queue + 1] = {clip, tier, tail, zone and zone.first}
    elseif not speak(clip, tier, tail, zone and zone.first) then
        return false
    end
    settings().last_at = now
    return true
end

-- /wstatus voicetest [voice] [level|zone]: play a recorded line exactly as a
-- friend's reaction would sound (pack lines too when the pack is installed;
-- "level" for a level line with its number, "zone" for a zone line with its
-- zone) and return its text and voice. A local test with
-- no friend needed: nothing is sent and the interval is not touched.
function V.simulate(request)
    local d, P = data(), WoWStatusPersonalities
    if not d or not P then return nil end
    if clock() < busyUntil then return nil, "busy" end
    request = type(request) == "string" and request:lower() or ""
    local only = (request:find("level", 1, true) or request:find("nivå", 1, true)) and "level"
        or (request:find("zone", 1, true) or request:find("sone", 1, true)) and "enjoy"
    local named = P.findReaction((request:gsub("level", ""):gsub("nivå", ""):gsub("zone", ""):gsub("sone", "")))
    local voices = {}
    for voice in pairs(d.lines) do voices[#voices + 1] = voice end
    table.sort(voices)
    local voice = (named and d.lines[named] and named) or (d.lines[P.reactionVoice()] and P.reactionVoice())
        or voices[math.random(math.max(#voices, 1))]
    local _, nn = P.reactionBanks(voice or "")
    local choices = {}
    for key, entries in pairs(voice and nn and d.lines[voice] or {}) do
        if not only or key == only then
            for index, entry in pairs(entries) do
                local playable = canPlay(entry[2])
                if key == "level" then playable = canPlay(2) and d.numbers[voice] ~= nil end
                if key == "enjoy" then playable = canPlay(2) and zonesOf(voice) ~= nil end
                if playable and nn[key] and nn[key][index] then choices[#choices + 1] = {key, index, entry} end
            end
        end
    end
    table.sort(choices, function(a, b) return a[3][1] < b[3][1] end)
    if #choices == 0 then return nil end
    local chosen = choices[math.random(#choices)]
    local key, index, entry = chosen[1], chosen[2], chosen[3]
    local text, tail, tailFirst = nn[key][index], nil, nil
    if key == "level" then
        local levels = {}
        for level in pairs(d.numbers[voice]) do levels[#levels + 1] = level end
        table.sort(levels)
        local level = levels[math.random(#levels)]
        tail = d.numbers[voice][level]
        text = (text:gsub("{level}", tostring(level)))
    elseif key == "enjoy" then
        local zones, names = zonesOf(voice), {}
        for name in pairs(zones) do names[#names + 1] = name end
        table.sort(names)
        local name = names[math.random(#names)]
        local at = text:find("{zone}", 1, true)
        tailFirst = at == 1
        tail = zones[name][(tailFirst and text:sub(at + 6, at + 6) == "?") and 2 or 1]
        text = text:sub(1, at - 1) .. name .. text:sub(at + 6)
    end
    if not speak(entry[1], entry[2], tail, tailFirst) then return nil end
    return text, voice
end

-- Settings: play one of the addon's own lines in the chosen reaction voice.
-- Local only, and it does not count against the interval.
function V.test()
    local d, P = data(), WoWStatusPersonalities
    if not d or clock() < busyUntil then return false end
    local wanted = P and P.reactionVoice()
    local voices = {}
    for voice in pairs(d.lines) do voices[#voices + 1] = voice end
    table.sort(voices)
    local voice = d.lines[wanted] and wanted or voices[math.random(math.max(#voices, 1))]
    local clips = {}
    for _, entries in pairs(voice and d.lines[voice] or {}) do
        for _, entry in pairs(entries) do if entry[2] == 1 then clips[#clips + 1] = entry[1] end end
    end
    table.sort(clips)
    if #clips == 0 then return false end
    return speak(clips[math.random(#clips)], 1)
end
