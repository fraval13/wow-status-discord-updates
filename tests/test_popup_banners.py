"""Big banners, clickable popups and a movable popup position (#61)."""
from test_journal import actor, clock, deliver_popup

DRAG = '''
    local methods = getmetatable(WoWStatusLevelPopup).__index
    function methods:GetPoint() return "TOPLEFT", UIParent, "TOPLEFT", 300, -250 end
'''


def received(level, *, sender_name='Mira'):
    own, friend = actor(sender_name), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', level)
    deliver_popup(own, friend)
    clock(friend, 11)
    friend.eval('WoWStatusPopups.tick')()
    return friend


def test_every_tenth_and_maximum_level_get_a_big_banner():
    lua = received(20)
    assert lua.eval('WoWStatusLevelPopup:IsShown()') is True
    assert lua.eval('WoWStatusLevelPopup.big') is True
    assert lua.eval('WoWStatusLevelPopup.scale') > 1
    assert lua.eval('WoWStatusLevelPopup.heading.text') == 'LEVEL 20!'
    assert lua.eval('WoWStatusPopups.bigMoment({level=60})') is True  # Vanilla maximum
    assert lua.eval('WoWStatusPopups.bigMoment({level=33})') is False
    assert lua.eval('WoWStatusPopups.bigMoment({kind="zone", text="x"})') is False


def test_ordinary_levels_and_disabled_option_keep_the_normal_popup():
    lua = received(13)
    assert lua.eval('WoWStatusLevelPopup.big') is False
    assert lua.eval('WoWStatusLevelPopup.scale') == 1
    lua.eval('WoWStatusPopups.setBigBanners')(False)
    assert lua.eval('WoWStatusPopups.bigMoment({level=20})') is False
    assert lua.eval('WoWStatusPopups.options().big_banners') is False


def test_big_banners_still_queue_one_at_a_time():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    for level, at in ((20, 10), (30, 20)):
        clock(own, at)
        own.eval('fire')('PLAYER_LEVEL_UP', level)
        own.eval('WoWStatusPopups.tick')()
    count = own.eval('#__sent')
    for i in range(1, count + 1):
        packet = own.eval(f'__sent[{i}]')
        if packet['prefix'] == 'WoWStatus':
            friend.eval('fire')('CHAT_MSG_ADDON', 'WoWStatus', packet['text'], 'WHISPER', 'Mira-TestRealm')
    assert friend.eval('#WoWStatusJournal.entries()') == 2
    seen = []
    for at in (11, 12, 18, 25, 32):
        clock(friend, at)
        friend.eval('WoWStatusPopups.tick')()
        heading = friend.eval('WoWStatusLevelPopup.heading.text')
        if not seen or seen[-1] != heading:
            seen.append(heading)
    # One at a time, in order; the level-20 First notice follows its level-up.
    assert seen == ['LEVEL 20!', 'A NEW FIRST!', 'LEVEL 30!', 'A NEW FIRST!']


def test_left_click_opens_the_log_entry_and_right_click_only_dismisses():
    lua = received(13)
    lua.execute('''
        local toast = WoWStatusLevelPopup
        toast.OnMouseUp(toast, "RightButton")
        assert(not toast:IsShown())
        assert(WoWStatusMainWindow.active() == nil)
    ''')
    lua = received(14)
    lua.execute('''
        local toast = WoWStatusLevelPopup
        local id = WoWStatusJournal.eventID(toast.item.sender, toast.item.nonce)
        assert(WoWStatusJournal.contains(id))
        toast.OnMouseUp(toast, "LeftButton")
        assert(not toast:IsShown())
        assert(WoWStatusMainWindow.active() == "activity")
        local index
        for i, e in ipairs(WoWStatusActivityLog.entriesList) do if e.id == id then index = i end end
        assert(index and WoWStatusActivityLog.scroll.scroll == (index - 1) * 132)
    ''')


def test_previews_do_not_open_the_log():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('''
        WoWStatusPopups.preview("level")
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        toast.OnMouseUp(toast, "LeftButton")
        assert(not toast:IsShown() and WoWStatusMainWindow.active() == nil)
    ''')


def test_popup_moves_only_when_unlocked_and_the_position_is_saved_and_reset():
    lua = actor('Thora')
    clock(lua, 10)
    lua.execute('WoWStatusPopups.preview("level"); WoWStatusPopups.tick()')
    lua.execute(DRAG)
    lua.execute('''
        local toast = WoWStatusLevelPopup
        toast.OnDragStart(toast); toast.OnDragStop(toast)
        assert(WoWStatusDB.popups.popup_position == nil)
        assert(toast.handle.visible == false)
        WoWStatusPopups.setUnlocked(true)
        assert(toast.handle.visible == true and WoWStatusPopups.options().unlocked)
        toast.OnDragStart(toast)
        assert(toast.dragging)
        local age = toast.age
        toast.OnUpdate(toast, 10)
        assert(toast.age == age and toast:IsShown()) -- held while moving
        toast.OnDragStop(toast)
        local p = WoWStatusDB.popups.popup_position
        assert(p.point == "TOPLEFT" and p.x == 300 and p.y == -250)
        toast.OnMouseUp(toast, "LeftButton") -- ends the drag; not a dismissal
        assert(toast:IsShown())
        WoWStatusPopups.resetPosition()
        assert(WoWStatusDB.popups.popup_position == nil)
    ''')


def test_preview_page_has_the_popup_options():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        assert(panel.unlock and panel.reset and panel.big)
        assert(panel.big.checked == true and not panel.unlock.checked)
        panel.unlock:SetChecked(true); panel.unlock.OnClick(panel.unlock)
        assert(WoWStatusDB.popups.popup_unlocked == true)
        panel.big:SetChecked(false); panel.big.OnClick(panel.big)
        assert(WoWStatusDB.popups.big_banners == false)
        WoWStatusDB.popups.popup_position = {point="TOP", x=1, y=2}
        panel.reset.OnClick(panel.reset)
        assert(WoWStatusDB.popups.popup_position == nil)
    ''')
