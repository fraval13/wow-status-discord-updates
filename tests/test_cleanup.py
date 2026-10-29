"""Armor-only announcements, native options, minimap and one-shot login sync."""
import pytest
from test_addon import STUBS, make_lua
from test_journal import actor, clock, mesh


def item_api(lua, quality, item_class=4, slot='INVTYPE_CHEST'):
    lua.execute(f'''
        function GetItemInfo(link)
            return "Test armor",link,{quality},1,1,"Item","Subtype",1,"{slot}",1,1,{item_class}
        end
    ''')


@pytest.mark.parametrize('quality,item_class,slot,expected', [
    (0,4,'INVTYPE_CHEST',False), (1,4,'INVTYPE_CHEST',False), (2,4,'INVTYPE_CHEST',False),
    (3,4,'INVTYPE_CHEST',True), (4,4,'INVTYPE_CHEST',True), (5,4,'INVTYPE_CHEST',True),
    (4,2,'INVTYPE_WEAPON',False), (4,7,'',False), (4,1,'INVTYPE_BAG',False),
    (3,4,'INVTYPE_FINGER',True), (4,4,'INVTYPE_SHIELD',True), (4,4,'',False),
])
def test_only_selected_rare_epic_legendary_armor_enters_log(quality, item_class, slot, expected):
    lua = make_lua()
    item_api(lua, quality, item_class, slot)
    lua.execute('__slot="|Hitem:123|h[Test armor]|h"; fire("PLAYER_EQUIPMENT_CHANGED",1)')
    assert lua.eval('#character().events') == int(expected)
    assert lua.eval('#WoWStatusJournal.entries()') == int(expected)
    if expected:
        assert lua.eval('WoWStatusJournal.entries()[1].class_id') == 4


def test_uncached_item_waits_for_classification():
    lua = make_lua()
    lua.execute('function GetItemInfo() return nil end')
    lua.execute('__slot="|Hitem:123|h[Test armor]|h"; fire("PLAYER_EQUIPMENT_CHANGED",1)')
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    item_api(lua, 3)
    lua.eval('fire')('GET_ITEM_INFO_RECEIVED', 123, True)
    assert lua.eval('#WoWStatusJournal.entries()') == 1
    lua.eval('fire')('GET_ITEM_INFO_RECEIVED', 123, True)
    assert lua.eval('#WoWStatusJournal.entries()') == 1


def test_rarity_preferences_default_on_and_remove_disabled_rarity_from_log():
    lua = make_lua()
    assert lua.eval('character().settings.in_game.loot') is True
    for rarity in ('rare','epic','legendary'):
        assert lua.eval(f'character().settings.loot_rarities.{rarity}') is True
    item_api(lua, 3)
    lua.execute('__slot="|Hitem:123|h[Test armor]|h"; fire("PLAYER_EQUIPMENT_CHANGED",1)')
    lua.execute('''
        for _, check in ipairs(WoWStatusSetup.checks) do
            if check.group=="loot_rarities" and check.key=="rare" then
                check.widget:SetChecked(false);check.widget.OnClick(check.widget)
            end
        end
    ''')
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    lua.execute('__slot="|Hitem:123|h[Test armor]|h"; fire("PLAYER_EQUIPMENT_CHANGED",1)')
    assert lua.eval('#WoWStatusJournal.entries()') == 0
    item_api(lua, 4)
    lua.execute('__slot="|Hitem:124|h[Test armor]|h"; fire("PLAYER_EQUIPMENT_CHANGED",1)')
    assert lua.eval('#WoWStatusJournal.entries()') == 1


def test_received_loot_requires_armor_metadata_and_respects_rarity():
    lua = actor('Mira')
    channel = lua.eval('function() for id in pairs(character().group_ids) do return WoWStatusGroups.channel(id) end end')()
    receive = lua.eval('WoWStatusPopups.receive')
    assert not receive('WSTATUS6 classic-era loot 1793000000 oldarmor 3 4 INVTYPE_CHEST 123 Robe', 'Eldrin-TestRealm', channel)
    assert not receive('WSTATUS4 classic-era loot 1793000000 old Looted arbitrary junk', 'Eldrin-TestRealm', channel)
    assert not receive('WSTATUS7 classic-era loot 1793000000 weapon 4 2 INVTYPE_WEAPON 1 Sword', 'Eldrin-TestRealm', channel)
    assert receive('WSTATUS7 classic-era loot 1793000000 armor 3 4 INVTYPE_CHEST 123 Robe', 'Eldrin-TestRealm', channel)
    lua.execute('character().settings.loot_rarities.epic=false')
    assert not receive('WSTATUS7 classic-era loot 1793000000 epic 4 4 INVTYPE_CHEST 124 Robe', 'Eldrin-TestRealm', channel)
    assert lua.eval('#WoWStatusJournal.entries()') == 1


