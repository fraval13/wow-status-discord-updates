"""Spoken reactions (Forever): every voiced Nynorsk reaction from a friend is read aloud, one at a time."""
from pathlib import Path

from test_addon import make_lua, run_addon_file
from test_forever import forever_runtime
from test_journal import actor, clock, deliver_popup
from test_reactions import sent_whispers

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = 'Interface\\AddOns\\WoWStatus\\Sounds\\Voices\\'
PACK = 'Interface\\AddOns\\WoWStatus_Voices\\Sounds\\'
# The same paths written inside Lua strings.
LUA_SAMPLE, LUA_PACK = SAMPLE.replace('\\', '\\\\'), PACK.replace('\\', '\\\\')

# Two Wholesome GZ! lines (one in the addon, one in the pack), a level line that
# ends in its number, and that number. Real clips are tested in test_voices.py.
VOICE_DATA = r'''
__played = {}
__willPlay = true
function PlaySoundFile(file, channel) table.insert(__played, {file, channel}); return __willPlay, #__played end
__after = {}
C_Timer.After = function(seconds, fn) table.insert(__after, {seconds, fn}) end
local _, nn = WoWStatusPersonalities.reactionBanks("wholesome")
for i, line in ipairs(nn.level) do
    if not __levelIndex and line:find(" {level}!", 1, true) and line:sub(-8) == "{level}!" then __levelIndex = i end
end
WoWStatusVoiceData = {
    pack = {addon = "WoWStatus_Voices", url = "https://example.invalid/WoWStatus_Voices.zip"},
    gap = .1,
    lines = {wholesome = {gz = {[1] = {"aaaaaaaaaaaa", 1}, [2] = {"bbbbbbbbbbbb", 2}},
                          level = {[__levelIndex] = {"cccccccccccc", 2}}}},
    numbers = {wholesome = {[37] = "dddddddddddd"}},
    seconds = {aaaaaaaaaaaa = 2, bbbbbbbbbbbb = 2, cccccccccccc = 1.5, dddddddddddd = .6},
}
__nn = nn
'''


def voiced_lua():
    lua = actor('Mira')
    lua.execute(VOICE_DATA)
    return lua


def test_without_voice_data_nothing_is_read_and_nothing_changes():
    lua = make_lua()
    lua.execute('''
        __played = {}
        function PlaySoundFile(file) table.insert(__played, file) return true end
        local V = WoWStatusVoices
        local _, nn = WoWStatusPersonalities.reactionBanks("wholesome")
        assert(not V.available() and not V.heard(nn.gz[1]) and not V.test() and #__played == 0)
        WoWStatusPreviews.show()
        assert(WoWStatusNotificationPreviews.voices == nil)
    ''')


def test_every_voiced_reaction_is_read_by_default_one_after_another():
    lua = voiced_lua()
    lua.execute(f'''
        local V = WoWStatusVoices
        assert(V.available() and V.enabled() and V.interval() == 0 and V.intervalLabel() == "Every reaction")
        assert(V.heard(__nn.gz[1]))
        assert(__played[1][1] == "{LUA_SAMPLE}aaaaaaaaaaaa.ogg" and __played[1][2] == "Dialog")
        assert(#__after == 1 and __after[1][1] == 2)    -- the next one starts when this clip ends
        -- Reactions that arrive while a clip plays wait their turn, in order.
        local packLine = __nn.gz[2]
        WoWStatusVoicePack = {{version = 1}}
        assert(V.heard(packLine) and V.heard(__nn.gz[1]) and V.queued() == 2 and #__played == 1)
        __after[1][2]()
        assert(#__played == 2 and __played[2][1] == "{LUA_PACK}bbbbbbbbbbbb.ogg" and V.queued() == 1)
        __after[1][2]()                                 -- an old timer does not cut the new clip short
        assert(#__played == 2 and V.queued() == 1)
        __after[2][2]()
        assert(#__played == 3 and __played[3][1] == "{LUA_SAMPLE}aaaaaaaaaaaa.ogg" and V.queued() == 0)
        -- The queue is bounded: past it, a reaction stays text-only.
        for _ = 1, V.MAX_QUEUE do assert(V.heard(__nn.gz[1])) end
        assert(not V.heard(__nn.gz[1]) and V.queued() == V.MAX_QUEUE)
        -- A clip the game refuses is skipped and the next one plays.
        __willPlay = false
        __after[3][2]()
        assert(V.queued() == 0)
        __willPlay = true
        -- Turning the voices off drops what is waiting.
        __mono = __mono + 10
        assert(V.heard(__nn.gz[1]) and V.heard(__nn.gz[1]) and V.queued() == 1)
        V.setEnabled(false)
        local played = #__played
        __after[#__after][2]()
        assert(V.queued() == 0 and #__played == played)
        V.setEnabled(true)
    ''')


