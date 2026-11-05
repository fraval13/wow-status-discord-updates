"""Themes and a size setting for addon windows (#60)."""
from test_addon import STUBS, make_lua

THEMES = STUBS.replace('"SetAllPoints","SetColorTexture",', '"SetAllPoints",') + '''
function methods:SetColorTexture(r, g, b, a) self.colour = {r, g, b, a} end
__faction = "Alliance"
function UnitFactionGroup() return __faction end
'''


def test_default_is_the_solid_brown_achievement_look_at_full_size():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusJournal.show()
        local c = WoWStatusMainFrame.background.colour
        assert(c[1] == .16 and c[2] == .1 and c[4] == 1)
        assert(WoWStatusMainFrame.scale == 1)
        assert(WoWStatusTheme.label() == "Theme: Achievement · size 100%")
    ''')


def test_the_old_default_moves_once_and_chosen_themes_stay():
    lua = make_lua(THEMES + 'WoWStatusDB = {version=1, characters={}, theme={name="night"}}\n')
    lua.execute('''
        assert(WoWStatusTheme.settings().name == "achievement")
        WoWStatusTheme.next()
        assert(WoWStatusTheme.settings().name == "night")
        assert(WoWStatusTheme.settings().name == "night") -- Night chosen again stays.
    ''')
    chosen = make_lua(THEMES + 'WoWStatusDB = {version=1, characters={}, theme={name="journal"}}\n')
    assert chosen.eval('WoWStatusTheme.settings().name') == 'journal'


def test_theme_and_size_apply_at_once_and_are_saved_account_wide():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusJournal.show()
        assert(WoWStatusTheme.next() == "night")
        assert(WoWStatusTheme.next() == "journal")
        local c = WoWStatusMainFrame.background.colour
        assert(c[1] == .2 and c[2] == .14)
        assert(WoWStatusTheme.next() == "faction")
        assert(WoWStatusMainFrame.background.colour[3] == .24)    -- Alliance blue
        __faction = "Horde"; WoWStatusTheme.apply()
        assert(WoWStatusMainFrame.background.colour[1] == .24)    -- Horde red
        assert(WoWStatusTheme.next() == "achievement")
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
        -- Notifications follow the theme by default (popups was not saved as chosen).
        assert(value.name == "achievement" and value.scale == 1.2 and value.popups == true)
    ''')


def test_popups_follow_the_theme_by_default_and_can_opt_out():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusTheme.next(); WoWStatusTheme.next(); WoWStatusTheme.resize(.2) -- Journal, 120%
        WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.bg.colour[1] == .2 and toast.scale == 1.2)
        WoWStatusTheme.setPopups(false)
        assert(toast.bg.colour[1] == .025 and toast.scale == 1)
        -- Unticking is kept.
        assert(WoWStatusTheme.settings().popups == false)
    ''')


def test_options_controls():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        panel.themeNext.OnClick(panel.themeNext)
        assert(panel.theme.text == "Theme: Night · size 100%")
        panel.themeNext.OnClick(panel.themeNext)
        assert(panel.theme.text == "Theme: Journal · size 100%")
        panel.larger.OnClick(panel.larger)
        assert(panel.theme.text == "Theme: Journal · size 110%")
        panel.smaller.OnClick(panel.smaller); panel.smaller.OnClick(panel.smaller)
        assert(WoWStatusDB.theme.scale == .9)
        panel.themePopups:SetChecked(true); panel.themePopups.OnClick(panel.themePopups)
        assert(WoWStatusDB.theme.popups == true)
    ''')


def test_notification_size_is_a_percentage_with_100_as_default():
    lua = make_lua(THEMES)
    lua.execute('''
        assert(WoWStatusTheme.popupSize() == 100)
        WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.scale == 1)
        assert(WoWStatusTheme.setPopupSize(150))
        assert(math.abs(toast.scale - 1.5) < 1e-9 and WoWStatusDB.theme.popup_size == 150)
        -- With the window size applied to popups too, the two multiply.
        WoWStatusTheme.resize(.2); WoWStatusTheme.setPopups(true)
        assert(math.abs(toast.scale - 1.8) < 1e-9)
        WoWStatusTheme.setPopups(false)
        -- Out of range or not a number: refused, the old size stays.
        assert(not WoWStatusTheme.setPopupSize(49) and not WoWStatusTheme.setPopupSize(201))
        assert(not WoWStatusTheme.setPopupSize("big") and WoWStatusTheme.popupSize() == 150)
        assert(WoWStatusTheme.setPopupSize(" 80 ") == false or WoWStatusTheme.popupSize() == 80)
        -- Saved values are kept in range.
        WoWStatusDB.theme.popup_size = 999
        assert(WoWStatusTheme.popupSize() == 200)
    ''')


def test_notification_size_from_the_options_box_and_the_command():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(panel.popupSize:GetText() == "100")
        panel.popupSize:SetText("125"); panel.popupSize.OnEnterPressed(panel.popupSize)
        assert(WoWStatusTheme.popupSize() == 125 and panel.popupSize:GetText() == "125")
        panel.popupSize:SetText("500"); panel.popupSizeApply.OnClick(panel.popupSizeApply)
        assert(WoWStatusTheme.popupSize() == 125 and panel.popupSize:GetText() == "125")
        SlashCmdList.WOWSTATUS("popupsize 90")
        assert(WoWStatusTheme.popupSize() == 90)
        SlashCmdList.WOWSTATUS("popupsize")
        assert(WoWStatusTheme.popupSize() == 90)
    ''')