def test_old_unknown_junk_is_cleaned_and_known_armor_is_migrated():
    lua = actor('Thora')
    lua.execute('''
        local c=character()
        local name="Thora-TestRealm"
        local function old(sequence,quality,item)
            local nonce=c.epoch.."-"..sequence
            table.insert(c.history.events,{id=c.identity.guid..":"..c.epoch..":"..sequence,
                kind="loot",at=time(),data={item=item,quality=quality}})
            return {id=WoWStatusJournal.eventID(name,nonce),sender=name,owner=c.identity.guid,
                kind="loot",client="classic-era",at=time(),text="Looted armor",quality=quality,groups={}}
        end
        WoWStatusDB.journal.entries={old(10,1,"|Hitem:1|h[Junk]|h"),old(11,4,"|Hitem:2|h[Armor]|h")}
        WoWStatusJournal.prepare(WoWStatusDB)
        WoWStatusJournal.init(WoWStatusDB,c)
    ''')
    assert lua.eval('#WoWStatusJournal.entries()') == 1
    assert lua.eval('WoWStatusJournal.entries()[1].class_id') == 4


def test_log_and_options_hide_discord_introduction_and_manual_sync_controls():
    stubs = STUBS.replace('return setmetatable({font=font}, {__index=methods}) end',
                          'local f=setmetatable({font=font}, {__index=methods});table.insert(__frames,f);return f end')
    lua = make_lua(stubs)
    lua.execute('''
        SlashCmdList.WOWSTATUS("groups")
        SlashCmdList.WOWSTATUS("previews")
        SlashCmdList.WOWSTATUS("journal")
        assert(WoWStatusActivityLog.status==nil)
        assert(WoWStatusSetup.preview==nil)
        assert(WoWStatusDiscordSettings==nil)
        assert(WoWStatusMilestoneSettings==nil)
        WoWStatusHistoryUI.show(character,"payload")
        assert(not WoWStatusHistoryWindow.text:GetText():lower():find("discord",1,true))
        for _,frame in ipairs(__frames) do
            local text=type(frame.text)=="string" and frame.text or ""
            assert(not text:find("Discord",1,true))
            assert(not text:find("Install the addon",1,true))
            assert(text~="Catch up" and text~="Introduce character" and text~="Preview toast")
            assert(text~="Preview character status card")
        end
    ''')


def test_minimap_book_opens_log_and_options_and_can_be_dragged():
    lua = make_lua(STUBS + '''
        function methods:RegisterForClicks() end
        Minimap=CreateFrame("Frame","Minimap",UIParent)
        function Minimap:GetCenter() return 0,0 end
        function Minimap:GetEffectiveScale() return 1 end
        function GetCursorPosition() return 80,0 end
    ''')
    lua.execute('''
        local button=WoWStatusMinimapButton
        assert(button and button:IsShown())
        assert(button.icon.texture:find("INV_Misc_Book_09",1,true))
        button.OnClick(button,"LeftButton")
        assert(WoWStatusActivityLog:IsShown())
        button.OnClick(button,"RightButton")
        assert(WoWStatusSetup:IsShown())
        button.OnDragStart(button);button.OnUpdate(button,.1);button.OnDragStop(button)
        assert(WoWStatusDB.minimap_angle==0)
    ''')


def test_login_hello_contacts_every_peer_once_and_stops_when_finished():
    clients = {name: actor(name) for name in ('Thora','Eldrin','Mira')}
    for i, lua in enumerate(clients.values()):
        clock(lua, 10)
        lua.eval('fire')('PLAYER_LEVEL_UP', i+2)
    mesh(clients, start=11, duration=100)
    for name, lua in clients.items():
        assert lua.eval('#WoWStatusJournal.entries()') == 3
        targets = []
        for i in range(1, lua.eval('#__sent')+1):
            packet = lua.eval(f'__sent[{i}]')
            if packet['prefix']=='WoWStatusLog' and ' H ' in packet['text']:
                targets.append(packet['target'].split('-')[0])
        assert sorted(targets)==sorted(set(clients)-{name})
        lua.execute('__sent={}')
    mesh(clients, start=112, duration=65)
    for lua in clients.values():
        assert lua.eval('#__sent') == 0


def test_new_login_triggers_reverse_catchup_on_already_online_peer():
    online, arriving = actor('Thora'), actor('Mira')
    clock(online, 10)
    clock(arriving, 10)
    online.eval('fire')('PLAYER_LEVEL_UP', 2)
    arriving.eval('fire')('PLAYER_LEVEL_UP', 3)
    online.execute('__peers={"Thora-TestRealm"}')
    clock(online, 150)
    online.eval('WoWStatusJournal.tick')()  # its own login window is over
    clock(arriving, 200)
    arriving.eval('WoWStatusJournal.init')(arriving.eval('WoWStatusDB'), arriving.eval('character')())
    mesh({'Thora': online, 'Mira': arriving}, start=201, duration=55)
    assert online.eval('#WoWStatusJournal.entries()') == 2
    assert arriving.eval('#WoWStatusJournal.entries()') == 2
    for lua in (online, arriving):
        assert lua.eval('WoWStatusLevelPopup') is None


