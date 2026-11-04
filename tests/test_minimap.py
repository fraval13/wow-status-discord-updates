"""Minimap geometry with simulated frames; rendering requires a game client."""
from pathlib import Path

import pytest
from test_addon import STUBS, lupa

ROOT = Path(__file__).parents[1]


def minimap_runtime(client):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS + '''
        function methods:RegisterForClicks() end
        function methods:GetHeight() return self.height end
        function methods:HookScript(event, fn) self[event]=fn end
        function methods:SetPoint(...) self.point={...} end
        Minimap=CreateFrame("Frame","Minimap",UIParent)
        Minimap:SetSize(198,198)
        function Minimap:GetCenter() return 20,30 end
        function Minimap:GetEffectiveScale() return .75 end
        function GetCursorPosition() return 150,22.5 end
        WoWStatusDB={minimap_angle=0}
    ''')
    lua.execute((ROOT / 'addon/shared/Safe.lua').read_text())
    lua.globals().WoWStatusAdapter = lua.table_from({'client_id': client})
    lua.execute((ROOT / 'addon/shared/Minimap.lua').read_text())
    lua.execute('WoWStatusMinimap.init(WoWStatusDB)')
    return lua


@pytest.mark.parametrize('client', ['retail', 'forever', 'classic-era', 'tbc-anniversary'])
def test_button_follows_modern_map_rim_and_preserves_classic_distance(client):
    lua = minimap_runtime(client)
    modern = client in ('retail', 'forever')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == (109 if modern else 80)
    lua.execute('''
        assert(WoWStatusDB.minimap_angle==0)
        Minimap:SetSize(280,240)
        Minimap.OnSizeChanged()
    ''')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == (150 if modern else 80)
    lua.execute('WoWStatusDB.minimap_angle=90;Minimap.OnShow()')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == pytest.approx(0, abs=1e-10)
    assert lua.eval('WoWStatusMinimapButton.point[5]') == (130 if modern else 80)
    lua.execute('''
        local button=WoWStatusMinimapButton
        button.OnDragStart(button);button.OnUpdate(button,.1);button.OnDragStop(button)
        assert(WoWStatusDB.minimap_angle==0)
        assert(button.OnUpdate==nil)
    ''')
    assert lua.eval('WoWStatusMinimapButton.point[4]') == (150 if modern else 80)


@pytest.mark.parametrize('client', ['retail', 'forever'])
def test_unavailable_map_dimensions_are_safe_and_later_layout_recovers(client):
    lua = minimap_runtime(client)
    lua.execute('''
        Minimap:SetSize(0,0);Minimap.OnSizeChanged()
        assert(WoWStatusMinimapButton.point[4]==80)
        __secret={}
        function issecretvalue(value) return value==__secret end
        Minimap:SetSize(__secret,198);Minimap.OnSizeChanged()
        assert(WoWStatusMinimapButton.point[4]==80)
        Minimap:SetSize(198,198);Minimap.OnShow()
        assert(WoWStatusMinimapButton.point[4]==109)
    ''')
