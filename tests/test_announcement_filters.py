"""A character's announcement choices govern both sharing and reception."""
import pytest
from test_journal import actor, clock, deliver_popup, join_roster, mesh


@pytest.mark.parametrize('kind,category', [
    ('level', 'level'), ('death', 'death'), ('zone', 'zone'), ('quest', 'quest'),
    ('profession', 'profession'), ('dungeon', 'dungeon'), ('raid', 'dungeon'),
    ('mount', 'mount'), ('epicmount', 'mount'), ('reputation', 'reputation'),
    ('unlock', 'unlock'), ('pvp', 'pvp'), ('battleground', 'pvp'),
    ('achievement', 'achievement'), ('recap', 'recap'), ('loot', 'loot'),
])
def test_disabled_category_rejects_live_and_recovered_log_entries(kind, category):
    lua = actor('Mira')
    lua.execute(f'character().settings.in_game.{category}=false')
    item = lua.table_from(dict(sender='Eldrin-TestRealm', nonce='filter-1', kind=kind,
                               text='Completed 100 quests!' if kind == 'quest' else 'Example',
                               at=1793000010, group_id=lua.eval('next(character().group_ids)')[0]))
    assert not lua.eval('WoWStatusJournal.received')(item)
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    lua.execute(f'character().settings.in_game.{category}=true')
    if kind == 'loot':
        for key, value in dict(item_id=42, quality=3, class_id=4, equip_loc='INVTYPE_HEAD').items():
            item[key] = value
    assert lua.eval('WoWStatusJournal.received')(item)
    assert lua.eval('#WoWStatusJournal.entries()') == 1
    lua.execute(f'character().settings.in_game.{category}=false')
    assert not lua.eval('WoWStatusJournal.visible(WoWStatusJournal.entries()[1])')
    lua.eval('WoWStatusJournal.privacyChanged')()
    assert lua.eval('#WoWStatusJournal.entries()') == 0


def test_deaths_off_stops_own_sharing_and_friends_popups_but_other_kinds_work():
    sender, receiver = actor('Thora'), actor('Eldrin')
    for lua in (sender, receiver):
        clock(lua, 10)
    receiver.execute('character().settings.in_game.death=false; fire("PLAYER_DEAD")')
    assert receiver.eval('#__sent') == 0
    sender.eval('fire')('PLAYER_DEAD')
    packet = sender.eval('__sent[1].text')
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('WoWStatusLevelPopup') is None
    assert receiver.eval('#WoWStatusDB.popups.activity') == 0
    # Pausing own sharing and hiding own level detail must not block reception.
    receiver.execute('character().settings.enabled=false; character().settings.fields.level=false')
    clock(sender, 12)
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', sender.eval('__sent[2].text'), 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('WoWStatusLevelPopup:IsShown()')
    assert receiver.eval('WoWStatusLevelPopup.item.level') == 2


def test_turning_category_off_clears_active_and_queued_popups_but_keeps_previews():
    sender, receiver = actor('Thora'), actor('Eldrin')
    for lua in (sender, receiver):
        clock(lua, 10)
    join_roster(receiver, "Thora-TestRealm")
    sender.eval('fire')('PLAYER_DEAD')
    packet = sender.eval('__sent[1].text')
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet, 'WHISPER', 'Thora-TestRealm')
    assert receiver.eval('WoWStatusLevelPopup:IsShown()')
    receiver.execute('''
        character().settings.in_game.death=false
        WoWStatusPopups.privacyChanged(); WoWStatusJournal.privacyChanged()
        assert(not WoWStatusLevelPopup:IsShown())
        character().settings.in_game.level=true
        __combat=true
    ''')
    clock(sender, 12)
    sender.eval('fire')('PLAYER_LEVEL_UP', 2)
    receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', sender.eval('__sent[2].text'), 'WHISPER', 'Thora-TestRealm')
    receiver.execute('''
        character().settings.in_game.level=false
        WoWStatusPopups.privacyChanged(); WoWStatusJournal.privacyChanged()
        __now=__now+20; __combat=false; WoWStatusPopups.tick()
        assert(not WoWStatusLevelPopup:IsShown())
        WoWStatusPopups.preview("level")
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup:IsShown() and WoWStatusLevelPopup.item.preview)
    ''')


def test_disabled_category_cannot_return_through_login_catchup():
    author, relay, late = actor('Thora'), actor('Eldrin'), actor('Mira')
    clock(author, 10)
    clock(relay, 10)
    author.eval('fire')('PLAYER_LEVEL_UP', 2)
    deliver_popup(author, relay)
    assert relay.eval('#WoWStatusJournal.entries()') == 1
    late.execute('character().settings.in_game.level=false')
    late.eval('WoWStatusJournal.sync')()
    mesh({'Eldrin': relay, 'Mira': late})
    assert late.eval('#WoWStatusJournal.entries()') == 0
    assert late.eval('WoWStatusLevelPopup') is None


def test_the_existing_announcement_checkboxes_remain_controller_reachable():
    lua = actor('Mira')
    lua.execute('''
        SlashCmdList.WOWSTATUS("")
        -- Model WoW showing the native Options host around its addon canvas.
        local host=WoWStatusSetup
        while host do if host.Show then host:Show() end host=host.parent end
        local m=getmetatable(WoWStatusSetup).__index
        function m:GetObjectType() return self.kind end
        function m:GetRect() return 0,0,700,700 end
        function m:GetChildren()
            local children={}
            for _,f in ipairs(__frames) do if f.parent==self then children[#children+1]=f end end
            return (unpack or table.unpack)(children)
        end
        local reached={}
        for _,control in ipairs(WoWStatusGamepad.controls(WoWStatusSetup,{WoWStatusSetup})) do reached[control]=true end
        local count=0
        for _,entry in ipairs(WoWStatusSetup.checks) do
            if entry.group=="in_game" then
                assert(reached[entry.widget],entry.key)
                assert(entry.widget:GetObjectType()=="CheckButton" and entry.widget:GetScript("OnClick"))
                count=count+1
            end
        end
        assert(count>=12)
    ''')


def test_disabling_a_category_cancels_unconfirmed_sends_before_retry():
    lua = actor('Mira')
    clock(lua, 10)
    lua.eval('fire')('PLAYER_LEVEL_UP', 2)
    assert lua.eval('#WoWStatusPopups.pendingDeliveries()') > 0
    lua.execute('''
        character().settings.in_game.level=false
        WoWStatusPopups.privacyChanged()
        assert(#WoWStatusPopups.pendingDeliveries()==0)
    ''')