def test_a_chosen_interval_reads_at_most_one_reaction_per_interval():
    lua = voiced_lua()
    lua.execute('''
        local V = WoWStatusVoices
        assert(V.setInterval(1) and WoWStatusDB.voices.interval == 1 and V.intervalLabel() == "1 min")
        assert(V.heard(__nn.gz[1]))
        assert(not V.heard(__nn.gz[1]) and V.queued() == 0)  -- inside the minute: text only
        __mono = __mono + 10; __now = __now + 30
        assert(not V.heard(__nn.gz[1]))
        __now = __now + 31
        assert(V.heard(__nn.gz[1]) and #__played == 2)
        assert(not V.setInterval(61) and not V.setInterval(2.5) and not V.setInterval(-1) and V.interval() == 1)
        assert(V.setInterval(5) and WoWStatusDB.voices.interval == 5)
        assert(V.setInterval(0) and WoWStatusDB.voices.interval == nil and V.interval() == 0)
        -- Off, English, unknown and muted reactions are not read and do not count.
        V.setEnabled(false)
        __mono = __mono + 10; __now = __now + 400
        assert(not V.heard(__nn.gz[1]) and WoWStatusDB.voices.enabled == false)
        V.setEnabled(true)
        assert(WoWStatusDB.voices.enabled == nil)
        local en = WoWStatusPersonalities.reactionBanks("wholesome")
        assert(not V.heard(en.gz[1]) and not V.heard("GZ!") and not V.heard(nil))
        __willPlay = false
        local last = WoWStatusDB.voices.last_at
        assert(not V.heard(__nn.gz[1]) and WoWStatusDB.voices.last_at == last)
        __willPlay = true
        assert(V.heard(__nn.gz[1]) and #__played == 4)  -- the refused clip was tried too
    ''')


def test_the_chosen_volume_slider_plays_the_voice_and_is_saved_only_when_changed():
    lua = voiced_lua()
    lua.execute('''
        local V = WoWStatusVoices
        assert(V.channel() == "Dialog" and V.channelLabel() == "Dialog")
        assert(not V.setChannel("Music") and not V.setChannel(nil) and V.channel() == "Dialog")
        assert(V.setChannel("Master") and WoWStatusDB.voices.channel == "Master")
        assert(V.channelLabel() == "Master (loudest)")
        assert(V.heard(__nn.gz[1]) and __played[1][2] == "Master")
        assert(V.setChannel("SFX") and V.channel() == "SFX")
        __mono = __mono + 10
        assert(V.test() and __played[2][2] == "SFX")
        assert(V.setChannel("Dialog") and WoWStatusDB.voices.channel == nil)
        WoWStatusDB.voices.channel = "Nonsense"            -- an old or edited setting
        assert(V.channel() == "Dialog")
    ''')


def test_pack_lines_need_the_pack_and_level_lines_add_their_number():
    lua = voiced_lua()
    lua.execute(f'''
        local V = WoWStatusVoices
        local level = __nn.level[__levelIndex]:gsub("{{level}}", "37")
        assert(not V.packInstalled() and not V.heard(__nn.gz[2]) and not V.heard(level) and #__played == 0)
        WoWStatusVoicePack = {{version = 3}}
        assert(V.packVersion() == 3)
        assert(V.heard(level))
        assert(__played[1][1] == "{LUA_PACK}cccccccccccc.ogg" and #__after == 2)
        assert(math.abs(__after[1][1] - 1.6) < 1e-9)
        __after[1][2]()
        assert(__played[2][1] == "{LUA_PACK}dddddddddddd.ogg" and __played[2][2] == "Dialog")
        __mono = __mono + 10; __now = __now + 301
        assert(not V.heard((__nn.level[__levelIndex]:gsub("{{level}}", "38"))))  -- no clip for 38
        assert(V.heard(__nn.gz[2]) and __played[3][1] == "{LUA_PACK}bbbbbbbbbbbb.ogg")
        -- A preview plays one of the addon's own lines and does not count.
        __mono = __mono + 10
        local last = WoWStatusDB.voices.last_at
        assert(V.test() and __played[4][1] == "{LUA_SAMPLE}aaaaaaaaaaaa.ogg" and WoWStatusDB.voices.last_at == last)
    ''')


