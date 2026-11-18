"""Labs: experiments are off for everyone until a player switches one on (#222)."""
from test_addon import make_lua


def labs(lua):
    """Register two experiments and open the page, as a feature module would."""
    lua.execute('''
        WoWStatusFeatures.forgetAll() -- the experiments the addon itself registers
        assert(WoWStatusFeatures.register("combo","Hype combo banner","A banner when friends hit milestones together"))
        assert(WoWStatusFeatures.register("bingo","Weekly group bingo card"))
        SlashCmdList.WOWSTATUS("labs")
    ''')
    return lua.eval('WoWStatusLabsPage')


def test_nothing_is_enabled_and_nothing_is_saved_until_a_player_asks():
    lua = make_lua()
    page = labs(lua)
    assert lua.eval('WoWStatusFeatures.enabled("combo")') is False
    assert lua.eval('WoWStatusFeatures.enabled("bingo")') is False
    assert lua.eval('WoWStatusFeatures.anyEnabled()') is False
    # An account that never visited Labs says nothing about experiments.
    assert lua.eval('(function() local n=0; for _ in pairs(WoWStatusDB.labs) do n=n+1 end; return n end)()') == 0
    assert page.rows[1].checked in (None, False)
    assert page.rows[2].checked in (None, False)
    assert page.allOff.enabled is False
    assert page.empty.visible is False


def test_a_toggle_persists_for_the_account_and_turn_all_off_clears_it():
    lua = make_lua()
    labs(lua)
    lua.execute('''
        local row=WoWStatusLabsPage.rows[1]
        row:SetChecked(true);row.OnClick(row)
    ''')
    assert lua.eval('WoWStatusFeatures.enabled("combo")') is True
    assert lua.eval('WoWStatusFeatures.enabled("bingo")') is False
    assert lua.eval('WoWStatusDB.labs.combo') is True
    assert lua.eval('WoWStatusLabsPage.allOff.enabled') is True
    # Reopening reads the saved value back, as a later login would.
    lua.execute('WoWStatusLabs.render()')
    assert lua.eval('WoWStatusLabsPage.rows[1]:GetChecked()') is True
    lua.execute('WoWStatusLabsPage.allOff.OnClick()')
    assert lua.eval('WoWStatusFeatures.enabled("combo")') is False
    assert lua.eval('WoWStatusDB.labs.combo') is None
    assert lua.eval('WoWStatusLabsPage.rows[1]:GetChecked()') is False
    assert lua.eval('WoWStatusLabsPage.allOff.enabled') is False


def test_a_malformed_saved_value_falls_back_to_off():
    lua = make_lua()
    labs(lua)
    for value in ('"yes"', '1', 'false', '{}'):
        lua.execute(f'WoWStatusDB.labs.combo={value};WoWStatusLabs.render()')
        assert lua.eval('WoWStatusFeatures.enabled("combo")') is False, value
        assert lua.eval('WoWStatusLabsPage.rows[1]:GetChecked()') is False, value


def test_an_unknown_experiment_is_never_enabled_and_cannot_be_set():
    lua = make_lua()
    labs(lua)
    lua.execute('WoWStatusDB.labs.smuggled=true')
    assert lua.eval('WoWStatusFeatures.enabled("smuggled")') is False
    assert lua.eval('WoWStatusFeatures.set("smuggled",true)') is False
    assert lua.eval('WoWStatusFeatures.known("smuggled")') is False
    # Registering the same id twice does not add a second row.
    assert lua.eval('WoWStatusFeatures.register("combo","Again")') is False
    assert lua.eval('#WoWStatusFeatures.experiments()') == 2


def test_discord_stays_a_code_only_flag_and_off_the_page():
    lua = make_lua()
    labs(lua)
    assert lua.eval('WoWStatusFeatures.discord') is False
    assert lua.eval('WoWStatusFeatures.known("discord")') is False
    labels = [lua.eval(f'WoWStatusLabsPage.rows[{i}].label:GetText()') for i in (1, 2)]
    assert not any('iscord' in (label or '') for label in labels)


def test_the_page_says_so_when_a_version_ships_no_experiments():
    lua = make_lua()
    lua.execute('WoWStatusFeatures.forgetAll(); SlashCmdList.WOWSTATUS("labs")')
    assert lua.eval('#WoWStatusFeatures.experiments()') == 0
    assert lua.eval('WoWStatusLabsPage.empty:IsShown()') is True
    assert lua.eval('WoWStatusLabsPage.empty:GetText()') == 'No experiments in this version yet.'
    assert lua.eval('WoWStatusLabsPage.allOff.enabled') is False


def test_the_rows_and_the_button_are_controller_controls_in_a_scroll_frame():
    lua = make_lua()
    page = labs(lua)
    # AGENTS.md: every interactive element a CheckButton/Button with an OnClick,
    # lists in a ScrollFrame, so the gamepad frame walk reaches them.
    assert page.rows[1].kind == 'CheckButton'
    assert page.rows[1].OnClick is not None
    assert page.allOff.kind == 'Button'
    assert page.allOff.OnClick is not None
    assert page.scroll.kind == 'ScrollFrame'
    assert lua.eval('WoWStatusLabsPage.rows[1]:GetParent()==WoWStatusLabsPage.child') is True
    # The page lives in the main window, which is the frame B closes.
    assert lua.eval('WoWStatusMainWindow.has("labs")') is True
    assert lua.eval('WoWStatusLabsPage:GetParent()') is not None


def test_nynorsk_labels_are_translated():
    lua = make_lua()
    lua.execute('WoWStatusLocale.set("nn")')
    labs(lua)
    assert lua.eval('WoWStatusLabsPage.heading:GetText()') == 'Laben'
    assert lua.eval('WoWStatusLabsPage.allOff:GetText()') == 'Slå av alle eksperiment'
    assert 'eksperiment' in lua.eval('WoWStatusLabsPage.hint:GetText()').lower()
