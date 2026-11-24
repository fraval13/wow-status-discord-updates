"""Battlegrounds report their result, not every death inside them."""
from test_journal import actor, clock, deliver_popup

BG = '''
__instance, __winner, __bg = nil, nil, "Warsong Gulch"
function IsInInstance() return __instance ~= nil, __instance end
function GetBattlefieldWinner() return __winner end
function GetInstanceInfo() return __bg, __instance end
function UnitFactionGroup() return "Alliance" end
function kinds()
    local list = {}
    for _, e in ipairs(character().events) do list[#list + 1] = e.kind end
    return table.concat(list, ",")
end
'''


def player(name='Mira'):
    lua = actor(name)
    lua.execute(BG)
    clock(lua, 10)
    return lua


def test_deaths_in_a_battleground_or_arena_are_neither_announced_nor_counted():
    lua = player()
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('kinds()') == 'death'          # Out in the world, as before.
    before = lua.eval('WoWStatusProgress.totalDeaths(character())')
    for where in ('pvp', 'arena'):
        lua.execute(f'__instance = "{where}"; character().death_latched = false')
        lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('kinds()') == 'death'          # Still only the first one.
    assert lua.eval('WoWStatusProgress.totalDeaths(character())') == before
    # A death back in the open world is announced again.
    lua.execute('__instance = nil; character().death_latched = false')
    lua.eval('fire')('PLAYER_DEAD')
    assert lua.eval('kinds()') == 'death,death'


def test_a_finished_battleground_is_reported_once_with_its_name():
    lua = player()
    lua.execute('__instance = "pvp"')
    lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')   # Mid-match: no winner yet.
    assert lua.eval('kinds()') == ''
    lua.execute('__winner = 1')                     # 1 is Alliance, so a win.
    for _ in range(3):
        lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    assert lua.eval('kinds()') == 'battleground'    # The event repeats; we do not.
    event = lua.eval('character().events[1]')
    assert event.data.won is True and event.data.name == 'Warsong Gulch'
    assert lua.eval('WoWStatusPopups.eventText')(event) == 'Won Warsong Gulch'
    # Leaving clears the latch, and the next match is reported on its own terms.
    lua.execute('__instance, __winner = nil, nil')
    lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    lua.execute('__instance, __winner, __bg = "pvp", 0, "Arathi Basin"')
    lua.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    assert lua.eval('kinds()') == 'battleground,battleground'
    lost = lua.eval('character().events[2]')
    assert lost.data.won is False
    assert lua.eval('WoWStatusPopups.eventText')(lost) == 'Lost Arathi Basin'


def test_the_result_reaches_a_friend_and_reads_as_a_battleground():
    own, friend = player('Mira'), player('Thora')
    own.execute('__instance, __winner = "pvp", 1')
    own.eval('fire')('UPDATE_BATTLEFIELD_STATUS')
    deliver_popup(own, friend)
    friend.execute('''
        __text = nil
        for _, e in ipairs(WoWStatusJournal.entries()) do
            if e.kind == "battleground" then __text = e.text end
        end
        local item = {kind="battleground", text="Won Warsong Gulch", sender="Mira-TestRealm"}
        local _, _, _, _, won = WoWStatusPresentation.theme(item)
        item.text = "Lost Arathi Basin"
        local _, _, _, _, lost = WoWStatusPresentation.theme(item)
        __headings = won .. " / " .. lost
        -- This kind has no caption bank, so the line under it is empty. The
        -- harness clock sits inside Hallow's End, and seasonal captions apply to
        -- every kind but death, so the holiday is stubbed away to see that.
        WoWStatusFlavour.holiday = function() return nil end
        __caption = WoWStatusFlavour.text(item)
    ''')
    assert friend.eval('__text') == 'Won Warsong Gulch'
    assert friend.eval('__headings') == 'BATTLEGROUND WON! / BATTLEGROUND LOST'
    assert friend.eval('__caption') == ''
