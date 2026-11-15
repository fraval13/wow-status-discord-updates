"""Muting one friend's notifications without leaving the group (#169)."""
import re
from pathlib import Path

from test_addon import lupa
from test_gamepad import FRAMES, main_window
from test_journal import actor, clock, deliver_popup, join_roster
from test_profile import open_profile
from test_roster import pair, pump

ROOT = Path(__file__).parents[1]


def level_up(muted=None):
    """Mira levels up and Thora receives it, with Mira muted first if asked."""
    mira, thora = actor('Mira'), actor('Thora')
    clock(mira, 10)
    clock(thora, 10)
    if muted:
        assert thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', muted) is True
    mira.eval('fire')('PLAYER_LEVEL_UP', 40)
    deliver_popup(mira, thora)
    thora.eval('WoWStatusPopups.tick')()
    return mira, thora


def popup_shown(lua):
    return lua.eval('WoWStatusLevelPopup ~= nil and WoWStatusLevelPopup:IsShown()') is True


def logged(lua, level=40):
    return lua.eval(f'''(function()
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.sender == "Mira-TestRealm" and e.level == {level} then return true end
        end
        return false
    end)()''')


def visible(lua, level=40):
    return lua.eval(f'''(function()
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.sender == "Mira-TestRealm" and e.level == {level} then return WoWStatusJournal.visible(e) end
        end
        return nil
    end)()''')


def sent(lua):
    """Everything the client sent, with each run's random event IDs made alike."""
    return [re.sub(r'\b\d{10}-\d+-\d+-[0-9a-f]+\b', 'EVENT', p['prefix'] + ' ' + p['text'])
            for p in lua.eval('__sent').values()]


def test_unmuted_friend_still_gets_a_popup():
    _, thora = level_up()
    assert popup_shown(thora)
    assert logged(thora) and visible(thora)


def test_log_only_keeps_the_entry_and_skips_the_popup():
    _, thora = level_up('log')
    assert not popup_shown(thora)
    assert logged(thora) and visible(thora)
    assert thora.eval('WoWStatusDB.popups.last_receive.state') == 'muted'
    # Records still count a "Log only" friend.
    assert thora.eval('''(function()
        local group = next(character().group_ids)
        local result = WoWStatusFirsts.compute(WoWStatusJournal.entries(), group)
        for _, e in pairs(result) do if e.sender == "Mira-TestRealm" then return true end end
        return false
    end)()''')


def test_nothing_about_a_mute_leaves_the_client():
    _, plain = level_up()
    _, muted = level_up('log')
    _, hidden = level_up('hide')
    # The same packets as without a mute: the delivery confirmation included,
    # so the muted friend cannot tell.
    assert sent(muted) == sent(plain) and sent(hidden) == sent(plain)
    assert any(' WSACK ' in text for text in sent(plain))
    before = len(sent(muted))
    muted.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'hide')
    muted.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'show')
    for t in range(11, 40):
        clock(muted, t)
        muted.eval('WoWStatusPopups.tick')()
    assert len(sent(muted)) == before


def test_hide_completely_leaves_them_out_of_every_page_until_unmuted():
    _, thora = level_up('hide')
    assert not popup_shown(thora)
    assert logged(thora)  # still in the log itself, and relayed as before
    assert visible(thora) is False
    thora.execute('WoWStatusJournal.show()')
    entries = thora.eval('WoWStatusActivityLog.entriesList')
    assert not any(entries[i].sender == 'Mira-TestRealm' for i in range(1, len(entries) + 1))
    assert thora.eval('''(function()
        local group = next(character().group_ids)
        local result = WoWStatusFirsts.compute(WoWStatusJournal.entries(), group)
        for _, e in pairs(result) do if e.sender == "Mira-TestRealm" then return false end end
        return true
    end)()''')
    assert thora.eval('WoWStatusJournal.latestFriend()') is None
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'show')
    assert visible(thora) is True
    assert thora.eval('WoWStatusJournal.latestFriend().sender') == 'Mira-TestRealm'


def test_hide_applies_to_recovered_catch_up_entries():
    thora = actor('Thora')
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'hide')
    thora.execute('''
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=40,at=time()-60,group_id=group})
    ''')
    assert logged(thora) and visible(thora) is False


def test_record_notices_for_a_muted_friend_are_skipped():
    thora = actor('Thora')
    notice = thora.eval('WoWStatusPopups.notice')
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'log')
    assert notice(thora.eval('{sender="Mira-TestRealm", kind="first", text="First to 10!"}')) is False
    assert notice(thora.eval('{sender="Eldrin-TestRealm", kind="first", text="First to 10!"}')) is True


