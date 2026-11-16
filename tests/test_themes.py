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
        local pick = panel.popupSize
        assert(pick.kind == "Button" and pick.text == "100%")
        -- A dropdown (controller support): every listed size is in range.
        pick.OnClick(pick)
        local menu = WoWStatusUI.menuFrame
        assert(menu.owner == pick and #menu.items == #WoWStatusTheme.POPUP_SIZES)
        for _, item in ipairs(menu.items) do
            assert(item.value >= WoWStatusTheme.POPUP_MIN and item.value <= WoWStatusTheme.POPUP_MAX)
        end
        menu.onPick(125)
        assert(WoWStatusTheme.popupSize() == 125 and pick.text == "125%")
        -- Picking shows a sample at the new size.
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup:IsShown() and math.abs(WoWStatusLevelPopup.scale - 1.25) < 1e-9)
        WoWStatusLocale.set("nn"); assert(WoWStatusTheme.popupSizeLabel(90) == "90 %"); WoWStatusLocale.set("en")
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
-- As in the game: clearing a focused box's focus fires OnEditFocusLost.
function methods:SetFocus() self.focused = true; if self.OnEditFocusGained then self.OnEditFocusGained(self) end end
function methods:ClearFocus()
    if self.focused then self.focused = false; if self.OnEditFocusLost then self.OnEditFocusLost(self) end end
end
''')
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(panel.windowSize:GetText() == "100")
        panel.windowSize:SetFocus(); panel.windowSize:SetText("150"); panel.windowSize.OnEnterPressed(panel.windowSize)
        assert(WoWStatusTheme.windowSize() == 150 and panel.theme.text == "Theme: Achievement · size 150%")
        panel.windowSize:SetFocus(); panel.windowSize:SetText("999"); panel.windowSize.OnEnterPressed(panel.windowSize)
        assert(WoWStatusTheme.windowSize() == 150 and panel.windowSize:GetText() == "150")
        panel.windowSize:SetFocus(); panel.windowSize:SetText("80"); panel.windowSize.OnEscapePressed(panel.windowSize)
        assert(WoWStatusTheme.windowSize() == 150 and panel.windowSize:GetText() == "150")
        -- A controller has no Enter: leaving the box (B, or a click elsewhere) applies it.
        panel.windowSize:SetFocus(); panel.windowSize:SetText("120"); panel.windowSize:ClearFocus()
        assert(WoWStatusTheme.windowSize() == 120 and panel.theme.text == "Theme: Achievement · size 120%")
        -- Typing and then pressing + applies the typed size, then steps from it.
        panel.windowSize:SetFocus(); panel.windowSize:SetText("130")
        panel.larger.OnClick(panel.larger)
        assert(WoWStatusTheme.windowSize() == 140 and panel.windowSize:GetText() == "140")
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
function methods:SetClampRectInsets(...) self.insets = {...} end
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
        assert(WoWStatusTheme.label() == "Theme: Achievement · size 200%")
        assert(WoWStatusTheme.shownNote() == "Shown at 104% to fit the screen")
        -- A larger screen (or smaller UI scale) shows more of the chosen size.
        __screen = {2560, 1440}; WoWStatusTheme.apply()
        assert(main.scale == 2 and WoWStatusTheme.shownNote() == nil)
        -- Sizes that fit are untouched; the default never changes.
        __screen = {1280, 720}; WoWStatusTheme.setWindowSize(100)
        assert(main.scale == 1 and WoWStatusTheme.shownNote() == nil)
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
        -- The window and its 6-unit gold border, in UIParent units, are all inside.
        local function inside(w, h)
            local s = main.scale
            return (main.at[1] - 6) * s >= -1e-6 and (main.at[1] + 786) * s <= w + 1e-6
                and (main.at[2] - 6) * s >= -1e-6 and (main.at[2] + 686) * s <= h + 1e-6
        end
        assert(main.scale == 2 and inside(2560, 1440))
        -- A smaller resolution after that: the window comes back inside.
        __screen = {1280, 720}; main.at = {500, 300}
        WoWStatusTheme.apply()
        assert(inside(1280, 720))
        -- Opening the window checks again; a window already inside stays put.
        main.at = {-200, -200}; main.hooks.OnShow(main)
        assert(math.abs(main.at[1] - 6) < 1e-9 and math.abs(main.at[2] - 6) < 1e-9)
        main.at = {10, 6.2}; main.hooks.OnShow(main)   -- at 104 % only a sliver of height is spare
        assert(main.at[1] == 10 and main.at[2] == 6.2)
        assert(main.insets[1] == -6 and main.insets[2] == 6 and main.insets[3] == 6 and main.insets[4] == -6)
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
        assert(WoWStatusTheme.scale() == 1.04)  -- the scale as shown, not as chosen
    ''')


