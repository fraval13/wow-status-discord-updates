"""Group status line under the quest tracker (#62)."""
from test_journal import actor, clock, deliver_popup

TRACKER = '''
    QuestWatchFrame = CreateFrame("Frame", "QuestWatchFrame", UIParent); QuestWatchFrame:Show()
    local methods = getmetatable(QuestWatchFrame).__index
    function methods:SetPoint(point, relative, relativePoint, x, y) self.anchor = {point, relative, relativePoint, x, y} end
    function methods:GetPoint() return "TOPLEFT", UIParent, "TOPLEFT", 40, -50 end
'''


def line(lua):
    return lua.eval('WoWStatusStatusLineFrame')


def test_line_shows_online_count_and_latest_announcement_and_updates_live():
    own, friend = actor('Mira'), actor('Thora')
    friend.execute(TRACKER)
    friend.execute('__peers={"Thora-TestRealm","Mira-TestRealm","Bob-TestRealm"}')
    friend.eval('WoWStatusStatusLine.update')()
    assert friend.eval('WoWStatusStatusLineFrame.text.text').startswith('WoW Status · ')
    clock(own, 10)
    clock(friend, 10)
    own.eval('fire')('PLAYER_LEVEL_UP', 42)
    deliver_popup(own, friend)
    clock(friend, 310)
    friend.eval('WoWStatusStatusLine.update')()
    text = friend.eval('WoWStatusStatusLineFrame.text.text')
    assert text.endswith('Mira hit 42 (5m)'), text
    assert ' online · ' in text


def test_online_count_uses_the_channel_count_without_requesting_a_roster():
    lua = actor('Thora')
    lua.execute('''
        __peers={"Thora-TestRealm","A-TestRealm","B-TestRealm","C-TestRealm"}
        SetSelectedDisplayChannel = function() error("must not request a roster") end
        assert(WoWStatusPopups.onlineCount() == 3)
    ''')


def test_members_who_logged_off_stop_counting_as_online():
    lua = actor('Thora')
    lua.execute('''
        __peers={"Thora-TestRealm","A-TestRealm","B-TestRealm"}
        local group=next(character().group_ids)
        WoWStatusPopups.peers(group)
        for _=1,3 do WoWStatusPopups.tick() end
        assert(WoWStatusPopups.onlineCount() == 2)
        -- A and B log off: the old roster read no longer matches the channel.
        __peers={"Thora-TestRealm"}
        assert(WoWStatusPopups.onlineCount() == 0)
        -- A recently heard member who left is not counted either.
        WoWStatusPopups.notePeer(group,"A-TestRealm")
        assert(WoWStatusPopups.onlineCount() == 0)
        __peers={"Thora-TestRealm","A-TestRealm"}
        assert(WoWStatusPopups.onlineCount() == 1)
    ''')


def test_line_attaches_under_the_quest_tracker_or_floats():
    lua = actor('Thora')
    lua.execute(TRACKER)
    lua.execute('''
        WoWStatusStatusLine.update()
        local f = WoWStatusStatusLineFrame
        assert(f:IsShown() and f.attached and f.anchor[2] == QuestWatchFrame)
        WoWStatusStatusLine.set("attach", false)
        assert(not f.attached and f.anchor[1] == "TOPRIGHT")
        f.OnDragStart(f); f.OnDragStop(f)
        assert(WoWStatusDB.status_line.position.x == 40)
        WoWStatusStatusLine.update()
        assert(f.anchor[1] == "TOPLEFT" and f.anchor[4] == 40)
        -- Without a tracker an attached line floats too.
        QuestWatchFrame:Hide()
        WoWStatusStatusLine.set("attach", true)
        assert(not f.attached)
    ''')


def test_click_opens_the_main_window_but_a_drag_does_not():
    lua = actor('Thora')
    lua.execute(TRACKER)
    lua.execute('''
        WoWStatusStatusLine.set("attach", false)
        local f = WoWStatusStatusLineFrame
        f.OnDragStart(f); f.OnDragStop(f); f.OnClick(f)
        assert(WoWStatusMainWindow.active() == nil)
        f.OnClick(f)
        assert(WoWStatusMainWindow.active() == "activity")
    ''')


