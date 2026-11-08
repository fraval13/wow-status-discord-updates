"""Reaction whispers on friends' notifications: GZ!, F / Git Good, Congrats!"""
import re

from test_journal import actor, clock, deliver_popup


def label(button):
    """A reaction button's text without the click-guard countdown."""
    return re.sub(r' \(\d\.\d\)$', '', button.text)


def sent_whispers(lua):
    return [(p['text'], p['target']) for p in lua.eval('__sent').values()
            if p['kind'] == 'WHISPER' and not p['prefix']]


def test_level_up_offers_gz_and_whispers_it_once():
    own, friend = actor('Mira'), actor('Thora')
    friend.execute('WoWStatusPopups.CLICK_GUARD = 0  -- this test is not about the click guard')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.reactions[1]:IsShown() and toast.reactions[1].reaction == "GZ!")
        local item = toast.item
        toast.reactions[1].OnClick(toast.reactions[1])
        -- Reacting closes the notification; a second reaction is refused.
        assert(not toast:IsShown())
        assert(not WoWStatusPopups.react(item, "GZ!"))
    ''')
    assert sent_whispers(friend) == [('GZ!', 'Mira-TestRealm')]


def test_each_kind_gets_fitting_reactions():
    lua = actor('Thora')
    lua.execute('''
        local function r(item) return table.concat(WoWStatusPopups.reactions(item), "|") end
        assert(r({sender="Mira-TestRealm", level=10}) == "GZ!|Congrats on level 10!")
        assert(r({sender="Mira-TestRealm", kind="death", text="Died"}) == "F|Git Good")
        assert(r({sender="Mira-TestRealm", kind="zone", text="Entered Stranglethorn Vale"}) == "Enjoy Stranglethorn Vale!")
        for _, kind in ipairs({"profession","dungeon","raid","mount","epicmount","reputation","unlock","pvp","quest","loot"}) do
            assert(r({sender="Mira-TestRealm", kind=kind}) == WoWStatusPopups.CONGRATS[kind], kind)
        end
        assert(r({sender="Mira-TestRealm", kind="loot"}) == "Congrats on the new gear!")
        assert(r({sender="Mira-TestRealm", kind="introduction"}) == "Welcome!")
        -- A record notice names a real friend; sample previews and yourself get nothing.
        assert(r({sender="Mira-TestRealm", kind="first", preview=true, key="local-notice"}) == "Congrats on the record!")
        assert(r({sender="Previewlock", kind="death", preview=true, key="local-preview"}) == "")
        assert(r({sender="Thora-TestRealm", level=10}) == "")
        assert(r({sender="Mira-TestRealm", kind="recap"}) == "")
    ''')


def test_a_hovered_notification_stays_until_the_mouse_leaves():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_DEAD')
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.reactions[1].reaction == "F" and toast.reactions[2].reaction == "Git Good")
        local death = toast.item
        __over = true
        function MouseIsOver(frame) return __over and frame == toast end
        local start = time()
        function time() return start + 30 end
        WoWStatusPopups.tick()
        assert(toast:IsShown() and toast.item == death)
        __over = false
        function time() return start + 40 end
        WoWStatusPopups.tick()
        -- The death notification closed; Mira's "First in the group to die" record follows.
        assert(toast.item ~= death and toast.item.kind == "first")
        assert(toast.reactions[1].reaction == "Congrats on the record!")
    ''')


