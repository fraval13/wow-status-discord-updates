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
-- Sender side, Nynorsk only: how often a reaction uses a voiced line, and how
-- many of those come from the lines inside the addon (the rest need the pack).
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
-- The Nynorsk line to whisper for a reaction: usually a voiced one.
function V.pick(voice, key, count)
    local found = voicedIndexes(voice, key)
    if not found or math.random() >= V.VOICED_SHARE then return math.random(count) end
    local list = found.pack
    if #found.sample > 0 and (#list == 0 or math.random() < V.SAMPLE_SHARE) then list = found.sample end
    local index = #list > 0 and list[math.random(#list)]
    if not index or index > count then return math.random(count) end
    return index
end

-- Receiver side ------------------------------------------------------------

-- Exact Nynorsk lines and level lines (text before and after the number).
local exact, levels
local function buildIndex()
    exact, levels = {}, {}
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
                local at = line and line:find("{level}", 1, true)
                if at then
                    levels[#levels + 1] = {line:sub(1, at - 1), line:sub(at + 7), voice, entry}
                elseif line and not exact[line] then
                    exact[line] = {voice, entry}
                end
            end
        end
    end
    table.sort(levels, function(a, b) return #a[1] + #a[2] > #b[1] + #b[2] end)
end
-- A received text's voice, clip entry and (for a level line) the level.
function V.lookup(text)
    if type(text) ~= "string" or not data() then return nil end
    if not exact then buildIndex() end
    local found = exact[text]
    if found then return found[1], found[2] end
    for _, rule in ipairs(levels) do
        local before, after = rule[1], rule[2]
        if #text > #before + #after and text:sub(1, #before) == before
            and (after == "" or text:sub(-#after) == after) then
            local middle = text:sub(#before + 1, #text - #after)
            if middle:match("^%d+$") then return rule[3], rule[4], tonumber(middle) end
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
-- Play a clip (and a level's number after it); returns false if nothing played.
-- When it ends, the next queued reaction (if any) plays.
local function speak(clip, tier, number)
    local d = data()
    if not play(clipFile(clip, tier)) then return false end
    local length = tonumber(d.seconds[clip]) or 3
    if number then
        local after = length + (tonumber(d.gap) or .12)
        if C_Timer and C_Timer.After then C_Timer.After(after, function() play(clipFile(number, 2)) end) end
        length = after + (tonumber(d.seconds[number]) or 1)
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
        if speak(item[1], item[2], item[3]) then return end
    end
end
function V.queued() return #queue end

-- A friend's reaction has been accepted (Journal): read it aloud if it is voiced,
-- the voices are on and the interval (if any) has passed. While another clip
-- plays it is queued instead; a full queue drops it to text only.
function V.heard(text)
    if not V.available() or not V.enabled() then return false end
    local voice, entry, level = V.lookup(text)
    if not voice then return false end
    local clip, tier = entry[1], entry[2]
    if not canPlay(tier) then return false end
    local number
    if level then
        local numbers = data().numbers[voice]
        number = numbers and numbers[level]
        if not number or not canPlay(2) then return false end
    end
    local last, now = tonumber(settings().last_at), S.now()
    if last and now >= last and now - last < V.interval() * 60 then return false end
    if clock() < busyUntil then
        if #queue >= V.MAX_QUEUE then return false end
        queue[#queue + 1] = {clip, tier, number}
    elseif not speak(clip, tier, number) then
        return false
    end
    settings().last_at = now
    return true
end

-- /wstatus voicetest [voice] [level]: play a recorded line exactly as a friend's
-- reaction would sound (pack lines too when the pack is installed; "level" for a
-- level line with its number) and return its text and voice. A local test with
-- no friend needed: nothing is sent and the interval is not touched.
function V.simulate(request)
    local d, P = data(), WoWStatusPersonalities
    if not d or not P then return nil end
    if clock() < busyUntil then return nil, "busy" end
    request = type(request) == "string" and request:lower() or ""
    local levelOnly = request:find("level", 1, true) or request:find("nivå", 1, true)
    local named = P.findReaction((request:gsub("level", ""):gsub("nivå", "")))
    local voices = {}
    for voice in pairs(d.lines) do voices[#voices + 1] = voice end
    table.sort(voices)
    local voice = (named and d.lines[named] and named) or (d.lines[P.reactionVoice()] and P.reactionVoice())
        or voices[math.random(math.max(#voices, 1))]
    local _, nn = P.reactionBanks(voice or "")
    local choices = {}
    for key, entries in pairs(voice and nn and d.lines[voice] or {}) do
        if not levelOnly or key == "level" then
            for index, entry in pairs(entries) do
                local playable = canPlay(entry[2])
                if key == "level" then playable = canPlay(2) and d.numbers[voice] ~= nil end
                if playable and nn[key] and nn[key][index] then choices[#choices + 1] = {key, index, entry} end
            end
        end
    end
    table.sort(choices, function(a, b) return a[3][1] < b[3][1] end)
    if #choices == 0 then return nil end
    local chosen = choices[math.random(#choices)]
    local key, index, entry = chosen[1], chosen[2], chosen[3]
    local text, number = nn[key][index], nil
    if key == "level" then
        local levels = {}
        for level in pairs(d.numbers[voice]) do levels[#levels + 1] = level end
        table.sort(levels)
        local level = levels[math.random(#levels)]
        number = d.numbers[voice][level]
        text = (text:gsub("{level}", tostring(level)))
    end
    if not speak(entry[1], entry[2], number) then return nil end
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