def test_own_characters_cannot_be_muted():
    thora = actor('Thora')
    thora.eval('WoWStatusMutes.setCharacter')('Thora-TestRealm', 'hide')
    assert thora.eval('WoWStatusMutes.mode("Thora-TestRealm")') == 'show'


def test_mute_all_of_a_players_characters_and_the_stronger_setting_wins():
    mira, thora = pair()
    pump(mira, thora)
    choices = thora.eval('WoWStatusMutes.choices("Mira-TestRealm")')
    labels = [choices[i].label for i in range(1, len(choices) + 1)]
    assert labels[:3] == ['Show popups', 'Log only', 'Hide completely']
    assert "All characters of Frank: log only" in labels
    pick = next(choices[i].value for i in range(1, len(choices) + 1)
                if choices[i].label == "All characters of Frank: hide completely")
    assert thora.eval('WoWStatusMutes.pick')('Mira-TestRealm', pick) is True
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'hide'
    assert thora.eval('WoWStatusMutes.hidden("Mira-TestRealm")') is True
    # The leaderboard leaves a hidden friend out.
    group = thora.eval('(next(character().group_ids))')
    board = thora.eval(f'WoWStatusRoster.leaderboard("{group}")')
    assert not any(board[i].name == 'Mira-TestRealm' for i in range(1, len(board) + 1))
    # A character set to Log only under a hidden player stays hidden.
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'log')
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'hide'
    thora.eval('WoWStatusMutes.set')('player', pick.id, 'show')
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'log'
    board = thora.eval(f'WoWStatusRoster.leaderboard("{group}")')
    assert any(board[i].name == 'Mira-TestRealm' for i in range(1, len(board) + 1))


def test_the_profile_mutes_and_the_card_says_so():
    mira, thora = pair()
    pump(mira, thora)
    view = open_profile(thora, 'Mira')
    assert view.mute.IsShown(view.mute) and view.mute.text == 'Mute'
    view.mute.OnClick(view.mute)
    pick = next(r for r in thora.eval('WoWStatusMenu.rows').values() if r.IsShown(r) and r.text.text == 'Log only')
    pick.OnClick(pick)
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'log'
    assert view.mute.text == 'Muted'
    thora.eval('SlashCmdList.WOWSTATUS')('characters')
    count = thora.eval('WoWStatusCharactersPage.count')
    card = next(thora.eval(f'WoWStatusCharactersPage.lines[{i}]') for i in range(1, count + 1)
                if 'Mira' in thora.eval(f'WoWStatusCharactersPage.lines[{i}]').name.text)
    assert 'muted' in card.status.text
    # Your own profile has no Mute button.
    own = open_profile(thora, 'Thora')
    assert not own.mute.IsShown(own.mute)


def test_the_muted_list_shows_and_unmutes():
    mira, thora = pair()
    pump(mira, thora)
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'log')
    thora.eval('WoWStatusMutes.set')('player', thora.eval('WoWStatusRoster.playerIdOf("Mira-TestRealm")'), 'hide')
    thora.eval('SlashCmdList.WOWSTATUS')('mutes')
    frame = thora.eval('WoWStatusMutedFriends')
    assert frame.IsShown(frame)
    assert 'WoWStatusMutedFriends' in thora.eval('UISpecialFrames').values()
    rows = [frame.rows[i] for i in range(1, len(frame.rows) + 1) if frame.rows[i].IsShown(frame.rows[i])]
    assert [r.name.text for r in rows] == ['Frank (all characters)', 'Mira']
    assert [r.mode.text for r in rows] == ['Hide completely', 'Log only']
    rows[0].unmute.OnClick(rows[0].unmute)
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'log'
    rows = [frame.rows[i] for i in range(1, len(frame.rows) + 1) if frame.rows[i].IsShown(frame.rows[i])]
    assert [r.name.text for r in rows] == ['Mira']
    rows[0].mode.OnClick(rows[0].mode)
    pick = next(r for r in thora.eval('WoWStatusMenu.rows').values() if r.IsShown(r) and r.text.text == 'Hide completely')
    pick.OnClick(pick)
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'hide'
    rows[0].unmute.OnClick(rows[0].unmute)
    assert thora.eval('WoWStatusMutes.count()') == 0
    assert frame.empty.IsShown(frame.empty)


