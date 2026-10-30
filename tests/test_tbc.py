"""TBC Anniversary API/protocol mocks; live-client acceptance is still required."""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_addon import STUBS, lupa

from wow_status.schema import ValidationError, validate

ROOT = Path(__file__).parents[1]


def tbc_runtime(name='Thora', extra=''):
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(STUBS.replace('return "Thora" end',f'return "{name}" end') + '''
        WOW_PROJECT_BURNING_CRUSADE_CLASSIC=5
        WOW_PROJECT_ID=5
        __level=69
        function GetBuildInfo() return "2.5.6","70577","test",20506 end
        C_Item={GetItemInfo=GetItemInfo}
        GetItemInfo=nil
    ''' + extra)
    runtime.globals().date = lambda fmt, at: datetime.fromtimestamp(at,timezone.utc).strftime(fmt.lstrip('!'))
    folder = ROOT/'addon/tbc/WoWStatus'
    for line in (folder/'WoWStatus.toc').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            runtime.execute((folder/line.strip()).read_text())
    runtime.eval('fire')('PLAYER_LOGIN')
    runtime.execute('WoWStatusGroups.announce=nil')
    return runtime


def test_tbc_supports_70_and_rejects_other_client_editions():
    lua=tbc_runtime()
    lua.execute('''
        assert(character().identity.client=="tbc-anniversary")
        assert(character().identity.interface==20506)
        __level=70;fire("PLAYER_LEVEL_UP",70)
        assert(character().events[1].data.maximum)
        assert(character().snapshot.level==70)
        __level=71;fire("PLAYER_LEVEL_UP",71)
        assert(#character().events==1)
        assert(WoWStatusAdapter.level()==nil)
        WOW_PROJECT_ID=2;assert(not WoWStatusAdapter.supported())
        WOW_PROJECT_ID=1;assert(not WoWStatusAdapter.supported())
        WOW_PROJECT_ID=18;assert(not WoWStatusAdapter.supported())
        WOW_PROJECT_ID=5
        function GetBuildInfo() return "3.4.0","0","test",30400 end
        assert(not WoWStatusAdapter.supported())
    ''')


def test_tbc_levels_roundtrip_and_reject_vanilla_forever_packets():
    own,friend=tbc_runtime(),tbc_runtime('Eldrin')
    for lua in (own,friend):
        lua.eval('WoWStatusGroups.update')('navsquad','')
    own.eval('fire')('PLAYER_LEVEL_UP',70)
    packet=own.eval('__sent[1].text')
    assert 'WSTATUS2 tbc-anniversary LEVEL 70 ' in packet
    friend.eval('fire')('CHAT_MSG_ADDON','WoWStatus',packet,'WHISPER','Thora-TestRealm')
    assert 'level 70!' in friend.eval('WoWStatusLevelPopup.message:GetText()')
    assert friend.eval('#WoWStatusJournal.entries()')==1
    channel=friend.eval('function() for id in pairs(character().group_ids) do return WoWStatusGroups.channel(id) end end')()
    for client in ('classic-era','forever'):
        assert not friend.eval('WoWStatusPopups.receive')(
            f'WSTATUS2 {client} LEVEL 33 1793000000 other', 'Thora-TestRealm',channel)


def test_tbc_jewelcrafting_and_master_titles_and_first_equip():
    lua=tbc_runtime(extra='''
        __skills=0;__cap=75
        function GetNumSkillLines() return __skills end
        function GetSkillLineInfo() return "Jewelcrafting",false,false,1,0,0,__cap end
    ''')
    lua.execute('''
        __skills=1;fire("SKILL_LINES_CHANGED")
        assert(#character().events==1)
        assert(character().events[1].data.learned)
        assert(character().snapshot.professions[1].key=="jewelcrafting")
        __cap=375;fire("SKILL_LINES_CHANGED")
        assert(character().events[2].data.title=="Master")
        __slot="|Hitem:123|h[Armor]|h";fire("PLAYER_EQUIPMENT_CHANGED",1)
        assert(character().events[3].data.first_equip)
        fire("PLAYER_EQUIPMENT_CHANGED",1)
        assert(#character().events==3)
        assert(WoWStatusFeatures.discord==false)
        assert(character().settings.discord_enabled==false)
    ''')


def test_tbc_protocol_cap_and_character_namespace(store,payload,clone):
    original=store.ingest('owner',payload)['character_id']
    tbc=clone(payload)
    tbc['identity']['client']='tbc-anniversary'
    tbc['snapshot']['level']=70
    tbc['events'][1]['data']['level']=70
    assert validate(tbc)['events'][1]['data']['maximum']
    tbc_id=store.ingest('owner',tbc)['character_id']
    assert tbc_id!=original
    tbc['events'][1]['data']['level']=71
    with pytest.raises(ValidationError):
        validate(tbc)
    tbc['events']=[]
    tbc['snapshot']['level']=71
    with pytest.raises(ValidationError):
        validate(tbc)


def test_tbc_installer_selects_the_correct_client_and_interface(tmp_path):
    addons=tmp_path/'Interface/AddOns'
    addons.mkdir(parents=True)
    command=[sys.executable,str(ROOT/'scripts/install_addon.py'),'--client','tbc',
             '--addons-dir',str(addons),'--interface']
    invalid=subprocess.run([*command,'11509'],capture_output=True,text=True)
    assert invalid.returncode!=0 and not (addons/'WoWStatus').exists()
    subprocess.run([*command,'20506'],check=True,capture_output=True,text=True)
    assert (addons/'WoWStatus/TBC.lua').is_file()
    assert '## Interface: 20506' in (addons/'WoWStatus/WoWStatus.toc').read_text()
