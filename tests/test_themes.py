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
        for _ = 1, 15 do WoWStatusTheme.resize(WoWStatusTheme.STEP) end
        assert(WoWStatusMainFrame.scale == 2)
        for _ = 1, 20 do WoWStatusTheme.resize(-WoWStatusTheme.STEP) end
        assert(WoWStatusMainFrame.scale == .7)
        assert(WoWStatusDB.theme.name == "night" and WoWStatusDB.theme.scale == .7)
    ''')


def test_saved_values_are_validated():
    lua = make_lua(THEMES + 'WoWStatusDB = {version=1, characters={}, theme={name="neon", scale=7, popups="yes"}}\n')
    lua.execute('''
        local value = WoWStatusTheme.settings()
        -- Notifications follow the theme by default (popups was not saved as chosen).
        assert(value.name == "achievement" and value.scale == 2 and value.popups == true)
        WoWStatusDB.theme.scale = .1; assert(WoWStatusTheme.settings().scale == .7)
        WoWStatusDB.theme.scale = 0 / 0; assert(WoWStatusTheme.settings().scale == 1)
        WoWStatusDB.theme.scale = "big"; assert(WoWStatusTheme.settings().scale == 1)
        WoWStatusDB.theme.scale = 1.234; assert(WoWStatusTheme.settings().scale == 1.23)
    ''')


def test_sizes_saved_before_the_wider_range_load_unchanged():
    for saved in ('.8', '.9', '1', '1.1', '1.2'):
        lua = make_lua(THEMES + f'WoWStatusDB = {{version=1, characters={{}}, theme={{scale={saved}}}}}\n')
        assert lua.eval('WoWStatusTheme.settings().scale') == float(saved)
        assert lua.eval('WoWStatusTheme.windowSize()') == round(float(saved) * 100)


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
        assert(panel.theme.text == "Theme: Journal · size 110%" and panel.windowSize:GetText() == "110")
        panel.smaller.OnClick(panel.smaller); panel.smaller.OnClick(panel.smaller)
        assert(WoWStatusDB.theme.scale == .9 and panel.windowSize:GetText() == "90")
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


def test_window_size_is_a_whole_percentage_from_70_to_200():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusJournal.show()
        assert(WoWStatusTheme.windowSize() == 100)
        assert(WoWStatusTheme.setWindowSize(135))
        assert(WoWStatusMainFrame.scale == 1.35 and WoWStatusDB.theme.scale == 1.35)
        assert(WoWStatusTheme.resize(WoWStatusTheme.STEP) == 1.45)
        assert(WoWStatusTheme.setWindowSize("200") and WoWStatusMainFrame.scale == 2)
        assert(WoWStatusTheme.setWindowSize(70) and WoWStatusMainFrame.scale == .7)
        -- Out of range or not a number: refused, the old size stays.
        assert(not WoWStatusTheme.setWindowSize(69) and not WoWStatusTheme.setWindowSize(201))
        assert(not WoWStatusTheme.setWindowSize("huge") and not WoWStatusTheme.setWindowSize(nil))
        assert(WoWStatusTheme.windowSize() == 70)
        -- The steps stop at both ends.
        WoWStatusTheme.resize(-WoWStatusTheme.STEP); assert(WoWStatusTheme.windowSize() == 70)
        WoWStatusTheme.setWindowSize(195); WoWStatusTheme.resize(WoWStatusTheme.STEP)
        assert(WoWStatusTheme.windowSize() == 200)
    ''')


def test_window_size_box_in_options_is_reachable_with_a_controller():
    lua = make_lua(THEMES + '''
function methods:GetObjectType() return self.kind end
function methods:GetScript(name) return self[name] end
''')
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(panel.windowSize:GetText() == "100")
        panel.windowSize:SetText("150"); panel.windowSize.OnEnterPressed(panel.windowSize)
        assert(WoWStatusTheme.windowSize() == 150 and panel.theme.text == "Theme: Achievement · size 150%")
        panel.windowSize:SetText("999"); panel.windowSize.OnEnterPressed(panel.windowSize)
        assert(WoWStatusTheme.windowSize() == 150 and panel.windowSize:GetText() == "150")
        panel.windowSize:SetText("80"); panel.windowSize.OnEscapePressed(panel.windowSize)
        assert(WoWStatusTheme.windowSize() == 150 and panel.windowSize:GetText() == "150")
        -- Gamepad.lua reaches a text box and a button with OnClick.
        assert(panel.windowSize.kind == "EditBox" and WoWStatusGamepad.interactive(panel.windowSize))
        assert(WoWStatusGamepad.interactive(panel.smaller) and WoWStatusGamepad.interactive(panel.larger))
    ''')


SCREEN = '''
__screen = {1920 / 1.5, 1080 / 1.5} -- 1080p at the UI scale that makes UIParent 1280x720
function UIParent:GetWidth() return __screen[1] end
function UIParent:GetHeight() return __screen[2] end
function UIParent:GetEffectiveScale() return 1 end
function methods:GetHeight() return self.height or 400 end
function methods:GetScale() return self.scale or 1 end
function methods:GetEffectiveScale() return self.scale or 1 end
-- A frame placed by its bottom-left corner, in its own (scaled) units.
function methods:SetPoint(point, relative, relativePoint, x, y)
    if point == "BOTTOMLEFT" then self.at = {x, y} end
