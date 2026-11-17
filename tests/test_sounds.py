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


def sound_for(lua, item):
    return lua.eval(f'WoWStatusPopups.soundFor({item})')


def test_dungeons_and_joins_have_their_own_sounds_and_follow_everything_else_until_chosen():
    lua = actor('Thora')
    lua.execute('WoWStatusPopups.setSound("other", 878)')
    for item in ('{kind="dungeon"}', '{kind="raid"}', '{kind="introduction"}', '{kind="mount"}'):
        assert sound_for(lua, item) == 878
    lua.execute('WoWStatusPopups.setSound("dungeon", 8960); WoWStatusPopups.setSound("join", 0)')
    assert sound_for(lua, '{kind="dungeon"}') == 8960
    assert sound_for(lua, '{kind="introduction"}') == 0
    assert sound_for(lua, '{kind="mount"}') == 878


def test_big_moments_keep_their_usual_sound_until_one_is_chosen():
    lua = actor('Thora')
    lua.execute('WoWStatusPopups.setSound("level", 888); WoWStatusPopups.setSound("dungeon", 8960)')
    assert lua.eval('WoWStatusPopups.soundChoice("big")') == lua.eval('WoWStatusPopups.SOUND_USUAL')
    assert lua.eval('WoWStatusPopups.sound("big")') is None
    assert sound_for(lua, '{level=40}') == 888
    assert sound_for(lua, '{kind="raid"}') == 8960
    lua.execute('WoWStatusPopups.setSound("big", 12889)')
    assert sound_for(lua, '{level=40}') == 12889
    assert sound_for(lua, '{kind="raid"}') == 12889
    assert sound_for(lua, '{kind="epicmount"}') == 12889
    assert sound_for(lua, '{level=42}') == 888
    assert sound_for(lua, '{kind="dungeon"}') == 8960
    # Turning big banners off keeps the big sound: it is chosen on its own.
    lua.execute('WoWStatusPopups.setBigBanners(false)')
    assert sound_for(lua, '{level=40}') == 12889
    lua.execute('WoWStatusPopups.setSound("big", WoWStatusPopups.SOUND_USUAL)')
    assert sound_for(lua, '{level=40}') == 888
    assert lua.eval('WoWStatusDB.popups.sounds.big') is None


def test_a_big_level_plays_the_big_moment_sound():
    setup = 'WoWStatusPopups.setSound("level", 888); WoWStatusPopups.setSound("big", 8959)'
    assert shown(('PLAYER_LEVEL_UP', 40), setup) == [8959]
    assert shown(('PLAYER_LEVEL_UP', 42), setup) == [888]


def test_a_missing_or_invalid_sound_plays_nothing():
    lua = actor('Thora')
    lua.execute('''
        __played = {}; function PlaySound(id) table.insert(__played, id); error("no such kit") end
        WoWStatusPopups.playSound(0); WoWStatusPopups.playSound(-1); WoWStatusPopups.playSound("x"); WoWStatusPopups.playSound(nil)
        assert(#__played == 0)
        WoWStatusPopups.playSound(8959)
        assert(#__played == 1)
        PlaySound = nil
        WoWStatusPopups.playSound(8959)
    ''')


def test_kinds_that_follow_another_sound_can_go_back_to_it():
    lua = actor('Thora')
    lua.execute('''
        __played = {}; function PlaySound(id) table.insert(__played, id) end
        WoWStatusPreviews.show()
        local panel = WoWStatusNotificationPreviews
        for _, kind in ipairs({"dungeon", "join", "big"}) do assert(panel.sounds[kind], kind) end
        local button = panel.sounds.big
        assert(button.text == "Same as usual")
        local function pick(label)
            button.OnClick(button)
            for _, row in ipairs(WoWStatusMenu.rows) do
                if row:IsShown() and row.text.text == label then row.OnClick(row); return end
            end
            error("no row " .. label)
        end
        pick("Alarm")
        assert(WoWStatusPopups.sound("big") == 12889 and button.text == "Alarm" and __played[1] == 12889)
        pick("Same as usual")
        -- Dungeons follow "Everything else" until picked, and can follow it again.
        WoWStatusPopups.setSound("other", 878)
        local dungeon = panel.sounds.dungeon
        assert(dungeon.text == "Same as usual" and WoWStatusPopups.soundFor({kind="raid"}) == 878)
        button = dungeon
        pick("Ready check")
        assert(dungeon.text == "Ready check" and WoWStatusPopups.soundFor({kind="raid"}) == 8960)
        pick("Same as usual")
        -- Going back previews what will play: the "Everything else" sound.
        assert(dungeon.text == "Same as usual" and WoWStatusPopups.soundFor({kind="raid"}) == 878 and __played[3] == 878)
        button = panel.sounds.big
        assert(WoWStatusPopups.soundChoice("big") == WoWStatusPopups.SOUND_USUAL and button.text == "Same as usual" and #__played == 3 and __played[2] == 8960)
    ''')


def test_every_sound_picker_is_reachable_with_a_controller():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusPreviews.show()
        -- The shared frame mock has no layout: give every frame a kind, its children and a place.
        local methods = getmetatable(CreateFrame("Frame")).__index
        function methods:GetObjectType() return self.kind end
        function methods:GetChildren()
            local list = {}
            for _, f in ipairs(__frames) do if f.parent == self then list[#list + 1] = f end end
            return (unpack or table.unpack)(list)
        end
        function methods:GetScript(name) return self[name] end
        function methods:GetRect() return 0, 0, 10, 10 end
        local panel = WoWStatusNotificationPreviews
        local reached = {}
        for _, control in ipairs(WoWStatusGamepad.controls(panel, {panel})) do reached[control] = true end
        for _, entry in ipairs(WoWStatusPopups.SOUND_KINDS) do assert(reached[panel.sounds[entry[1]]], entry[1]) end
    ''')
