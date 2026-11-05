"""Character list grouped by player, with portraits (#59)."""
from test_journal import actor, clock

EXTRA = '''
    function UnitRace() return "Dwarf", "Dwarf" end
    function UnitSex() return 3 end
    RAID_CLASS_COLORS = {WARRIOR={colorStr="ffc79c6e"}}
'''


def person(name, player_name):
    lua = actor(name)
    lua.execute(EXTRA)
    # Test runtimes share one random seed; give each account its own player ID.
    pid = (name.encode().hex() * 8)[:16]
    lua.execute(f'WoWStatusDB.player_name = "{player_name}"; WoWStatusDB.roster.id = "{pid}"; WoWStatusRoster.observe(character())')
    return lua


def pump(sender, receiver, start=100):
    """Run the sender's roster ticks and deliver its roster whispers to the receiver."""
    before = sender.eval('#__sent')
    for step in range(20):
        sender.execute(f'__mono = {start + step}')
        sender.eval('WoWStatusRoster.tick')()
    name = sender.eval('WoWStatusAdapter.playerName()') + '-TestRealm'
    delivered = []
    for i in range(before + 1, sender.eval('#__sent') + 1):
        packet = sender.eval(f'__sent[{i}]')
        if packet['prefix'] == 'WoWStatusChr':
            delivered.append(packet['text'])
            receiver.eval('fire')('CHAT_MSG_ADDON', 'WoWStatusChr', packet['text'], 'WHISPER', name)
    return delivered


def pair():
    mira, thora = person('Mira', 'Frank'), person('Thora', 'Ada')
    for lua in (mira, thora):
        lua.execute('__peers={"Thora-TestRealm","Mira-TestRealm"}')
    return mira, thora


def test_characters_are_announced_once_per_member_and_grouped_by_player():
    mira, thora = pair()
    sent = pump(mira, thora)
    assert len(sent) == 1
    assert sent[0].split(' ')[0] == 'C' and sent[0].endswith('Mira-TestRealm Dwarf 3 WARRIOR 1')
    assert pump(mira, thora, start=200) == []  # not repeated to the same member
    groups = thora.eval('WoWStatusRoster.groups()')
    titles = [groups[i].title for i in range(1, len(groups) + 1)]
    assert 'Frank (1 character)' in titles and 'Ada (you) (1 character)' in titles
    thora.eval('SlashCmdList.WOWSTATUS')('characters')
    cards = [thora.eval(f'WoWStatusCharactersPage.lines[{i}]') for i in range(1, thora.eval('WoWStatusCharactersPage.count') + 1)]
    mira_card = next(c for c in cards if c.name.text == '|cffc79c6eMira|r')
    assert mira_card.badge.text.text == '1' and mira_card['class'].text == 'Dwarf Warrior'
    assert mira_card.status.text == 'online'


def test_accounts_with_the_same_player_name_are_merged():
    mira, thora = pair()
    other = person('Bob', 'frank')
    other.execute('__peers={"Thora-TestRealm","Bob-TestRealm"}')
    thora.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    pump(mira, thora)
    pump(other, thora)
    groups = thora.eval('WoWStatusRoster.groups()')
    frank = [groups[i] for i in range(1, len(groups) + 1) if groups[i].title.lower().startswith('frank')]
    assert len(frank) == 1 and len(frank[0].rows) == 2


def test_portraits_prefer_live_units_then_race_faces_then_silhouettes():
    lua = person('Thora', 'Ada')
    lua.execute('''
        __live = nil
        function SetPortraitTexture(texture, unit) texture.texture = "live:" .. unit end
        function UnitName(unit) if unit == "target" and __live then return __live end if unit == "player" then return "Thora" end end
        local t = CreateFrame("Frame"):CreateTexture()
        __live = "Mira"
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm", "Dwarf", 3) == "live" and t.texture == "live:target")
        __live = nil
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm", "Dwarf", 3) == "met")
        assert(t.texture == "Interface\\\\CharacterFrame\\\\TemporaryPortrait-Female-Dwarf")
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm") == "unknown")
        assert(t.texture == "Interface\\\\CharacterFrame\\\\TempPortrait")
        local methods = getmetatable(t).__index
        local original = methods.SetTexture
        function methods:SetTexture(path) if path:find("TempPortrait", 1, true) then return false end self.texture = path end
        assert(WoWStatusRoster.portrait(t, "Mira-TestRealm") == "unknown")
        assert(t.texture == "Interface\\\\Icons\\\\INV_Misc_QuestionMark")
        methods.SetTexture = original
    ''')