def test_nynorsk_senders_favour_voiced_lines_and_english_is_unchanged():
    lua = voiced_lua()
    counts = lua.eval('''(function()
        math.randomseed(7)
        local P = WoWStatusPersonalities
        P.setReaction("wholesome")
        WoWStatusLocale.set("nn")
        local sample, pack, other = 0, 0, 0
        for _ = 1, 4000 do
            local line = P.reactionLine("gz")
            if line == __nn.gz[1] then sample = sample + 1
            elseif line == __nn.gz[2] then pack = pack + 1 else other = other + 1 end
        end
        WoWStatusLocale.set("en")
        local en = P.reactionBanks("wholesome")
        local voicedEnglish = 0
        for _ = 1, 4000 do
            local line = P.reactionLine("gz")
            if line == en.gz[1] or line == en.gz[2] then voicedEnglish = voicedEnglish + 1 end
        end
        return {sample, pack, other, voicedEnglish}
    end)()''')
    sample, pack, other, english = (counts[i] for i in range(1, 5))
    assert 0.87 < (sample + pack) / 4000 < 0.93
    assert 0.20 < sample / (sample + pack) < 0.30
    assert english < 100  # 2 of 300 lines: no weighting in English


def test_a_friends_voiced_gz_is_read_aloud_on_arrival():
    own, friend = actor('Mira'), actor('Thora')
    for lua in (own, friend):
        lua.execute(VOICE_DATA)
    friend.execute('''
        WoWStatusPopups.CLICK_GUARD = 0  -- this test is not about the click guard
        WoWStatusPersonalities.setReaction("wholesome")
        WoWStatusLocale.set("nn")
        WoWStatusVoices.VOICED_SHARE, WoWStatusVoices.SAMPLE_SHARE = 1, 1
    ''')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    whispered = friend.eval('''(function()
        WoWStatusPopups.tick()
        local button = WoWStatusLevelPopup.reactions[1]
        button.OnClick(button)
        return WoWStatusLevelPopup.item.whispered
    end)()''')
    assert whispered == friend.eval('__nn.gz[1]')
    assert sent_whispers(friend) == [(whispered, 'Mira-TestRealm')]
    assert len(list(friend.eval('__played').values())) == 0  # the sender hears nothing
    own.execute(f'''
        __peers = {{"Mira-TestRealm", "Thora-TestRealm"}}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        fire("CHAT_MSG_WHISPER", {whispered!r}, "Thora-TestRealm")
        assert(#__played == 1 and __played[1][1] == "{LUA_SAMPLE}aaaaaaaaaaaa.ogg")
        -- A stranger's whisper of the same line is not a reaction and is not read.
        __mono = __mono + 10; __now = __now + 400
        fire("CHAT_MSG_WHISPER", {whispered!r}, "Stranger-TestRealm")
        assert(#__played == 1)
    ''')


def test_settings_turn_voices_off_choose_the_interval_and_show_the_pack_link():
    lua = voiced_lua()
    # The settings page is built once; build it again now that this client has voices.
    run_addon_file(lua, ROOT / 'addon/vanilla/WoWStatus/Previews.lua')
    lua.execute('''
        local V = WoWStatusVoices
        local function pick(button, label)
            button.OnClick(button)
            local names, found = {}, nil
            for _, row in ipairs(WoWStatusMenu.rows) do
                if row:IsShown() then
                    names[#names + 1] = row.text.text
                    if row.text.text == label then found = row end
                end
            end
            if not found then error("no " .. label .. " in " .. table.concat(names, ", ")) end
            found.OnClick(found)
            return names
        end
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(panel.voices.checked == true and panel.voiceInterval.text == "Every reaction")
        assert(panel.voiceLink.text == "https://example.invalid/WoWStatus_Voices.zip")
        assert(panel.voicePack.text:find("not installed", 1, true))
        panel.voices:SetChecked(false); panel.voices.OnClick(panel.voices)
        assert(not V.enabled())
        local names = pick(panel.voiceInterval, "10 min")
        assert(names[1] == "Every reaction" and names[#names] == "60 min" and V.interval() == 10)
        assert(panel.voiceInterval.text == "10 min")
        -- The volume slider: picking one saves it and plays a sample through it.
        assert(panel.voiceChannel.text == "Dialog")
        names = pick(panel.voiceChannel, "Master (loudest)")
        assert(names[1] == "Dialog" and names[2] == "Sound effects" and #names == 3)
        assert(V.channel() == "Master" and panel.voiceChannel.text == "Master (loudest)")
        assert(__played[#__played][2] == "Master")
        -- Typing in the link box puts the link back; it is there to copy.
        panel.voiceLink.OnTextChanged(panel.voiceLink, true)
        assert(panel.voiceLink.text == "https://example.invalid/WoWStatus_Voices.zip")
        WoWStatusVoicePack = {version = 2}
        WoWStatusLocale.set("nn")
        WoWStatusPreviews.show()
        assert(panel.voicePack.text == "Røystepakke 2 er installert." and panel.voiceInterval.text == "10 min")
        assert(panel.voiceChannel.text == "Hovudvolum (høgast)")
        pick(panel.voiceInterval, "Kvar reaksjon")
        assert(V.interval() == 0 and #__sent == 0)
    ''')