def test_login_sync_transfers_only_requested_armor_rarities():
    own, friend = actor('Thora'), actor('Mira')
    clock(own, 10)
    for quality in (3,4,5):
        item_api(own, quality)
        own.execute(f'__slot="|Hitem:{120+quality}|h[Test armor]|h"; fire("PLAYER_EQUIPMENT_CHANGED",1)')
    friend.execute('character().settings.loot_rarities.rare=false')
    mesh({'Thora':own,'Mira':friend},start=11,duration=45)
    assert friend.eval('#WoWStatusJournal.entries()') == 2
    assert friend.eval('function() for _,e in ipairs(WoWStatusJournal.entries()) do if e.quality<4 or e.class_id~=4 then return false end end return true end')()
    assert friend.eval('WoWStatusLevelPopup') is None


def test_discord_suspension_stops_exports_and_can_restore_saved_opt_ins(tmp_path):
    from wow_status.companion import exports
    enabled = make_lua(discord_feature=True)
    enabled.execute('''
        character().settings.discord_enabled=true
        character().discord_enrolled=true
        local other=WoWStatusHistory.copy(character())
        other.identity.guid="Player-other";other.settings.discord_enabled=false;other.discord_enrolled=false
        WoWStatusDB.characters.other=other
    ''')
    def saved(lua):
        return lua.eval('''function()
            local function literal(value)
                if type(value)=="table" then
                    local parts={}
                    for k,v in pairs(value) do parts[#parts+1]="["..literal(k).."]="..literal(v) end
                    return "{"..table.concat(parts,",").."}"
                elseif type(value)=="string" then return string.format("%q",value)
                else return tostring(value) end
            end
            return "WoWStatusDB = "..literal(WoWStatusDB)
        end''')()
    disabled = make_lua(STUBS + saved(enabled))
    assert disabled.eval('character().settings.discord_enabled') is False
    assert disabled.eval('WoWStatusDB.characters.other.settings.discord_enabled') is False
    path = tmp_path/'WoWStatus.lua'
    path.write_text(saved(disabled))
    assert list(exports(path)) == []
    restored = make_lua(STUBS + saved(disabled), discord_feature=True)
    assert restored.eval('function() for _,c in pairs(WoWStatusDB.characters) do if c.identity.guid=="Player-123-0001" then return c.settings.discord_enabled end end end')() is True
    assert restored.eval('WoWStatusDB.characters.other.settings.discord_enabled') is False


def test_quest_turnins_only_update_totals_and_hundred_milestones():
    lua = make_lua()
    lua.execute('''
        for id=1,99 do fire("QUEST_TURNED_IN",id) end
        assert(character().snapshot.quests_completed==99)
        assert(#WoWStatusJournal.entries()==0)
        fire("QUEST_TURNED_IN",100)
        assert(character().snapshot.quests_completed==100)
        assert(#WoWStatusJournal.entries()==1)
        assert(WoWStatusJournal.entries()[1].kind=="quest")
        assert(WoWStatusJournal.entries()[1].text=="Completed 100 quests!")
        table.insert(WoWStatusDB.journal.entries,{id="old-quest",client="classic-era",sender="Thora-TestRealm",
            owner=character().identity.guid,kind="questprogress",at=time(),text="Completed a quest",groups={}})
        table.insert(WoWStatusDB.journal.entries,{id="legacy-single-quest",client="classic-era",sender="Eldrin-TestRealm",
            kind="quest",at=time(),text="Completed a quest",groups={}})
        WoWStatusJournal.init(WoWStatusDB,character())
        assert(#WoWStatusJournal.entries()==1)
        assert(WoWStatusJournal.entries()[1].kind=="quest")
    ''')


def test_zone_first_visits_persist_and_seed_old_history_without_reload_spam():
    lua = make_lua()
    lua.execute('''
        __zone="Dun Morogh"
        function GetRealZoneText() return __zone end
        fire("ZONE_CHANGED_NEW_AREA")
        assert(#character().events==0)
        __zone="Loch Modan";fire("ZONE_CHANGED_NEW_AREA")
        assert(#character().events==1 and character().events[1].data.zone=="Loch Modan")
        __zone="Dun Morogh";fire("ZONE_CHANGED_NEW_AREA")
        __zone="Loch Modan";fire("ZONE_CHANGED_NEW_AREA")
        assert(#character().events==1)
        WoWStatusProgress.initZones(character(),__zone)
        fire("PLAYER_ENTERING_WORLD");fire("ZONE_CHANGED_NEW_AREA")
        assert(#character().events==1)
        __zone="Wetlands";fire("ZONE_CHANGED_NEW_AREA")
        assert(#character().events==2 and character().events[2].data.zone=="Wetlands")
        -- Migration from an older addon without the visit set.
        character().visited_zones=nil
        WoWStatusProgress.initZones(character(),__zone)
        assert(not WoWStatusProgress.visitZone(character(),"Loch Modan"))
        assert(not WoWStatusProgress.visitZone(character(),"Wetlands"))
    ''')