end
function methods:GetLeft() return self.at and self.at[1] end
function methods:GetBottom() return self.at and self.at[2] end
function methods:GetRight() return self.at and self.at[1] + self:GetWidth() end
function methods:GetTop() return self.at and self.at[2] + self:GetHeight() end
function methods:SetClampedToScreen(value) self.clamped = value end
function methods:HookScript(name, fn) self.hooks = self.hooks or {}; self.hooks[name] = fn end
'''


def test_a_size_the_screen_cannot_hold_is_shown_smaller_and_said_so():
    lua = make_lua(THEMES + SCREEN)
    lua.execute('''
        WoWStatusJournal.show()
        local main = WoWStatusMainFrame
        assert(main.clamped == true and main.hooks.OnShow)
        -- 780x680 plus the border fits 720 units of height only up to 1.04.
        WoWStatusTheme.setWindowSize(200)
        assert(WoWStatusDB.theme.scale == 2)                 -- the choice is kept
        assert(main.scale == 1.04)                           -- what fits is shown
        assert(WoWStatusTheme.label() == "Theme: Achievement · size 200% (104% fits the screen)")
        -- A larger screen (or smaller UI scale) shows more of the chosen size.
        __screen = {2560, 1440}; WoWStatusTheme.apply()
        assert(main.scale == 2 and WoWStatusTheme.label() == "Theme: Achievement · size 200%")
        -- Sizes that fit are untouched; the default never changes.
        __screen = {1280, 720}; WoWStatusTheme.setWindowSize(100)
        assert(main.scale == 1 and WoWStatusTheme.label() == "Theme: Achievement · size 100%")
        -- A client that reports no screen size limits nothing.
        __screen = {0, 0}; WoWStatusTheme.setWindowSize(180)
        assert(main.scale == 1.8)
    ''')


def test_a_window_pushed_off_screen_moves_back_with_the_title_bar_visible():
    lua = make_lua(THEMES + SCREEN)
    lua.execute('''
        __screen = {2560, 1440}
        WoWStatusJournal.show()
        local main = WoWStatusMainFrame
        -- Dragged to the top right at 100 %, then made twice as large.
        main.at = {2560 - 790, 1440 - 690}
        WoWStatusTheme.setWindowSize(200)
        local left, bottom = main.at[1] * 2, main.at[2] * 2  -- in UIParent units
        assert(left >= 0 and left + 780 * 2 <= 2560 and bottom >= 0 and bottom + 680 * 2 <= 1440)
        -- A smaller resolution after that: the window comes back inside.
        __screen = {1280, 720}; main.at = {500, 300}
        WoWStatusTheme.apply()
        local s = main.scale
        assert(main.at[1] * s >= 0 and (main.at[1] + 780) * s <= 1280 + 1e-6)
        assert(main.at[2] * s >= 0 and (main.at[2] + 680) * s <= 720 + 1e-6)
        -- Opening the window checks again; a window already inside stays put.
        main.at = {-200, -200}; main.hooks.OnShow(main)
        assert(main.at[1] == 0 and main.at[2] == 0)
        main.at = {10, 10}; main.hooks.OnShow(main)
        assert(main.at[1] == 10 and main.at[2] == 10)
    ''')


def test_resolution_and_ui_scale_changes_size_the_window_again():
    lua = make_lua(THEMES + SCREEN)
    lua.execute('''
        __screen = {2560, 1440}
        WoWStatusJournal.show()
        WoWStatusTheme.setWindowSize(200)
        assert(WoWStatusMainFrame.scale == 2)
        __screen = {1280, 720}
        for _, event in ipairs({"DISPLAY_SIZE_CHANGED", "UI_SCALE_CHANGED"}) do
            local handled = false
            for _, frame in ipairs(__events[event] or {}) do
                if frame.OnEvent then frame.OnEvent(frame, event); handled = true end
            end
            assert(handled, event)
        end
        assert(WoWStatusMainFrame.scale == 1.04)
    ''')


def test_notifications_follow_the_window_size_only_within_the_old_range():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusPopups.preview("zone"); WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        WoWStatusTheme.setWindowSize(200)
        assert(math.abs(toast.scale - 1.2) < 1e-9)       -- not doubled with the window
        WoWStatusTheme.setPopupSize(200)
        assert(math.abs(toast.scale - 2.4) < 1e-9)       -- as large as before this change
        WoWStatusTheme.setWindowSize(70); WoWStatusTheme.setPopupSize(100)
        assert(math.abs(toast.scale - .8) < 1e-9)
        WoWStatusTheme.setWindowSize(110)
        assert(math.abs(toast.scale - 1.1) < 1e-9)       -- inside the old range it follows exactly
    ''')


def test_the_screen_note_is_translated():
    lua = make_lua(THEMES)
    lua.execute('''
        WoWStatusLocale.set("nn")
        assert(WoWStatusLocale.T("Theme: Night · size 200% (104% fits the screen)")
            == "Tema: Natt · storleik 200 % (104 % får plass på skjermen)")
        assert(WoWStatusLocale.T("Theme: Night · size 120%") == "Tema: Natt · storleik 120 %")
    ''')