def test_forever_ships_the_voice_data_before_the_voices():
    toc = (ROOT / 'addon/forever/WoWStatus/WoWStatus.toc').read_text(encoding='utf-8').splitlines()
    assert toc.index('FlavourLegend.lua') < toc.index('VoiceData.lua') < toc.index('Voices.lua') < toc.index(
        'Theme.lua')
    for edition in ('vanilla', 'tbc', 'retail'):
        other = (ROOT / f'addon/{edition}/WoWStatus/WoWStatus.toc').read_text(encoding='utf-8').splitlines()
        assert 'Voices.lua' in other and 'VoiceData.lua' not in other
        assert not (ROOT / f'addon/{edition}/WoWStatus/VoiceData.lua').exists()
    lua = forever_runtime()
    assert lua.eval('WoWStatusVoices.available()') is True
    assert lua.eval('WoWStatusVoiceData.pack.addon') == 'WoWStatus_Voices'


def test_voicetest_plays_a_recorded_line_without_a_friend():
    lua = voiced_lua()
    lua.execute(f'''
        local said
        DEFAULT_CHAT_FRAME.AddMessage = function(_, message) said = message end
        local V = WoWStatusVoices
        -- Without the pack only the addon's own line can play.
        SlashCmdList.WOWSTATUS("voicetest")
        assert(said:find("Spoken reaction test: Wholesome: " .. __nn.gz[1], 1, true), said)
        assert(__played[1][1] == "{LUA_SAMPLE}aaaaaaaaaaaa.ogg")
        SlashCmdList.WOWSTATUS("voicetest")
        assert(said:find("already playing", 1, true) and #__played == 1)
        -- With the pack, "level" plays a level line and then its number; the interval is untouched.
        WoWStatusVoicePack = {{version = 1}}
        __mono = __mono + 10
        SlashCmdList.WOWSTATUS("voicetest hjartevarm level")
        assert(said:find("37", 1, true) and __played[2][1] == "{LUA_PACK}cccccccccccc.ogg" and #__after == 3, said)
        assert(WoWStatusDB.voices == nil or WoWStatusDB.voices.last_at == nil)
        __mono = __mono + 10
        assert(V.heard(__nn.gz[1]))  -- a real reaction still plays at once afterwards
    ''')
    plain = make_lua()
    plain.execute('''
        local said
        DEFAULT_CHAT_FRAME.AddMessage = function(_, message) said = message end
        SlashCmdList.WOWSTATUS("voicetest")
        assert(said:find("only", 1, true) == nil and said:find("WoW Forever", 1, true))
    ''')


def test_with_every_clip_in_the_pack_the_sample_button_plays_from_the_pack():
    lua = voiced_lua()
    lua.execute('WoWStatusVoiceData.lines.wholesome.gz[1] = nil')  # no clip inside the addon
    run_addon_file(lua, ROOT / 'addon/vanilla/WoWStatus/Previews.lua')
    lua.execute(f'''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        panel.voiceTest.OnClick(panel.voiceTest)
        assert(#__played == 0)  -- without the pack there is nothing to play
        WoWStatusVoicePack = {{version = 2}}
        __mono = __mono + 10
        panel.voiceTest.OnClick(panel.voiceTest)
        assert(#__played >= 1 and __played[1][1]:find("{LUA_PACK}", 1, true) == 1)
    ''')


def test_a_bundled_build_plays_every_clip_from_its_own_folder_without_the_pack():
    lua = voiced_lua()
    lua.execute('WoWStatusVoiceData.bundled = true')
    run_addon_file(lua, ROOT / 'addon/vanilla/WoWStatus/Previews.lua')
    lua.execute(f'''
        local V = WoWStatusVoices
        assert(V.bundled() and not V.packInstalled())
        local level = __nn.level[__levelIndex]:gsub("{{level}}", "37")
        assert(V.heard(level))
        assert(__played[1][1] == "{LUA_SAMPLE}cccccccccccc.ogg")
        __after[1][2]()
        assert(__played[2][1] == "{LUA_SAMPLE}dddddddddddd.ogg")
        __mono = __mono + 10; __now = __now + 61
        assert(V.heard(__nn.gz[2]) and __played[3][1] == "{LUA_SAMPLE}bbbbbbbbbbbb.ogg")
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(panel.voicePack.text:find("no voice pack is needed", 1, true))
        assert(panel.voiceGet.visible == false and panel.voiceLink.visible == false)
    ''')