def test_the_notifications_settings_open_the_muted_list():
    thora = actor('Thora')
    thora.execute('WoWStatusPreviews.show()')
    button = thora.eval('WoWStatusNotificationPreviews.mutes')
    button.OnClick(button)
    assert thora.eval('WoWStatusMutedFriends:IsShown()') is True


def test_mutes_survive_reload_and_malformed_saved_values_are_dropped():
    thora = actor('Thora')
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'log')
    thora.execute('''
        WoWStatusDB.mutes.characters["bad"] = {mode="loud"}
        WoWStatusDB.mutes.characters[7] = {mode="log"}
        WoWStatusDB.mutes.players["x"] = "hide"
        WoWStatusMutes.init(WoWStatusDB)
    ''')
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'log'
    assert thora.eval('WoWStatusMutes.count()') == 1
    thora.execute('WoWStatusDB.mutes = "nonsense"; WoWStatusMutes.init(WoWStatusDB)')
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'show'
    assert thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'hide') is True
    assert thora.eval('WoWStatusMutes.set')('character', 'x', 'loud') is False


def test_mutes_are_capped():
    thora = actor('Thora')
    thora.execute('for i = 1, WoWStatusMutes.MAX do assert(WoWStatusMutes.set("character", "c" .. i, "log")) end')
    assert thora.eval('WoWStatusMutes.set')('character', 'one-more', 'log') is False
    assert thora.eval('WoWStatusMutes.set')('character', 'c1', 'hide') is True  # changing one is fine


def test_mute_texts_are_nynorsk():
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('WoWStatusLocale.set("nn")')
    choices = thora.eval('WoWStatusMutes.choices("Mira-TestRealm")')
    labels = [choices[i].label for i in range(1, len(choices) + 1)]
    assert labels[:3] == ['Vis varsel', 'Berre logg', 'Gøym heilt']
    assert 'Alle figurane til Frank: berre logg' in labels


