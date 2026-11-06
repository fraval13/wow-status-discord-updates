"""Quiet mode: notifications wait inside the instances ticked (off by default)."""
from test_journal import actor, clock, deliver_popup


def level_up(inside):
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    friend.execute(f'__inside = "{inside}"; function IsInInstance() return __inside ~= "none", __inside end')
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    return own, friend


def test_quiet_mode_is_off_by_default():
    own, friend = level_up('party')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert friend.eval('WoWStatusLevelPopup:IsShown()')


def test_notifications_wait_in_a_ticked_instance_and_show_afterwards():
    own, friend = level_up('raid')
    friend.execute('WoWStatusPopups.setQuiet("enabled", true)')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert not friend.eval('WoWStatusLevelPopup and WoWStatusLevelPopup:IsShown()')
    friend.execute('__inside = "none"')
    clock(friend, 30)
    friend.eval('WoWStatusPopups.tick')()
    assert friend.eval('WoWStatusLevelPopup:IsShown()')


def test_unticked_instances_and_previews_are_not_held():
    own, friend = level_up('pvp')
    friend.execute('WoWStatusPopups.setQuiet("enabled", true); WoWStatusPopups.setQuiet("pvp", false)')
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert friend.eval('WoWStatusLevelPopup:IsShown()')
    lua = actor('Thora')
    lua.execute('''
        function IsInInstance() return true, "party" end
        WoWStatusPopups.setQuiet("enabled", true)
        WoWStatusPopups.preview("death")
        WoWStatusPopups.tick()
        assert(WoWStatusLevelPopup:IsShown())
    ''')


def test_notifications_page_has_the_quiet_mode_checkboxes():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(not panel.quiet:GetChecked())
        panel.quiet:SetChecked(true); panel.quiet.OnClick(panel.quiet)
        assert(WoWStatusPopups.quietSettings().enabled)
        local raids = panel.quietKinds.raid
        assert(raids:GetChecked())
        raids:SetChecked(false); raids.OnClick(raids)
        assert(WoWStatusPopups.quietSettings().raid == false)
    ''')