def test_hide_in_combat_and_instances_and_turn_off():
    lua = actor('Thora')
    lua.execute(TRACKER)
    lua.execute('''
        __inside = false
        function IsInInstance() return __inside, __inside and "party" or "none" end
        WoWStatusStatusLine.update()
        local f = WoWStatusStatusLineFrame
        assert(f:IsShown())
        fire("PLAYER_REGEN_DISABLED"); assert(f:IsShown())
        WoWStatusStatusLine.set("hide_combat", true); assert(not f:IsShown())
        fire("PLAYER_REGEN_ENABLED"); assert(f:IsShown())
        __inside = true; fire("ZONE_CHANGED_NEW_AREA"); assert(f:IsShown())
        WoWStatusStatusLine.set("hide_instance", true); assert(not f:IsShown())
        __inside = false; WoWStatusStatusLine.update(); assert(f:IsShown())
        WoWStatusStatusLine.set("enabled", false); assert(not f:IsShown())
    ''')


def test_no_line_without_a_group():
    lua = actor('Thora')
    lua.execute('WoWStatusGroups.update("", ""); WoWStatusStatusLine.update()')
    assert line(lua) is None or not lua.eval('WoWStatusStatusLineFrame:IsShown()')


def test_options_page_controls_the_status_line():
    lua = actor('Thora')
    lua.execute('''
        WoWStatusPreviews.show()
        local widgets = WoWStatusNotificationPreviews.line
        assert(widgets.enabled.checked == true and widgets.attach.checked == true and widgets.hide_combat.checked == false)
        widgets.hide_instance:SetChecked(true); widgets.hide_instance.OnClick(widgets.hide_instance)
        assert(WoWStatusDB.status_line.hide_instance == true)
    ''')


def test_you_are_never_your_own_peer_when_the_roster_names_your_realm_differently():
    # WoW Forever: GetNormalizedRealmName gives an internal realm name, so a roster
    # entry for you need not match "<name>-<normalized realm>" (#25 live report).
    lua = actor('Thora')
    lua.execute('''
        local group=next(character().group_ids)
        __peers={"Thora-Realm1PvE","A-Realm1PvE"}
        WoWStatusPopups.peers(group)
        for _=1,3 do WoWStatusPopups.tick() end
        local peers=WoWStatusPopups.peers(group)
        assert(#peers==1 and peers[1]=="A-Realm1PvE")
        assert(WoWStatusPopups.onlineCount()==1)
        -- With a GUID from the roster, that decides.
        C_ChatInfo.GetChannelRosterInfo=function(_, i)
            local list={{"Somebody",UnitGUID("player")},{"Thora","Player-999"}}
            return list[i][1],false,false,list[i][2]
        end
        assert(WoWStatusPopups.isSelf("Somebody",UnitGUID("player")))
        assert(not WoWStatusPopups.isSelf("Thora","Player-999"))
        WoWStatusPopups.notePeer(group,"Thora-Realm1PvE")
        assert(WoWStatusPopups.onlineCount()==1)
    ''')


def test_dragging_an_attached_line_unpins_it_from_the_tracker():
    # Live report: players tracking quests could not move the line, others could.
    lua = actor('Thora')
    lua.execute(TRACKER)
    lua.execute('''
        WoWStatusStatusLine.update()
        local f = WoWStatusStatusLineFrame
        assert(f.attached)
        f.OnDragStart(f); f.OnDragStop(f)
        assert(not f.attached and WoWStatusDB.status_line.attach == false)
        assert(WoWStatusDB.status_line.position.x == 40)
        -- It stays where it was dropped, also after the next update.
        WoWStatusStatusLine.update()
        assert(not f.attached and f.anchor[1] == "TOPLEFT")
    ''')
