"""Armor updates: the item's own icon, quality-coloured name and game tooltip."""
from test_journal import actor

TOOLTIP = '''
    __tooltip = {}
    GameTooltip = {
        SetOwner=function(self, owner, anchor) __tooltip.owner, __tooltip.anchor = owner, anchor end,
        SetItemByID=function(self, id) __tooltip.item = id end,
        AddLine=function(self, text) __tooltip.lines = (__tooltip.lines or "") .. text .. "\\n" end,
        SetText=function(self, text) __tooltip.text = text end,
        Show=function() __tooltip.shown = true end, Hide=function() __tooltip.shown = false end,
        GetOwner=function() return __tooltip.owner end,
    }
    C_Item = C_Item or {}
    C_Item.GetItemIconByID = function(id) if id == 16923 then return 132633 end end
'''


def received_robe():
    lua = actor('Mira')
    lua.execute(TOOLTIP)
    channel = lua.eval('function() for id in pairs(character().group_ids) do return WoWStatusGroups.channel(id) end end')()
    assert lua.eval('WoWStatusPopups.receive')(
        'WSTATUS7 classic-era loot 1793000000 robe 4 4 INVTYPE_CHEST 16923 Robe of Transcendence', 'Eldrin-TestRealm', channel)
    lua.eval('WoWStatusPopups.tick')()
    return lua


def test_armor_notification_shows_the_item_icon_coloured_name_and_tooltip():
    lua = received_robe()
    lua.execute('''
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.item.item_id == 16923)
        assert(toast.icon.texture == 132633)
        assert(toast.message:GetText():find("|cffa335eeRobe of Transcendence|r", 1, true))
        toast.OnEnter(toast)
        assert(__tooltip.shown and __tooltip.item == 16923 and __tooltip.owner == toast)
        toast.OnLeave(toast)
        assert(not __tooltip.shown)
    ''')


def test_armor_log_card_shows_the_item_tooltip_with_who_equipped_it():
    lua = received_robe()
    lua.execute('''
        WoWStatusJournal.show()
        WoWStatusActivityLog.day = nil
        WoWStatusJournal.show()
        local row = WoWStatusActivityLog.rows[1]
        assert(row.entry.kind == "loot" and row.icon.texture == 132633)
        assert(row.message.text:find("|cffa335eeRobe of Transcendence|r", 1, true))
        row.OnEnter(row)
        assert(__tooltip.item == 16923 and __tooltip.lines:find("Equipped by Eldrin", 1, true))
    ''')


def test_other_updates_keep_their_usual_icon_and_tooltip():
    lua = actor('Mira')
    lua.execute(TOOLTIP)
    lua.execute('''
        local item = {kind="death", text="Died", item_id=16923}
        assert(WoWStatusPresentation.itemIcon(item) == nil)
        assert(not WoWStatusPresentation.itemTooltip(UIParent, item))
        assert(WoWStatusPresentation.colourItem({kind="loot", text="Equipped X", item_id=1}, "Equipped X") == "Equipped X")
    ''')


def heading(lua, quality, slot):
    return lua.eval(f'select(5, WoWStatusPresentation.theme({{kind="loot", quality={quality}, equip_loc="{slot}"}}))')


def test_armor_headings_name_the_piece():
    lua = actor('Mira')
    assert heading(lua, 3, 'INVTYPE_FINGER') == 'RARE RING EQUIPPED!'
    assert heading(lua, 4, 'INVTYPE_TRINKET') == 'EPIC TRINKET EQUIPPED!'
    assert heading(lua, 5, 'INVTYPE_CHEST') == 'LEGENDARY CHESTPIECE EQUIPPED!'
    assert heading(lua, 3, 'INVTYPE_SOMETHING_NEW') == 'RARE ARMOR EQUIPPED!'


def test_nynorsk_armor_headings_agree_with_the_piece():
    lua = actor('Mira')
    lua.execute('WoWStatusLocale.set("nn")')
    t = lua.eval('WoWStatusLocale.T')
    assert t('RARE RING EQUIPPED!') == 'SJELDAN RING PÅ!'           # masculine
    assert t('RARE SHIELD EQUIPPED!') == 'SJELDANT SKJOLD PÅ!'       # neuter
    assert t('RARE GLOVES EQUIPPED!') == 'SJELDNE HANSKAR PÅ!'       # plural
    assert t('EPIC CHESTPIECE EQUIPPED!') == 'EPISK BRYSTPANSAR PÅ!'
    assert t('LEGENDARY BOOTS EQUIPPED!') == 'LEGENDARISKE STØVLAR PÅ!'
    assert t('RARE ARMOR EQUIPPED!') == 'SJELDAN RUSTNING PÅ!'


def test_every_armor_slot_has_a_name_in_both_languages():
    import re
    from pathlib import Path
    root = Path(__file__).parents[1] / 'addon/shared'
    slots = re.findall(r'(INVTYPE_\w+)=true', (root / 'Loot.lua').read_text(encoding='utf-8'))
    assert len(slots) >= 18
    lua = actor('Mira')
    lua.execute('WoWStatusLocale.set("nn")')
    for slot in slots:
        for quality in (3, 4, 5):
            english = heading(lua, quality, slot)
            assert 'ARMOR' not in english, slot
            assert lua.eval(f'WoWStatusLocale.T("{english}")').endswith(' PÅ!'), english


FULL = 'item:16923:2564:0:0:0:0:0:0:60'


def test_the_full_item_reaches_friends_and_its_tooltip():
    from test_roster import pair, pump
    mira, thora = pair()
    pump(mira, thora)
    mira.execute(f'''
        WoWStatusRoster.itemDetails({{nonce="1-2-ab", group_ids=character().group_ids,
            data={{item="|cffa335ee|H{FULL}|h[Robe of Transcendence]|h|r"}}}})
    ''')
    sent = pump(mira, thora, start=300)
    assert any(line.startswith('I ') and FULL in line for line in sent)
    thora.execute(TOOLTIP + f'''
        GameTooltip.SetHyperlink = function(self, link) __tooltip.link = link end
        local group = next(character().group_ids)
        WoWStatusJournal.received({{sender="Mira-TestRealm", nonce="1-2-ab", kind="loot", text="Equipped Robe of Transcendence",
            quality=4, class_id=4, equip_loc="INVTYPE_CHEST", item_id=16923, at=time(), group_id=group}})
        local id = WoWStatusJournal.eventID("Mira-TestRealm", "1-2-ab")
        assert(WoWStatusJournal.details(WoWStatusJournal.entry(id)).item == "{FULL}")
        assert(WoWStatusPresentation.itemTooltip(UIParent, WoWStatusJournal.entry(id)))
        assert(__tooltip.link == "{FULL}" and __tooltip.item == nil)
    ''')


def test_bad_item_strings_are_refused():
    lua = actor('Mira')
    assert lua.eval('WoWStatusJournal.itemString')('|Hitem:1:2|h[x]|h') == 'item:1:2'
    assert lua.eval('WoWStatusJournal.itemString')('item:1;DROP') is None
    assert lua.eval('WoWStatusJournal.itemString')('item:' + '1:' * 80) is None
