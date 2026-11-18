"""Quest/profession privacy applies to the recent buffer and persistent history."""
import pytest
from test_addon import STUBS, make_lua


def client():
    return make_lua(STUBS + '''
        __skills=0; __cap=75
        function GetNumSkillLines() return __skills end
        function GetSkillLineInfo() return "Blacksmithing",nil,nil,1,0,0,__cap end
    ''')


def record_progress(lua):
    lua.execute('''
        for id=1,100 do fire("QUEST_TURNED_IN",id) end
        __skills=1; fire("SKILL_LINES_CHANGED")
        __cap=150; fire("SKILL_LINES_CHANGED")
        fire("PLAYER_LEVEL_UP",2)
    ''')


def event_ids(lua, buffer):
    events = lua.eval(f'character().{buffer}.events' if buffer == 'history' else 'character().events')
    return {event.id: event.kind for event in events.values()}


def toggle_detail(lua, field, enabled):
    lua.globals().__field, lua.globals().__enabled = field, enabled
    lua.execute('''
        SlashCmdList.WOWSTATUS("")
        local found=false
        for _,check in ipairs(WoWStatusSetup.checks) do
            if check.group=="fields" and check.key==__field then
                check.widget:SetChecked(__enabled)
                check.widget.OnClick(check.widget)
                found=true
            end
        end
        assert(found)
    ''')


@pytest.mark.parametrize(('field', 'kind'), [('quests', 'quest'), ('professions', 'profession')])
def test_disabled_details_do_not_enter_either_history(field, kind):
    lua = client()
    toggle_detail(lua, field, False)
    record_progress(lua)
    for buffer in ('recent', 'history'):
        kinds = set(event_ids(lua, buffer).values())
        assert kind not in kinds
        assert kinds == {'level', 'profession' if kind == 'quest' else 'quest'}


@pytest.mark.parametrize(('field', 'kind'), [('quests', 'quest'), ('professions', 'profession')])
@pytest.mark.parametrize('path', ['settings', 'logout', 'history'])
def test_old_details_are_pruned_without_losing_other_progress(field, kind, path):
    lua = client()
    record_progress(lua)
    before = event_ids(lua, 'history')
    assert list(before.values()).count('profession') == 2  # learning and promotion
    assert set(before.values()) == {'level', 'quest', 'profession'}
    expected = {event_id: event_kind for event_id, event_kind in before.items() if event_kind != kind}
    if path == 'settings':
        toggle_detail(lua, field, False)
    else:
        lua.execute(f'character().settings.fields.{field}=false')
        if path == 'logout':
            lua.eval('fire')('PLAYER_LOGOUT')
        else:
            lua.execute('WoWStatusHistory.scrub(character())')
    assert event_ids(lua, 'history') == expected
    if path != 'history':
        assert event_ids(lua, 'recent') == expected
    # Turning the field back on cannot recover data that was removed.
    toggle_detail(lua, field, True)
    assert event_ids(lua, 'history') == expected
