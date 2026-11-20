"""Gear transport across Forever's legacy realm and regional-name clients."""
import pytest
from test_equipment import GEAR
from test_equipment_sync import Network
from test_forever import REALMLESS, forever_runtime


class ForeverNetwork(Network):
    def add(self, name):
        first=name.split()[0]
        lua=forever_runtime(name=first, extra=REALMLESS+GEAR+'''
            __now=1793000000;__mono=0;__peers={}
            function time() return math.floor(__now) end
            function GetTime() return __mono end
            function UnitRace() return "Dwarf","Dwarf" end
            function UnitSex() return 3 end
            Enum.SendAddonMessageResult={Success=0}
            local send=C_ChatInfo.SendAddonMessage
            C_ChatInfo.SendAddonMessage=function(...) send(...);return 0 end
        ''')
        lua.globals()['__full']=name
        lua.globals()['__pid']=(first.encode().hex()*8)[:16]
        lua.execute('''
            function UnitGUID() return "Player-123-"..__pid:sub(1,8) end
            function GetPlayerInfoByGUID(guid)
                if guid==UnitGUID("player") then return "Warrior","WARRIOR","Dwarf","Dwarf",3,__full,"" end
            end
            fire("PLAYER_LOGIN")
            WoWStatusDB.roster.id=__pid
            WoWStatusDB.player_name="SyntheticPlayer"..__pid:sub(1,2)
            WoWStatusGroups.update("synthetic-gear-group","")
            WoWStatusEquipment.capture(WoWStatusPopups.character())
            WoWStatusRoster.observe(WoWStatusPopups.character())
        ''')
        self.clients[name]=lua
        self.offsets[name]=lua.eval('#__sent')
        return lua


def gear(lua,name):
    return lua.eval('(WoWStatusEquipmentSync.get(...))',name)


@pytest.mark.parametrize('legacy', [False,True])
def test_realmless_forever_fetches_and_refreshes_an_online_friends_gear(legacy):
    net=ForeverNetwork('Mira Stone','Thora Vale')
    mira,thora=net.clients['Mira Stone'],net.clients['Thora Vale']
    if legacy:
        mira.execute('''
            function RegionalUniqueNamesEnabled() return false end
            function GetRealmName() return "Legacy Realm" end
            function GetNormalizedRealmName() return "LegacyRealm" end
            character().normalized_realm="LegacyRealm"
        ''')
    net.advance(180)
    for lua,name in ((thora,'Mira Stone-PvE'),(mira,'Thora Vale-LegacyRealm')):
        snapshot=gear(lua,name)
        assert snapshot is not None
        assert snapshot['items'][1].startswith('item:16963:1503:')
    for lua in net.clients.values():
        for packet in lua.eval('__sent').values():
            if packet['prefix']=='WoWStatusChr' and packet['text'].split()[0] in ('H','J','F','T'):
                assert '-' not in packet['target']
    old=gear(thora,'Mira Stone-PvE').revision
    mira.execute('__gear[1]="item:42:0:0:0:0:0:0:0"')
    thora.eval('WoWStatusRoster.syncNow')()
    net.advance(180)
    assert gear(thora,'Mira Stone-PvE')['items'][1].startswith('item:42:')
    assert gear(thora,'Mira Stone-PvE').revision>old