def test_reaction_whispers_show_on_your_own_log_card():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        __peers = {"Thora-TestRealm", "Mira-TestRealm", "Bob-TestRealm"}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        fire("PLAYER_LEVEL_UP", 2)
        fire("CHAT_MSG_WHISPER", "GZ!", "Mira-TestRealm")
        fire("CHAT_MSG_WHISPER", "Gratulerer!", "Bob-TestRealm")      -- Congrats: not a level reaction
        fire("CHAT_MSG_WHISPER", "GZ!", "Stranger-TestRealm")         -- not in the group
        local own
        for _, e in ipairs(WoWStatusJournal.entries()) do if e.owner and e.kind == "level" then own = e end end
        assert(own.reactions and own.reactions["mira-testrealm"].text == "GZ!")
        assert(not own.reactions["stranger-testrealm"] and not own.reactions["bob-testrealm"])
        assert(WoWStatusJournal.reactionsText(own) == "GZ! from Mira")
        WoWStatusJournal.show()
        assert(WoWStatusActivityLog.rows[1].detail.text:find("GZ! from Mira", 1, true))
    ''')
    # A reaction long after the event is not linked to it.
    clock(lua, 10 + 1000)
    lua.execute('''
        fire("CHAT_MSG_WHISPER", "GZ!", "Bob-TestRealm")
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.owner and e.kind == "level" then assert(not e.reactions["bob-testrealm"]) end
        end
    ''')


def test_death_details_show_zone_and_killer_for_you_and_your_friends():
    from test_roster import pair, pump
    mira, thora = pair()
    pump(mira, thora)
    mira.execute('''
        __hit = {0, "SWING_DAMAGE", false, "Creature-1", "Defias Pillager", 0, 0, UnitGUID("player"), "Mira", 0, 0}
        function CombatLogGetCurrentEventInfo() return (unpack or table.unpack)(__hit) end
        function GetRealZoneText() return "Westfall" end
        fire("COMBAT_LOG_EVENT_UNFILTERED")
        fire("PLAYER_DEAD")
        local own
        for _, e in ipairs(WoWStatusJournal.entries()) do if e.kind == "death" then own = e end end
        assert(WoWStatusJournal.deathText(own):find("Westfall · killed by Defias Pillager", 1, true), WoWStatusJournal.deathText(own))
    ''')
    sent = pump(mira, thora, start=300)
    assert any(line.startswith('K ') and 'Defias_Pillager' in line for line in sent)
    # The death itself reaches Thora as a live update; the details join it by ID.
    thora.execute('''
        local group = next(character().group_ids)
        local nonce
        for id in pairs(WoWStatusDB.journal.details or {}) do nonce = id:match(":([^:]+)$") end
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce=nonce,kind="death",text="Total deaths: 1",at=time(),group_id=group})
        local e
        for _, entry in ipairs(WoWStatusJournal.entries()) do if entry.kind == "death" then e = entry end end
        assert(WoWStatusJournal.deathText(e) == "Total deaths: 1 · Westfall · killed by Defias Pillager", WoWStatusJournal.deathText(e))
    ''')


def pool(lua, key):
    return list(lua.eval(f'WoWStatusLocale.POOLS["{key}"]').values())


def test_nynorsk_gz_has_an_action_label_and_whispers_a_random_greeting():
    own, friend = actor('Mira'), actor('Thora')
    friend.execute('WoWStatusPopups.CLICK_GUARD = 0  -- this test is not about the click guard')
    clock(own, 10)
    clock(friend, 10)
    friend.execute('WoWStatusLocale.set("nn")')
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    shown = friend.eval('''(function()
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.reactions[1].label == "Gratuler")
        local item = toast.item
        toast.reactions[1].OnClick(toast.reactions[1])
        return item.whispered
    end)()''')
    assert shown in pool(friend, 'GZ!')
    assert sent_whispers(friend) == [(shown, 'Mira-TestRealm')]
    # An English-speaking friend's client links any of the lines to the level-up.
    own.execute(f'''
        __peers = {{"Mira-TestRealm", "Thora-TestRealm"}}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        fire("CHAT_MSG_WHISPER", "{shown}", "Thora-TestRealm")
        local e
        for _, item in ipairs(WoWStatusJournal.entries()) do if item.owner and item.kind == "level" then e = item end end
        assert(e.reactions["thora-testrealm"].text == "{shown}")
    ''')


def test_nynorsk_f_and_git_good_are_long_and_count_for_deaths():
    lines = ['Eg tek av meg hjelmen og bøyer hovudet i sorg.', 'Øv deg litt meir, så døyr du kanskje sjeldnare!']
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    friend.execute('WoWStatusLocale.set("nn")')
    assert [friend.eval(f'WoWStatusLocale.T("{t}")') for t in ('F', 'Git Good')] == lines
    own.execute('__peers = {"Mira-TestRealm", "Thora-TestRealm", "Bob-TestRealm"}')
    own.execute('for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end; for _ = 1, 3 do WoWStatusPopups.tick() end')
    own.eval('fire')('PLAYER_DEAD')
    own.execute(f'''
        fire("CHAT_MSG_WHISPER", "{lines[0]}", "Thora-TestRealm")
        fire("CHAT_MSG_WHISPER", "{lines[1]}", "Bob-TestRealm")
        local e
        for _, item in ipairs(WoWStatusJournal.entries()) do if item.owner and item.kind == "death" then e = item end end
        assert(e.reactions["thora-testrealm"].text == "{lines[0]}")
        assert(e.reactions["bob-testrealm"].text == "{lines[1]}")
    ''')


def death_toast(language):
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    friend.execute(f'WoWStatusLocale.set("{language}")')
    own.eval('fire')('PLAYER_DEAD')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    return friend.eval('WoWStatusLevelPopup')


def test_short_reactions_sit_beside_the_heading():
    toast = death_toast('en')
    assert toast.reactionRow == 'top' and toast.height >= 124
    assert [label(toast.reactions[i]) for i in (1, 2)] == ['F', 'Git Good']


def test_nynorsk_death_actions_stay_compact_beside_the_heading():
    toast = death_toast('nn')
    assert toast.reactionRow == 'top'
    assert [label(toast.reactions[i]) for i in (1, 2)] == ['Vis respekt', 'Ert litt']
    assert toast.reactions[1].width + toast.reactions[2].width + 4 <= 300


def test_caption_stays_under_the_fact_when_long_reactions_are_stacked():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    friend.execute('''
        WoWStatusLocale.set("nn")
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetPoint(...) self.point={...} end
        function methods:GetStringHeight() return 46 end
        -- Exercise wrapping independently of the now-short action labels.
        WoWStatusPopups.reactionLabel=function() return string.rep("Long button text ",4) end
        WoWStatusFlavour.text=function() return "Ei lang linje under dødsfallet, med plass til heile teksten." end
    ''')
    own.eval('fire')('PLAYER_DEAD')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    toast=friend.eval('WoWStatusLevelPopup')
    assert toast.detail.point[1]=='TOPLEFT'
    assert toast.detail.point[2]==104 and toast.detail.point[3]==-84
    assert toast.reactionRow=='stacked'
    # The topmost bottom button starts strictly below the 46px caption.
    topmost=min(toast.height-toast.reactions[i].point[3]-24 for i in (1,2))
    assert topmost >= 84+46+6


def test_specific_congrats_link_to_their_own_kind_in_either_language():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        __peers = {"Thora-TestRealm", "Mira-TestRealm", "Bob-TestRealm"}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        fire("PLAYER_LEVEL_UP", 2)
        fire("CHAT_MSG_WHISPER", "Gratulerer med det nye utstyret!", "Bob-TestRealm")  -- gear: not this level-up
        fire("CHAT_MSG_WHISPER", "Gratulerer med nivå 2!", "Mira-TestRealm")
        local own
        for _, e in ipairs(WoWStatusJournal.entries()) do if e.owner and e.kind == "level" then own = e end end
        assert(own.reactions["mira-testrealm"].text == "Gratulerer med nivå 2!")
        assert(not own.reactions["bob-testrealm"])
        WoWStatusLocale.set("nn")
        assert(WoWStatusLocale.T("Congrats on level 30!") == "Gratulerer med nivå 30!")
        assert(WoWStatusLocale.T("Congrats on the new gear!") == "Gratulerer med det nye utstyret!")
    ''')


