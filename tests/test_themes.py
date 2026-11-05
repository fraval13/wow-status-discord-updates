"""Themes and a size setting for addon windows (#60)."""
from test_addon import STUBS, make_lua

THEMES = STUBS.replace('"SetAllPoints","SetColorTexture",', '"SetAllPoints",') + '''
function methods:SetColorTexture(r, g, b, a) self.colour = {r, g, b, a} end
__faction = "Alliance"
function UnitFactionGroup() return __faction end
'''


def test_default_is_the_original_night_look_at_full_size():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusJournal.show()
        local c = WoWStatusMainFrame.background.colour
        assert(c[1] == .025 and c[3] == .065)
        assert(WoWStatusMainFrame.scale == 1)
        assert(WoWStatusTheme.label() == "Theme: Night · size 100%")
    ''')


def test_theme_and_size_apply_at_once_and_are_saved_account_wide():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusJournal.show()
        assert(WoWStatusTheme.next() == "journal")
        local c = WoWStatusMainFrame.background.colour
        assert(c[1] == .2 and c[2] == .14)
        assert(WoWStatusTheme.next() == "faction")
        assert(WoWStatusMainFrame.background.colour[3] == .24)    -- Alliance blue
        __faction = "Horde"; WoWStatusTheme.apply()
        assert(WoWStatusMainFrame.background.colour[1] == .24)    -- Horde red
        assert(WoWStatusTheme.next() == "night")
        for _ = 1, 5 do WoWStatusTheme.resize(WoWStatusTheme.STEP) end
        assert(WoWStatusMainFrame.scale == 1.2)
        for _ = 1, 9 do WoWStatusTheme.resize(-WoWStatusTheme.STEP) end
        assert(WoWStatusMainFrame.scale == .8)
        assert(WoWStatusDB.theme.name == "night" and WoWStatusDB.theme.scale == .8)
    ''')


def test_saved_values_are_validated():
    lua = make_lua(THEMES + 'WoWStatusDB = {version=1, characters={}, theme={name="neon", scale=7, popups="yes"}}\n')
    lua.execute('''
        local value = WoWStatusTheme.settings()
        assert(value.name == "night" and value.scale == 1.2 and value.popups == false)
    ''')


def test_popups_follow_the_theme_only_when_chosen():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusTheme.next(); WoWStatusTheme.resize(.2)
        WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.scale == 1 and toast.bg.colour[1] == .025)
        WoWStatusTheme.setPopups(true)
        assert(toast.bg.colour[1] == .2 and toast.scale == 1.2)
        WoWStatusTheme.setPopups(false)
        assert(toast.bg.colour[1] == .025 and toast.scale == 1)
    ''')


def test_options_controls():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        panel.themeNext.OnClick(panel.themeNext)
        assert(panel.theme.text == "Theme: Journal · size 100%")
        panel.larger.OnClick(panel.larger)
        assert(panel.theme.text == "Theme: Journal · size 110%")
        panel.smaller.OnClick(panel.smaller); panel.smaller.OnClick(panel.smaller)
        assert(WoWStatusDB.theme.scale == .9)
        panel.themePopups:SetChecked(true); panel.themePopups.OnClick(panel.themePopups)
        assert(WoWStatusDB.theme.popups == true)
    ''')