def test_the_muted_list_is_reachable_with_a_controller():
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('unpack = unpack or table.unpack')
    lua.execute(FRAMES)
    lua.execute((ROOT / 'addon/shared/Gamepad.lua').read_text(encoding='utf-8'))
    main_window(lua)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:SetSize(w,h) self.rect[3],self.rect[4]=w,h end
        function methods:SetText(text) self.text=text end
        function methods:CreateFontString() return CreateFrame("FontString",nil,self) end
        function methods:SetJustifyH() end
        function methods:SetShown(value) self.visible=value end
        function methods:SetScrollChild(child) self.child=child end
        WoWStatusLocale={T=function(text) return text end,F=string.format}
        WoWStatusSafe={string=function(v) return type(v)=="string" and v~="" and v or nil end,
            number=function(v) return type(v)=="number" and v or nil end, lowerASCII=string.lower}
        WoWStatusRoster={key=function(name) return name:lower() end}
        WoWStatusUI={text=function(parent) return CreateFrame("FontString",nil,parent) end}
        function time() return 1793000000 end
    ''')
    lua.execute((ROOT / 'addon/shared/Mutes.lua').read_text(encoding='utf-8'))
    lua.execute('''
        main:Hide()
        WoWStatusMutes.init(WoWStatusDB)
        WoWStatusMutes.setCharacter("Mira-Realm", "log")
        local frame=WoWStatusMutes.show()
        frame.rect={100,100,560,420}
        local row=frame.rows[1]
        row.mode.rect={340,400,140,26}; row.unmute.rect={480,400,96,26}; frame.close.rect={500,120,130,26}
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(frame,{frame})) do reached[control]=true end
        assert(reached[row.mode] and reached[row.unmute] and reached[frame.close])
        WoWStatusGamepad.update()
        press("PADDDOWN")
        WoWStatusGamepad.setFocus(row.unmute);press("PAD1")
        assert(WoWStatusMutes.mode("Mira-Realm")=="show")
        press("PAD2")
        assert(not frame:IsShown())
    ''')


def deliver_latest(sender, receiver):
    """Deliver the sender's newest live update (deliver_popup sends the first)."""
    packet = sender.eval('__sent[#__sent].text')
    name = sender.eval('WoWStatusAdapter.playerName()') + '-TestRealm'
    join_roster(receiver, name)
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', name)


def test_muting_drops_popups_already_waiting():
    mira, thora = level_up()
    assert popup_shown(thora)
    mira.eval('fire')('PLAYER_LEVEL_UP', 41)
    for t in range(11, 20):  # the second update goes out on a later tick
        clock(mira, t)
        mira.eval('WoWStatusPopups.tick')()
    deliver_latest(mira, thora)
    assert popup_shown(thora)
    assert logged(thora, 41)
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'log')
    assert not popup_shown(thora)  # the one on screen goes away
    for t in range(11, 40):
        clock(thora, t)
        thora.eval('WoWStatusPopups.tick')()
        assert not popup_shown(thora)  # and the waiting one never shows
    assert logged(thora, 40) and logged(thora, 41)


def test_log_only_entries_are_logged_even_when_the_popup_queue_is_full():
    mira, thora = actor('Mira'), actor('Thora')
    clock(mira, 10)
    clock(thora, 10)
    thora.execute('''
        for i = 1, 130 do WoWStatusPopups.notice({sender="Eldrin-TestRealm", kind="first", text="Record " .. i}) end
        WoWStatusPopups.tick()
        WoWStatusPopups.notice({sender="Eldrin-TestRealm", kind="first", text="One more"})
        WoWStatusPopups.tick()
    ''')
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'log')
    mira.eval('fire')('PLAYER_LEVEL_UP', 40)
    deliver_popup(mira, thora)
    assert logged(thora)
    assert thora.eval('WoWStatusDB.popups.last_receive.state') == 'muted'


def test_a_player_mute_holds_after_their_list_is_forgotten():
    mira, thora = pair()
    pump(mira, thora)
    pid = thora.eval('WoWStatusRoster.playerIdOf("Mira-TestRealm")')
    thora.eval('WoWStatusMutes.set')('player', pid, 'hide')
    assert thora.eval('WoWStatusMutes.hidden("Mira-TestRealm")') is True
    # Mira stops sharing her list (or newer players push it out).
    thora.execute(f'WoWStatusDB.roster.players["{pid}"] = nil')
    clock(thora, 1000)
    assert thora.eval('WoWStatusRoster.playerIdOf("Mira-TestRealm")') is None
    assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'hide'
    rows = thora.eval('WoWStatusMutes.list()')
    assert rows[1].kind == 'player' and rows[1].name == 'Frank'


def test_one_character_under_two_player_ids_follows_either_mute():
    mira, thora = pair()
    pump(mira, thora)
    pid = thora.eval('WoWStatusRoster.playerIdOf("Mira-TestRealm")')
    # After a reinstall Mira's character is also listed under a new player ID.
    thora.execute(f'''
        local old = WoWStatusDB.roster.players["{pid}"]
        local copy = {{name=old.name, groups=old.groups, characters={{}}}}
        for k, c in pairs(old.characters) do copy.characters[k] = c end
        WoWStatusDB.roster.players["ffffffffffffffff"] = copy
    ''')
    for id in (pid, 'ffffffffffffffff'):
        thora.eval('WoWStatusMutes.set')('player', id, 'log')
        assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'log'
        thora.eval('WoWStatusMutes.set')('player', id, 'show')
        assert thora.eval('WoWStatusMutes.mode("Mira-TestRealm")') == 'show'


def test_hidden_friends_reactions_are_not_kept_and_muted_ones_are_not_read_aloud():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        __peers = {"Thora-TestRealm", "Mira-TestRealm", "Bob-TestRealm"}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _ = 1, 3 do WoWStatusPopups.tick() end
        __heard = {}
        WoWStatusVoices.heard = function(text) table.insert(__heard, text) end
        WoWStatusMutes.setCharacter("Mira-TestRealm", "hide")
        WoWStatusMutes.setCharacter("Bob-TestRealm", "log")
        fire("PLAYER_LEVEL_UP", 2)
        fire("CHAT_MSG_WHISPER", "GZ!", "Mira-TestRealm")
        fire("CHAT_MSG_WHISPER", "GZ!", "Bob-TestRealm")
        local own
        for _, e in ipairs(WoWStatusJournal.entries()) do if e.owner and e.kind == "level" then own = e end end
        assert(not own.reactions["mira-testrealm"])
        assert(own.reactions["bob-testrealm"].text == "GZ!")
        assert(#__heard == 0)
    ''')


def test_the_profile_redraws_when_hidden_and_unmuted():
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('''
        local group = next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-a",kind="level",level=2,at=time()-60,group_id=group})
    ''')
    view = open_profile(thora, 'Mira')
    assert 'Level 2' in view.levels.text.text
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'hide')
    assert 'Level 2' not in view.levels.text.text and view.mute.text == 'Hidden'
    thora.eval('WoWStatusMutes.setCharacter')('Mira-TestRealm', 'show')
    assert 'Level 2' in view.levels.text.text and view.mute.text == 'Mute'
