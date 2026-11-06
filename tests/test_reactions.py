"""Reaction whispers on friends' notifications: GZ!, F / Git Good, Congrats!"""
from test_journal import actor, clock, deliver_popup


def sent_whispers(lua):
    return [(p['text'], p['target']) for p in lua.eval('__sent').values()
            if p['kind'] == 'WHISPER' and not p['prefix']]


def test_level_up_offers_gz_and_whispers_it_once():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.reactions[1]:IsShown() and toast.reactions[1].text == "GZ!")
        toast.reactions[1].OnClick(toast.reactions[1])
        assert(not toast.reactions[1]:IsShown())
        assert(toast.detail.text:find("GZ!", 1, true))
        -- A second click is not possible, and a direct second reaction is refused.
        assert(not WoWStatusPopups.react(toast.item, "GZ!"))
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
        assert(toast.reactions[1].text == "F" and toast.reactions[2].text == "Git Good")
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
        assert(toast.reactions[1].text == "Congrats on the record!")
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


def test_nynorsk_gz_is_the_long_wish_and_counts_as_gz():
    long_gz = 'Eg ynskjer deg hjarteleg til lukke med det nye nivået!'
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    friend.execute('WoWStatusLocale.set("nn")')
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.reactions[1].OnClick(toast.reactions[1])
    ''')
    assert sent_whispers(friend) == [(long_gz, 'Mira-TestRealm')]
    # An English-speaking friend's client links the long wish to the level-up.
    own.execute(f'''
        __peers = {{"Mira-TestRealm", "Thora-TestRealm"}}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        fire("CHAT_MSG_WHISPER", "{long_gz}", "Thora-TestRealm")
        local e
        for _, item in ipairs(WoWStatusJournal.entries()) do if item.owner and item.kind == "level" then e = item end end
        assert(e.reactions["thora-testrealm"].text == "{long_gz}")
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
    assert toast.reactionRow == 'top' and toast.height == 124
    assert [toast.reactions[i].text for i in (1, 2)] == ['F', 'Git Good']


def test_long_reactions_get_rows_along_the_bottom():
    toast = death_toast('nn')
    # Two long lines: one row each, under the text, at full width.
    assert toast.reactionRow == 'stacked' and toast.height == 124 + 2 * 28 + 6
    for i, text in ((1, 'Eg tek av meg hjelmen og bøyer hovudet i sorg.'), (2, 'Øv deg litt meir, så døyr du kanskje sjeldnare!')):
        button = toast.reactions[i]
        assert button.text == text
        assert button.width == max(86, len(text.encode()) * 6 + 24) and button.width <= 536


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
    assert [toast.reactions[i].text for i in (1, 2)] == ['GZ!', 'Congrats on level 30!']
    assert toast.reactionRow == 'top' and toast.height == 124