def test_options_label_follows_the_screen_and_language():
    lua = make_lua(THEMES + SCREEN)
    lua.execute('''
        __screen = {2560, 1440}
        WoWStatusJournal.show()
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        WoWStatusTheme.setWindowSize(200)
        assert(panel.theme.text == "Theme: Achievement · size 200%" and panel.themeNote.text == "")
        __screen = {1280, 720}; WoWStatusTheme.apply()        -- as on DISPLAY_SIZE_CHANGED
        assert(panel.themeNote.text == "Shown at 104% to fit the screen")
        WoWStatusLocale.set("nn"); WoWStatusPreviews.show()
        assert(panel.theme.text == "Tema: Bragd · storleik 200 %")
        assert(panel.themeNote.text == "Vist med 104 % så det får plass på skjermen")
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
        assert(WoWStatusLocale.T("Shown at 104% to fit the screen")
            == "Vist med 104 % så det får plass på skjermen")
        assert(WoWStatusLocale.T("Theme: Night · size 120%") == "Tema: Natt · storleik 120 %")
    ''')


def test_a_size_or_screen_change_closes_the_calendar_and_dropdown():
    lua = make_lua(THEMES + SCREEN)
    lua.execute('''
        __screen = {2560, 1440}
        WoWStatusJournal.show()
        WoWStatusTheme.setWindowSize(200)
        local calendar = CreateFrame("Frame"); WoWStatusUI.calendarFrame = calendar; calendar:Show()
        __screen = {1280, 720}
        for _, frame in ipairs(__events.DISPLAY_SIZE_CHANGED) do
            if frame.OnEvent then frame.OnEvent(frame, "DISPLAY_SIZE_CHANGED") end
        end
        assert(not calendar:IsShown())
        -- A size typed in Options closes them too; a theme change keeps them.
        local menu = CreateFrame("Frame"); WoWStatusUI.menuFrame = menu; menu:Show(); calendar:Show()
        WoWStatusTheme.next()
        assert(menu:IsShown() and calendar:IsShown())
        WoWStatusTheme.setWindowSize(80)
        assert(not menu:IsShown() and not calendar:IsShown())
    ''')


def test_the_dropdown_takes_the_window_size_like_its_button():
    lua = make_lua(THEMES + SCREEN)
    lua.execute('''
        __screen = {2560, 1440}
        WoWStatusJournal.show()
        WoWStatusTheme.setWindowSize(150)
        local owner = CreateFrame("Button", nil, WoWStatusMainFrame); owner.scale = 1.5
        local menu = WoWStatusUI.menu(owner, {{label="One", value=1}}, function() end)
        assert(menu.scale == 1.5)
        local plain = CreateFrame("Button")                      -- in Options: unscaled
        WoWStatusUI.menu(plain, {{label="One", value=1}}, function() end)
        assert(menu.scale == 1)
    ''')


def test_stepping_down_from_a_size_the_screen_caps_changes_the_window_at_once():
    lua = make_lua(THEMES + SCREEN)
    lua.execute('''
        __screen = {1280, 720}
        WoWStatusJournal.show()
        WoWStatusTheme.setWindowSize(200)
        assert(WoWStatusMainFrame.scale == 1.04)
        assert(WoWStatusTheme.resize(-WoWStatusTheme.STEP) == .94 and WoWStatusMainFrame.scale == .94)
    ''')
