"""Reaction voices: GZ!, F and Congrats! whispers in a chosen personality's voice."""
from test_addon import make_lua
from test_journal import actor, clock, deliver_popup
from test_personalities import builder
from test_reactions import sent_whispers

BUILD = builder()
# Reaction voices that ship, in menu order; the first is the one used below.
READY = tuple(p.id for p in BUILD.PERSONALITIES if p.id in BUILD.REACTION_VOICES)
NAMES = {p.id: p.name for p in BUILD.PERSONALITIES}
VOICE = READY[0]

KEYS = ('gz', 'level', 'f', 'gitgood', 'welcome', 'enjoy', 'congrats', 'congrats_loot', 'congrats_quest',
        'congrats_profession', 'congrats_dungeon', 'congrats_raid', 'congrats_mount', 'congrats_epicmount',
        'congrats_reputation', 'congrats_unlock', 'congrats_pvp', 'congrats_first')


def test_every_voice_has_paired_reaction_banks_of_300():
    lua = make_lua()
    lua.execute(f'''
        local P=WoWStatusPersonalities
        local keys={{{", ".join(repr(k).replace("'", '"') for k in KEYS)}}}
        local voices=P.reactionVoices()
        assert(#voices=={2 + len(READY)} and voices[1]=="random" and voices[2]=="classic")
        for i=3,#voices do
            local en,nn=P.reactionBanks(voices[i])
            for _,key in ipairs(keys) do
                assert(#en[key]==300 and #nn[key]==300, voices[i]..key)
                for pos,line in ipairs(en[key]) do
                    local slot=(key=="level" and "{{level}}") or (key=="enjoy" and "{{zone}}")
                    if slot then assert(line:find(slot,1,true) and nn[key][pos]:find(slot,1,true), voices[i]..key..pos) end
                end
            end
        end
        assert(not P.reactionBanks("classic") and not P.reactionBanks("random"))
    ''')


def test_reaction_voice_is_its_own_setting_and_defaults_to_wholesome():
    lua = make_lua(reaction_default=None)
    lua.globals().VOICE = READY[-1]
    lua.execute('''
        local P=WoWStatusPersonalities
        assert(P.reactionVoice()=="wholesome" and P.current()=="random")
        assert(WoWStatusDB.reaction_voice==nil and P.reactionLine("gz"))
        assert(P.setReaction(VOICE) and WoWStatusDB.reaction_voice==VOICE and P.current()=="random")
        assert(P.set("bard") and P.reactionVoice()==VOICE)
        -- Classic is a choice of its own and saved as such; Wholesome is saved as no choice.
        assert(P.setReaction("classic") and WoWStatusDB.reaction_voice=="classic" and P.reactionLine("gz")==nil)
        assert(P.setReaction("wholesome") and WoWStatusDB.reaction_voice==nil)
        WoWStatusDB.reaction_voice="pirate"
        assert(P.reactionVoice()=="wholesome" and not P.setReaction("pirate"))
        assert(P.findReaction("Klassisk")=="classic" and P.findReaction("Tilfeldig")=="random")
        -- Without Wholesome's lines, the default falls back to Classic.
        P.defs.wholesome.reactions=nil
        assert(P.reactionVoice()=="classic")
    ''')


def test_a_default_gz_whispers_a_wholesome_line():
    own, friend = actor('Mira'), actor('Thora')
    friend.execute('WoWStatusPopups.CLICK_GUARD = 0  -- this test is not about the click guard')
    friend.execute('WoWStatusPersonalities.REACTION_DEFAULT = "wholesome"  -- the shipped default')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    whispered = friend.eval('''(function()
        WoWStatusPopups.tick()
        local button = WoWStatusLevelPopup.reactions[1]
        assert(button.label == "GZ!")
        local item = WoWStatusLevelPopup.item
        button.OnClick(button)
        return item.whispered
    end)()''')
    assert whispered in list(friend.eval('WoWStatusPersonalities.reactionBanks("wholesome")')[0].gz.values())


def test_voiced_lines_fill_level_and_zone_and_follow_the_language():
    lua = make_lua()
    lua.globals().VOICE = VOICE
    lua.execute('''
        local P=WoWStatusPersonalities
        P.setReaction(VOICE)
        local en,nn=P.reactionBanks(VOICE)
        local function member(pool,text,slot,value)
            for _,line in ipairs(pool) do
                local filled=slot and line:gsub(slot:gsub("[{}]","%%%0"),value) or line
                if filled==text then return true end
            end
        end
        for i=1,30 do
            assert(member(en.gz,P.reactionLine("gz")))
            local level=P.reactionLine("level","42")
            assert(level:find("42",1,true) and not level:find("{",1,true) and member(en.level,level,"{level}","42"))
            local zone=P.reactionLine("enjoy","Stranglethorn Vale")
            assert(zone:find("Stranglethorn Vale",1,true) and member(en.enjoy,zone,"{zone}","Stranglethorn Vale"))
        end
        WoWStatusLocale.set("nn")
        assert(member(nn.f,P.reactionLine("f")))
        -- Random draws Classic (nil) as well as voices.
        P.setReaction("random")
        local classic,voiced=false,false
        for i=1,300 do if P.reactionLine("gz") then voiced=true else classic=true end end
        assert(classic and voiced)
    ''')


