"""Reaction whispers on friends' notifications: GZ!, F / Git Good, Congrats!"""
from test_journal import actor, clock, deliver_popup


def sent_whispers(lua):
    return [(p['text'], p['target']) for p in lua.eval('__sent').values()
            if p['kind'] == 'WHISPER' and not p['prefix']]


def test_level_up_offers_gz_and_whispers_it_once():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast:IsShown() and toast.reactions[1]:IsShown() and toast.reactions[1].text == "GZ!")
        toast.reactions[1].OnClick(toast.reactions[1])
        assert(not toast.reactions[1]:IsShown())
        assert(toast.detail.text:find("GZ!", 1, true))
        -- A second click is not possible, and a direct second reaction is refused.
        assert(not WoWStatusPopups.react(toast.item, "GZ!"))
    ''')
    assert sent_whispers(friend) == [('GZ!', 'Mira-TestRealm')]


def test_each_kind_gets_fitting_reactions():
    lua = actor('Thora')
    lua.execute('''
        local function r(item) return table.concat(WoWStatusPopups.reactions(item), "|") end
        assert(r({sender="Mira-TestRealm", level=10}) == "GZ!")
        assert(r({sender="Mira-TestRealm", kind="death", text="Died"}) == "F|Git Good")
        for _, kind in ipairs({"profession","dungeon","raid","mount","epicmount","reputation","unlock","pvp","quest","zone","loot"}) do
            assert(r({sender="Mira-TestRealm", kind=kind}) == "Congrats!", kind)
        end
        assert(r({sender="Mira-TestRealm", kind="introduction"}) == "Welcome!")
        -- A record notice names a real friend; sample previews and yourself get nothing.
        assert(r({sender="Mira-TestRealm", kind="first", preview=true, key="local-notice"}) == "Congrats!")
        assert(r({sender="Previewlock", kind="death", preview=true, key="local-preview"}) == "")
        assert(r({sender="Thora-TestRealm", level=10}) == "")
        assert(r({sender="Mira-TestRealm", kind="recap"}) == "")
    ''')


def test_a_hovered_notification_stays_until_the_mouse_leaves():
    own, friend = actor('Mira'), actor('Thora')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_DEAD')
    deliver_popup(own, friend)
    friend.execute('''
        WoWStatusPopups.tick()
        local toast = WoWStatusLevelPopup
        assert(toast.reactions[1].text == "F" and toast.reactions[2].text == "Git Good")
        local death = toast.item
        __over = true
        function MouseIsOver(frame) return __over and frame == toast end
        local start = time()
        function time() return start + 30 end
        WoWStatusPopups.tick()
        assert(toast:IsShown() and toast.item == death)
        __over = false
        function time() return start + 40 end
        WoWStatusPopups.tick()
        -- The death notification closed; Mira's "First in the group to die" record follows.
        assert(toast.item ~= death and toast.item.kind == "first")
        assert(toast.reactions[1].text == "Congrats!")
    ''')