def test_level_up_buttons_fit_beside_the_heading_in_english():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 30)
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    toast = friend.eval('WoWStatusLevelPopup')
    assert [label(toast.reactions[i]) for i in (1, 2)] == ['GZ!', 'Congrats on level 30!']
    assert toast.reactionRow == 'top' and toast.height >= 124


def level_up_shown(level=42):
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', level)
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    return friend


def test_clicks_in_the_first_moments_are_ignored():
    friend = level_up_shown()
    friend.execute('''
        local toast = WoWStatusLevelPopup
        __mono = 11   -- one second after it appeared: a stray click
        toast.reactions[1].OnClick(toast.reactions[1])
        toast.OnMouseUp(toast, "LeftButton")
        assert(toast:IsShown() and toast.reactions[1]:IsShown())
        __mono = 11.6 -- after 1.5 seconds clicks count: the reaction is sent and it closes
        toast.reactions[1].OnClick(toast.reactions[1])
        assert(not toast:IsShown())
    ''')
    assert sent_whispers(friend) == [('GZ!', 'Mira-TestRealm')]


def log_card(friend):
    friend.execute('WoWStatusJournal.show()')
    return friend.eval('''(function()
        for _, row in ipairs(WoWStatusActivityLog.rows) do
            if row:IsShown() and row.entry.kind == "level" and not row.entry.owner then return row end
        end
    end)()''')