def test_a_voiced_gz_whispers_the_line_but_the_button_stays_short():
    own, friend = actor('Mira'), actor('Thora')
    friend.execute('WoWStatusPopups.CLICK_GUARD = 0  -- this test is not about the click guard')
    clock(own, 10)
    clock(friend, 10)
    friend.execute(f'WoWStatusPersonalities.setReaction("{VOICE}")')
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    whispered = friend.eval('''(function()
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        local button = toast.reactions[1]
        assert(button.reaction == "GZ!" and button.label == "GZ!")
        local item = toast.item
        button.OnClick(button)
        return item.whispered
    end)()''')
    voiced = list(friend.eval(f'WoWStatusPersonalities.reactionBanks("{VOICE}")')[0].gz.values())
    assert whispered in voiced and whispered != 'GZ!'
    assert sent_whispers(friend) == [(whispered, 'Mira-TestRealm')]
    # Mira's client, in English with Classic reactions, counts the voiced line as a GZ!.
    own.execute(f'''
        __peers = {{"Mira-TestRealm", "Thora-TestRealm"}}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        fire("CHAT_MSG_WHISPER", {whispered!r}, "Thora-TestRealm")
        local e
        for _, item in ipairs(WoWStatusJournal.entries()) do if item.owner and item.kind == "level" then e = item end end
        assert(e.reactions["thora-testrealm"].text == {whispered!r})
    ''')


def test_every_voice_line_is_recognised_with_its_kind_and_zone():
    lua = make_lua()
    lua.execute('''
        local P=WoWStatusPersonalities
        for _,id in ipairs(P.reactionVoices()) do
            local en,nn=P.reactionBanks(id)
            for _,set in ipairs({en or {},nn or {}}) do
                for key,lines in pairs(set) do
                    for _,line in ipairs(lines) do
                        local text=line:gsub("{level}","17"):gsub("{zone}","Duskwood")
                        local found,value=P.matchReaction(text)
                        assert(found, id..": "..text)
                        -- Lines that read alike may share a key family; the slot value is exact.
                        if key=="enjoy" then assert(found=="enjoy" and value=="Duskwood", text) end
                        if key=="level" then assert(found=="level" and value=="17", text) end
                    end
                end
            end
        end
        assert(P.matchReaction("hello there")==nil)
    ''')


def test_settings_dropdown_picks_the_reaction_voice_without_sending():
    lua = make_lua()
    g = lua.globals()
    g.VOICE, g.NAME, g.LAST = VOICE, NAMES[VOICE], NAMES[READY[-1]]
    g.STEPS = len(READY)
    lua.execute('''
        local P=WoWStatusPersonalities
        -- Pick an entry by its label from the dropdown the button opens.
        local function pick(button,label)
            button.OnClick(button)
            local menu,names,found=WoWStatusMenu,{},nil
            for _,row in ipairs(menu.rows) do
                if row:IsShown() then
                    names[#names+1]=row.text.text
                    if row.text.text==label then found=row end
                end
            end
            if not found then error("no "..label.." in "..table.concat(names,", ")) end
            found.OnClick(found)
            return names
        end
        WoWStatusPreviews.show()
        local panel=WoWStatusNotificationPreviews
        assert(panel.reactionVoicePick.text=="Classic")  -- the harness default
        local names=pick(panel.reactionVoicePick,NAME)
        assert(#names==STEPS+2 and names[1]=="Random" and names[2]=="Classic")
        assert(P.reactionVoice()==VOICE and panel.reactionVoicePick.text==NAME)
        assert(P.current()=="random" and #__sent==0)
        pick(panel.reactionVoicePick,"Random")
        assert(P.reactionVoice()=="random")
        pick(panel.reactionVoicePick,"Classic")
        assert(P.reactionVoice()=="classic")
        local said
        DEFAULT_CHAT_FRAME.AddMessage=function(_,message) said=message end
        SlashCmdList.WOWSTATUS("voice "..NAME:lower())
        assert(P.reactionVoice()==VOICE and said:find("Reaction voice: "..NAME..".",1,true))
        SlashCmdList.WOWSTATUS("voice")
        assert(said:find(LAST,1,true))
        -- A personality without reaction lines yet is not a reaction voice.
        assert(P.findReaction("Goblin merchant")==nil or P.reactionBanks("goblin"))
        WoWStatusLocale.set("nn")
        WoWStatusPreviews.show()
        assert(panel.reactionVoicePick.text==P.name(P.reactionVoice()))
    ''')