def test_bad_or_unauthorised_announcements_are_rejected():
    mira, thora = pair()
    pid = mira.eval('WoWStatusDB.roster.id')
    group = thora.eval('(function() for id in pairs(character().group_ids) do return id end end)()')
    receive = thora.eval('WoWStatusRoster.receive')
    good = f'C {group} {pid} Frank Mira-TestRealm Dwarf 3 WARRIOR 12'
    assert receive(good, 'Mira-TestRealm', 'WHISPER') is True
    for bad in (good.replace('WARRIOR', 'PIRATE'), good.replace(' 12', ' 999'), good.replace(' 3 ', ' 1 '),
                good.replace('Dwarf', 'Dw4rf'), good.replace('Mira-TestRealm', 'Mira|cff'), good.replace(pid, 'xyz'),
                good.replace(f'C {group}', 'C othergroup'), good + ' extra'):
        assert receive(bad, 'Mira-TestRealm', 'WHISPER') is False, bad
    assert receive(good, 'Stranger-TestRealm', 'WHISPER') is False
    assert receive(good, 'Mira-TestRealm', 'CHANNEL') is False


def test_hiding_a_character_and_turning_sharing_off():
    mira, thora = pair()
    pump(mira, thora)
    assert thora.eval('next(WoWStatusDB.roster.players)') is not None
    mira.execute('WoWStatusRoster.setHidden(character(), true)')
    assert pump(mira, thora, start=300) == []
    mira.execute('WoWStatusRoster.setHidden(character(), false); WoWStatusRoster.setSharing(false)')
    sent = pump(mira, thora, start=400)
    assert len(sent) == 1 and sent[0].startswith('X ')
    assert thora.eval('next(WoWStatusDB.roster.players)') is None
    mira.execute('WoWStatusRoster.setSharing(true)')
    assert len(pump(mira, thora, start=500)) == 1


def test_log_senders_without_a_list_show_as_never_met():
    lua = person('Thora', 'Ada')
    clock(lua, 10)
    lua.execute('''
        WoWStatusJournal.received({sender="Eldrin-TestRealm", nonce="a1", kind="level", level=8})
        local found
        for _, group in ipairs(WoWStatusRoster.groups()) do
            if group.title:find("Not announced", 1, true) then found = group.rows[1] end
        end
        assert(found and found.name == "Eldrin-TestRealm" and found.level == nil)
        assert(found.latest == "Reached level 8!")
    ''')


