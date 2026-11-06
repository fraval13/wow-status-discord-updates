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
