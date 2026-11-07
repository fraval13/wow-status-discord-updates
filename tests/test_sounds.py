"""A sound per kind of notification; nothing plays unless chosen."""
from test_journal import actor, clock, deliver_popup


def shown(event, setup=''):
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    friend.execute('__played = {}; function PlaySound(id) table.insert(__played, id) end; ' + setup)
    own.eval('fire')(*event)
    deliver_popup(own, friend)
    friend.eval('WoWStatusPopups.tick')()
    assert friend.eval('WoWStatusLevelPopup:IsShown()')
    return list(friend.eval('__played').values())


def test_no_sound_unless_chosen():
    assert shown(('PLAYER_LEVEL_UP', 42)) == []


def test_each_kind_plays_its_own_sound():
    setup = 'WoWStatusPopups.setSound("level", 888); WoWStatusPopups.setSound("death", 8959)'
    assert shown(('PLAYER_LEVEL_UP', 42), setup) == [888]
    assert shown(('PLAYER_DEAD',), setup) == [8959]


def test_the_old_sound_switch_makes_the_chime_the_default():
    assert shown(('PLAYER_LEVEL_UP', 42), 'WoWStatusDB.popups.sound = true') == [850]
    assert shown(('PLAYER_LEVEL_UP', 42), 'WoWStatusDB.popups.sound = true; WoWStatusPopups.setSound("level", 0)') == []


def test_picking_a_sound_in_the_settings_plays_it():
    lua = actor('Thora')
    lua.execute('''
        __played = {}; function PlaySound(id) table.insert(__played, id) end
        WoWStatusPreviews.show()
        local button = WoWStatusNotificationPreviews.sounds.death
        assert(button.text == "None")
        button.OnClick(button)
        local pick
        for _, row in ipairs(WoWStatusMenu.rows) do if row:IsShown() and row.text.text == "Raid warning" then pick = row end end
        pick.OnClick(pick)
        assert(__played[1] == 8959 and WoWStatusPopups.sound("death") == 8959 and button.text == "Raid warning")
    ''')
