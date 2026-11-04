"""'Share it' whisper with the addon download link (#67)."""
from test_addon import STUBS, make_lua

SHARE = STUBS + '''
__now = 1793000000
function time() return __now end
__menus = {}
Menu = {ModifyMenu=function(tag, fn) __menus[tag] = fn end}
function whispers()
    local found = {}
    for _, item in ipairs(__sent) do if item.kind == "WHISPER" and not item.prefix then table.insert(found, item) end end
    return found
end
function openMenu(tag, context)
    local root = {buttons={}}
    function root:CreateDivider() end
    function root:CreateButton(text, fn) table.insert(self.buttons, {text=text, fn=fn}) end
    __menus[tag](nil, root, context)
    return root.buttons
end
'''


def test_share_command_whispers_the_download_link():
    lua = make_lua(SHARE)
    lua.execute('''
        SlashCmdList.WOWSTATUS("share Brann")
        local list = whispers()
        assert(#list == 1 and list[1].target == "Brann")
        assert(list[1].text:find("https://wow.frankvalde.com", 1, true))
    ''')


def test_share_is_limited_to_once_per_person_per_hour():
    lua = make_lua(SHARE)
    lua.execute('''
        SlashCmdList.WOWSTATUS("share Brann")
        SlashCmdList.WOWSTATUS("share brann")
        SlashCmdList.WOWSTATUS("share Moira")
        assert(#whispers() == 2)
        __now = __now + 3599
        SlashCmdList.WOWSTATUS("share Brann")
        assert(#whispers() == 2)
        __now = __now + 1
        SlashCmdList.WOWSTATUS("share Brann")
        assert(#whispers() == 3)
        -- The limit is account-wide and survives a reload.
        assert(WoWStatusDB.share.sent["brann"] == __now)
    ''')


def test_invalid_names_send_nothing():
    lua = make_lua(SHARE)
    lua.execute('''
        for _, name in ipairs({"", "two words", "Bad|cff", "A-B-C", "x" .. string.rep("y", 70), "<script>"}) do
            assert(WoWStatusShare.send(name) == false)
        end
        assert(#whispers() == 0)
        assert(WoWStatusShare.send("Brann-Ironforge") == true)
        assert(whispers()[1].target == "Brann-Ironforge")
    ''')


def test_nothing_is_sent_automatically_or_while_chat_is_restricted():
    lua = make_lua(SHARE)
    lua.execute('''
        fire("PLAYER_LEVEL_UP", 10)
        assert(#whispers() == 0)
        __restricted = true
        assert(WoWStatusShare.send("Brann") == false)
        __restricted = false
        assert(WoWStatusShare.send("Brann") == true)
    ''')


def test_right_click_menu_offers_share_for_other_players_only():
    lua = make_lua(SHARE)
    lua.execute('''
        assert(__menus.MENU_UNIT_PLAYER and __menus.MENU_UNIT_FRIEND)
        local buttons = openMenu("MENU_UNIT_FRIEND", {name="Brann", server="Ironforge"})
        assert(#buttons == 1 and buttons[1].text == "Share WoW Status")
        buttons[1].fn()
        assert(whispers()[1].target == "Brann-Ironforge")
        assert(#openMenu("MENU_UNIT_PLAYER", {name="Thora", isSelf=true}) == 0)
        assert(#openMenu("MENU_UNIT_PLAYER", {}) == 0)
    ''')


def test_clients_without_the_menu_api_still_have_the_command():
    lua = make_lua(STUBS)
    lua.execute('SlashCmdList.WOWSTATUS("share Brann")')
    assert lua.eval('#__sent') >= 1