def test_the_log_card_offers_the_reactions_for_a_minute():
    friend = level_up_shown()
    row = log_card(friend)
    assert row.reactions[1].text == 'GZ!' and row.reactions[2].text == 'Congrats on level 42!'
    friend.execute('__now = __now + 30')
    row = log_card(friend)
    row.reactions[2].OnClick(row.reactions[2])
    assert sent_whispers(friend) == [('Congrats on level 42!', 'Mira-TestRealm')]
    row = log_card(friend)
    assert not row.reactions[1].IsShown(row.reactions[1])
    assert 'You whispered “Congrats on level 42!”' in row.detail.text
    # The notification still on screen lost its buttons too: no second whisper.
    friend.execute('''
        local toast = WoWStatusLevelPopup
        __mono = 20
        if toast.reactions[1]:IsShown() then toast.reactions[1].OnClick(toast.reactions[1]) end
    ''')
    assert len(sent_whispers(friend)) == 1


def test_log_buttons_expire_after_a_minute():
    friend = level_up_shown()
    assert log_card(friend).reactions[1].IsShown(log_card(friend).reactions[1])
    friend.execute('__now = __now + 61')
    row = log_card(friend)
    assert not row.reactions[1].IsShown(row.reactions[1])


def test_reacting_on_the_notification_removes_the_log_buttons():
    friend = level_up_shown()
    friend.execute('''
        __mono = 12
        local toast = WoWStatusLevelPopup
        toast.reactions[1].OnClick(toast.reactions[1])
    ''')
    row = log_card(friend)
    first = row.reactions and row.reactions[1]
    assert first is None or not first.IsShown(first)
    assert 'You whispered “GZ!”' in row.detail.text


def test_caught_up_entries_have_no_reaction_buttons():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=5,at=time(),group_id=group})
        WoWStatusJournal.show()
        local row = WoWStatusActivityLog.rows[1]
        assert(row.entry.kind == "level")
        assert(not row.reactions or not row.reactions[1] or not row.reactions[1]:IsShown())
    ''')


def test_the_next_notification_follows_after_a_reaction():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.item.level == 42)
        WoWStatusPopups.preview("death")   -- waits in the queue
        __mono = 12
        toast.reactions[1].OnClick(toast.reactions[1])
        assert(not toast:IsShown())
        WoWStatusPopups.tick()
        assert(toast:IsShown() and toast.item.kind == "death")
    ''')


