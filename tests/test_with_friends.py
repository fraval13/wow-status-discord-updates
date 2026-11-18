"""Labs: "with Fra" on own log cards (#243)."""
from test_journal import actor, clock


def level_up(lua, level, party, hidden=(), enabled=True):
    lua.execute('WoWStatusFeatures.init(WoWStatusDB)')
    if enabled:
        lua.execute('WoWStatusFeatures.set("with", true)')
    names = ','.join(f'"{n}"' for n in party)
    hid = ','.join(f'["{n.lower()}"]=true' for n in hidden)
    lua.execute(f'''
        __party={{{names}}}
        function IsInRaid() return false end
        function UnitName(unit)
            local n=unit:match("^party(%d)$")
            if n then return __party[tonumber(n)] end
            return "Thora"
        end
        local hidden={{{hid}}}
        WoWStatusRoster.knownMember=function(group,k) return k:match("^[^-]+")~="stranger" end
        WoWStatusRoster.isHidden=function(k) return hidden[k:match("^[^-]+")] == true end
        __level={level}; fire("PLAYER_LEVEL_UP",{level})
    ''')
    return lua.eval('''(function()
        for _,e in ipairs(WoWStatusJournal.entries()) do
            if e.kind=="level" and e.owner then return WoWStatusJournal.withText(e) end
        end end)()''')


def test_names_known_friends_in_the_party_only():
    lua = actor('Thora'); clock(lua, 10)
    text = level_up(lua, 10, ['Mira', 'Stranger', 'Nils'])
    assert text == ' · with Mira, Nils'


def test_hidden_characters_are_never_named():
    lua = actor('Thora'); clock(lua, 10)
    assert level_up(lua, 10, ['Mira', 'Nils'], hidden=['Nils']) == ' · with Mira'


def test_nothing_without_the_toggle_or_a_party():
    lua = actor('Thora'); clock(lua, 10)
    assert level_up(lua, 10, ['Mira'], enabled=False) == ''
    lua2 = actor('Thora'); clock(lua2, 10)
    assert level_up(lua2, 10, []) == ''
    assert lua2.eval('WoWStatusDB.journal.with') is None