def test_full_names_with_spaces_are_announced_and_replace_first_name_entries():
    # WoW Forever: an older client announced "Mira"; the full name is "Mira Stone".
    mira, thora = pair()
    pump(mira, thora)
    mira.execute('character().chat_name = "Mira Stone"')
    mira.execute('WoWStatusRoster.changed()')
    sent = pump(mira, thora, start=300)
    assert sent and 'Mira_Stone-TestRealm' in sent[0]
    names = [r.name for g in thora.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    assert 'Mira Stone-TestRealm' in names and 'Mira-TestRealm' not in names


def test_a_first_name_entry_shows_as_its_one_known_full_name():
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('WoWStatusPopups.notePeer(next(character().group_ids), "Mira Stone-TestRealm")')
    names = [r.name for g in thora.eval('WoWStatusRoster.groups()').values() for r in g.rows.values()]
    assert 'Mira Stone-TestRealm' in names and 'Mira-TestRealm' not in names
    assert names.count('Mira Stone-TestRealm') == 1


def test_members_without_a_list_are_identified_from_their_roster_guid():
    # Live check: Forever's channel roster gives GUIDs, and GetPlayerInfoByGUID knows them.
    thora = person('Thora', 'Ada')
    thora.execute('''
        local group=next(character().group_ids)
        __peers={"x","y"}
        C_ChatInfo.GetChannelRosterInfo=function(_, i)
            local list={{"Thora",UnitGUID("player")},{"Bob","Player-1-0000BOB"}}
            local item=list[i]
            if item then return item[1],false,false,item[2] end
        end
        function GetPlayerInfoByGUID(guid)
            if guid=="Player-1-0000BOB" then return "Hunter","HUNTER","Night Elf","NightElf",2,"Bob","" end
        end
        WoWStatusPopups.peers(group)
        for _=1,3 do WoWStatusPopups.tick() end
        WoWStatusJournal.received({sender="Bob-TestRealm",nonce="1-1-aaaa",kind="level",level=5,at=time(),group_id=group})
        local function bob()
            for _,g in ipairs(WoWStatusRoster.groups()) do for _,r in ipairs(g.rows) do
                if r.name=="Bob-TestRealm" then return r end
            end end
        end
        local row=bob()
        assert(row.class=="HUNTER" and row.race=="NightElf" and row.sex==2 and row.level==nil)
        -- Still known after the GUID lookup stops answering (logged off, cache cleared).
        function GetPlayerInfoByGUID() return nil end
        row=bob()
        assert(row.class=="HUNTER" and row.race=="NightElf")
    ''')


def test_friends_show_as_character_and_player_name():
    mira, thora = pair()  # Mira's player chose the name "Frank".
    pump(mira, thora)
    thora.execute('''
        assert(WoWStatusRoster.displayName("Mira-TestRealm") == "Mira (Frank)")
        assert(WoWStatusRoster.displayName("Bob-TestRealm") == "Bob")
        local group=next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-aaaa",kind="death",text="Died",at=time(),group_id=group})
        WoWStatusJournal.show()
        assert(WoWStatusActivityLog.rows[1].message.text:find("Mira (Frank) — ",1,true))
        assert(WoWStatusStatusLine.latest():find("Mira (Frank)",1,true))
        WoWStatusPopups.notice({sender="Mira-TestRealm",kind="first",text="First in the group to die!"})
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup.message:GetText():find("Mira (Frank) — ",1,true))
        -- A player name that only repeats the first name adds nothing.
        for _, p in pairs(WoWStatusDB.roster.players) do p.name = "mira" end
        assert(WoWStatusRoster.displayName("Mira-TestRealm") == "Mira")
    ''')


def test_each_player_heading_notes_their_addon_version():
    mira, thora = pair()
    mira.execute('WoWStatusPopups.runtimeVersion = "1.11.0"')
    sent = pump(mira, thora)
    assert any(line.startswith('V ') and line.endswith(' 1.11.0') for line in sent)
    groups = {g.title: g.note for g in thora.eval('WoWStatusRoster.groups()').values()}
    assert groups['Frank (1 character)'] == 'v1.11.0'
    # A list from a version that does not send one, and members without a list.
    thora.execute('''
        for _, p in pairs(WoWStatusDB.roster.players) do p.version = nil end
        local group=next(character().group_ids)
        WoWStatusJournal.received({sender="Bob-TestRealm",nonce="1-1-aaaa",kind="level",level=5,at=time(),group_id=group})
    ''')
    groups = {g.title: g.note for g in thora.eval('WoWStatusRoster.groups()').values()}
    assert groups['Frank (1 character)'] == 'older version'
    assert groups['Not announced (1 character)'] == 'older version or list sharing off'
    thora.eval('SlashCmdList.WOWSTATUS')('characters')
    assert 'older version' in thora.eval('WoWStatusCharactersPage.headers[1].text.text') or \
        'older version' in thora.eval('WoWStatusCharactersPage.headers[2].text.text')


def test_cards_end_with_level_and_total_deaths():
    mira, thora = pair()
    pump(mira, thora)
    thora.execute('''
        local group=next(character().group_ids)
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-1-aaaa",kind="death",text="Total deaths: 2",at=time()-5,group_id=group})
        WoWStatusJournal.received({sender="Mira-TestRealm",nonce="1-2-bbbb",kind="death",text="Total deaths: 3",at=time(),group_id=group})
        fire("PLAYER_DEAD")
        SlashCmdList.WOWSTATUS("characters")
        local cards={}
        for i=1,WoWStatusCharactersPage.count do
            local c=WoWStatusCharactersPage.lines[i]; cards[c.character.name]=c.latest.text
        end
        assert(cards["Mira-TestRealm"]=="Level 1 · 3 deaths", cards["Mira-TestRealm"])
        assert(cards["Thora-TestRealm"]=="Level 1 · 1 death", cards["Thora-TestRealm"])
    ''')


def test_silent_members_seen_in_the_group_are_listed_and_remembered():
    # Live report: members on old versions with nothing in the log were missing.
    thora = person('Thora', 'Ada')
    thora.execute('''
        __peers={"Thora-TestRealm","Silent-TestRealm"}
        local function silent()
            for _,g in ipairs(WoWStatusRoster.groups()) do for _,r in ipairs(g.rows) do
                if r.name=="Silent-TestRealm" then return g.title, r end
            end end
        end
        local title,row=silent()
        assert(title=="Not announced (1 character)" and row.status=="online")
        -- After logging off they stay listed, as last seen.
        __peers={"Thora-TestRealm"}
        for id in pairs(character().group_ids) do WoWStatusPopups.peers(id) end
        for _=1,3 do WoWStatusPopups.tick() end
        title,row=silent()
        assert(row and row.status:find("last seen",1,true), row and row.status)
    ''')


def test_a_new_player_name_reaches_online_members_at_once():
    mira, thora = pair()
    pump(mira, thora)
    mira.eval('WoWStatusGroups.update')('dawnwatch', 'Frankie')
    pump(mira, thora, start=300)
    titles = [g.title for g in thora.eval('WoWStatusRoster.groups()').values()]
    assert 'Frankie (1 character)' in titles and 'Frank (1 character)' not in titles