def test_buttons_are_greyed_and_count_down_during_the_click_guard():
    own, friend = actor('Mira'), actor('Thora')
    friend.execute('''
        local methods = getmetatable(CreateFrame("Button")).__index
        function methods:Disable() self.disabled = true end
        function methods:Enable() self.disabled = false end
    ''')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        local gz = toast.reactions[1]
        assert(gz.text == "GZ! (1.5)" and gz.disabled, gz.text)
        __mono = 11
        toast.OnUpdate(toast, 1)
        assert(gz.text == "GZ! (0.5)" and gz.disabled, gz.text)
        __mono = 11.6
        toast.OnUpdate(toast, .6)
        assert(gz.text == "GZ!" and gz.disabled == false, gz.text)
    ''')


def test_the_nynorsk_lines_are_twenty_each_and_fit_a_whisper():
    lua = actor('Thora')
    for key in ('GZ!', 'F', 'Enjoy'):
        lines = pool(lua, key)
        assert len(lines) == 20 and len(set(lines)) == 20, key
        for line in lines:
            assert len(line.replace('{zone}', 'x' * 48).encode()) <= 160, line
            if key == 'Enjoy':
                assert line.count('{zone}') == 1, line


def test_random_lines_link_to_their_event_and_zone():
    lua = actor('Thora')
    clock(lua, 10)
    zone_line = pool(lua, 'Enjoy')[3].replace('{zone}', 'Elwynn Forest')
    f_line = pool(lua, 'F')[7]
    lua.execute(f'''
        __peers = {{"Thora-TestRealm", "Mira-TestRealm", "Bob-TestRealm"}}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        function GetRealZoneText() return "Elwynn Forest" end
        fire("ZONE_CHANGED_NEW_AREA")
        fire("PLAYER_DEAD")
        fire("CHAT_MSG_WHISPER", "{zone_line}", "Mira-TestRealm")
        fire("CHAT_MSG_WHISPER", "{f_line}", "Bob-TestRealm")
        local zone, death
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.owner and e.kind == "zone" then zone = e end
            if e.owner and e.kind == "death" then death = e end
        end
        assert(zone and zone.reactions and zone.reactions["mira-testrealm"], "zone")
        assert(death.reactions["bob-testrealm"].text == "{f_line}")
    ''')


def test_english_buttons_keep_their_one_line():
    toast = death_toast('en')
    assert [toast.reactions[i].label for i in (1, 2)] == ['F', 'Git Good']


def test_nynorsk_action_labels_are_stable_across_events_and_reaction_voices():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusLocale.set("nn")
        local P = WoWStatusPopups
        local expected = {
            ["GZ!"]="Gratuler", ["F"]="Vis respekt", ["Git Good"]="Ert litt",
            ["Congrats on level 42!"]="Feir nivået", ["Enjoy Stranglethorn Vale!"]="Ynsk god tur",
            ["Welcome!"]="Ynsk velkomen", ["Congrats!"]="Gratuler",
        }
        for _, reaction in pairs(P.CONGRATS) do expected[reaction]="Gratuler" end
        for _, voice in ipairs(WoWStatusPersonalities.reactionVoices()) do
            assert(WoWStatusPersonalities.setReaction(voice))
            for reaction, label in pairs(expected) do
                local item = {}
                assert(P.reactionLabel(item, reaction)==label, voice..":"..reaction)
                assert(P.reactionLabel(item, reaction)==label)
                assert(P.reactionText(item, reaction)~=label)
            end
        end
    ''')
    assert sent_whispers(lua) == []


def test_nynorsk_log_actions_send_the_whisper_and_record_it_once():
    friend = level_up_shown()
    friend.execute('''
        WoWStatusLocale.set("nn")
        WoWStatusPersonalities.setReaction("wholesome")
    ''')
    row = log_card(friend)
    assert row.reactions[1].text == 'Gratuler'
    assert row.reactions[2].text == 'Feir nivået'
    expected = friend.eval('WoWStatusPopups.reactionText')(row.entry, 'GZ!')
    bank = friend.eval('WoWStatusPersonalities.reactionBanks("wholesome")')[1]
    assert expected in list(bank.gz.values())
    row.reactions[1].OnClick(row.reactions[1])
    assert sent_whispers(friend) == [(expected, 'Mira-TestRealm')]
    assert row.entry.whispered == expected
    row.reactions[1].OnClick(row.reactions[1])
    assert len(sent_whispers(friend)) == 1
