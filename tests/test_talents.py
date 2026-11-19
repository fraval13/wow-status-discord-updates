"""Real tree geometry over bounded group whispers; no native talent mutation."""
import pytest
from test_client_compatibility import client_runtime
from test_equipment_sync import Network
from test_profile import open_profile

CLASSIC = r'''
function UnitClass() return "Warrior","WARRIOR",1 end
function GetNumTalentTabs() return 3 end
function GetTalentTabInfo(tab) return ({"Arms","Fury","Protection"})[tab],132400,0 end
function GetNumTalents() return 2 end
function GetTalentInfo(tab,index)
    return "Talent"..tab..index,132400+tab*10+index,index,index,index==1 and tab or 0,5
end
function GetTalentPrereqs(_,index) if index==2 then return 1,1,true end end
function GetSpellInfo(id)
    local spell=type(id)=="number" and id or 90000+tonumber(id:match("(%d+)$"))
    return "Talent "..spell,nil,132400,0,0,0,spell
end
function LearnTalent() error("a shared build must be read only") end
'''
MODERN = r'''
function UnitClass() return "Warrior","WARRIOR",1 end
function GetSpecialization() return 1 end
function GetSpecializationInfo() return 71,"Arms" end
C_ClassTalents={GetActiveConfigID=function() return 77 end}
C_Traits={
 GetConfigInfo=function() return {treeIDs={55}} end,
 GetTreeNodes=function() return {101,102,103} end,
 GetNodeInfo=function(_,id) return {posX=(id-101)*300,posY=(id-101)*400,
    currentRank=id==102 and 0 or 1,ranksPurchased=id==102 and 0 or 1,maxRanks=1,
    isVisible=true,entryIDs={id},visibleEdges=id==101 and {{targetNode=103}} or {}} end,
 GetEntryInfo=function(_,id) return {definitionID=id,maxRanks=1} end,
 GetDefinitionInfo=function(id) return {spellID=id+90000,overrideIcon=132400} end,
 PurchaseRank=function() error("a shared build must be read only") end,
}
C_Spell=C_Spell or {}
C_Spell.GetSpellInfo=function(id) return {name="Talent "..id,spellID=id,iconID=132400} end
'''


def talent_snapshot(lua, name='Mira-TestRealm'):
    return lua.eval('(WoWStatusTalents.get(...))', name)


@pytest.mark.parametrize('edition', ['vanilla', 'tbc', 'forever', 'retail'])
def test_captures_the_actual_tree_positions_ranks_and_prerequisites(edition):
    lua = client_runtime(edition)
    lua.execute(MODERN if edition in ('forever', 'retail') else CLASSIC)
    lua.execute('''
        local methods=getmetatable(CreateFrame("Frame")).__index
        function methods:CreateLine()
            local line=CreateFrame("Frame")
            function line:SetThickness() end
            function line:SetColorTexture() end
            function line:SetStartPoint(point,relative,...)
                assert(point=="CENTER" and relative.kind=="Button" and select("#",...)==0)
                self.start=relative
            end
            function line:SetEndPoint(point,relative,...)
                assert(point=="CENTER" and relative.kind=="Button" and select("#",...)==0)
                self.finish=relative
            end
            return line
        end
        local c=character()
        local build=WoWStatusTalents.capture(c)
        assert(build and build.class==1)
        assert(#build.nodes>0 and #build.edges>0)
        local decoded=WoWStatusTalents.decode(build.encoded)
        assert(decoded and #decoded.nodes==#build.nodes and decoded.nodes[1].rank==build.nodes[1].rank)
        assert(decoded.nodes[1].x==build.nodes[1].x and decoded.nodes[2].y==build.nodes[2].y)
        WoWStatusMainWindow.show("characters")
        local row={name=WoWStatusPopups.characterName(c),class="WARRIOR",race="Human",level=24}
        WoWStatusProfile.show(row,{self=true})
        local view=WoWStatusProfileView
        assert(view.talents and #view.talents.nodes==#build.nodes)
        assert(view.body.height>1600)
        assert(#view.talents.lines==#build.edges and view.talents.lines[1].start and view.talents.lines[1].finish)
        assert(view.talents.nodes[1].OnClick and view.talents.nodes[1].data.rank==build.nodes[1].rank)
        c.settings.fields.gear=false
        assert(WoWStatusTalents.capture(c)==nil and c.talent_profile==nil)
    ''')


def test_restricted_or_loading_traits_keep_the_last_public_snapshot():
    lua = client_runtime('forever')
    lua.execute(MODERN + '''
        local c=character()
        local good=WoWStatusTalents.capture(c)
        __secret={}
        function issecretvalue(value) return value==__secret end
        C_Traits.GetNodeInfo=function() return __secret end
        assert(WoWStatusTalents.capture(c)==good)
        C_ClassTalents.GetActiveConfigID=function() return nil end
        assert(WoWStatusTalents.capture(c)==good)
    ''')


def network():
    net = Network('Mira', 'Thora')
    net.clients['Mira'].execute(CLASSIC + 'WoWStatusTalents.capture(character())')
    net.advance()
    return net


def test_requested_tree_is_atomic_and_remains_available_for_an_offline_owner():
    net = network()
    thora = net.clients['Thora']
    assert thora.eval('WoWStatusTalents.request')('Mira-TestRealm')
    net.advance(30, drop=lambda source, target, text: source == 'Mira' and text.startswith('B ') and text.split()[3:6] and text.split()[3] == 'D' and text.split()[5] == '1')
    assert talent_snapshot(thora) is None
    # A new explicit refresh supersedes the incomplete token after its cooldown.
    net.advance(2)
    assert thora.eval('WoWStatusTalents.request')('Mira-TestRealm')
    net.advance(35)
    build = talent_snapshot(thora)
    assert build is not None and len(build.nodes) == 6 and build.nodes[1].rank == 1
    assert all(len(text.encode()) <= 250 for _, _, text in net.packets)
    net.clients.pop('Mira')
    net.advance(5)
    assert talent_snapshot(thora).encoded == build.encoded
    view = open_profile(thora, 'Mira')
    assert len(view.talents.nodes) == 6


@pytest.mark.parametrize('privacy', ['gear', 'hidden', 'sharing'])
def test_owner_privacy_withdraws_cached_talents_and_pending_replies(privacy):
    net = network()
    mira, thora = net.clients['Mira'], net.clients['Thora']
    thora.eval('WoWStatusTalents.request')('Mira-TestRealm')
    net.advance(30)
    assert talent_snapshot(thora) is not None
    if privacy == 'gear':
        mira.execute('character().settings.fields.gear=false; WoWStatusEquipmentSync.privacyChanged()')
    elif privacy == 'hidden':
        mira.eval('WoWStatusRoster.setHidden')(mira.eval('character()'), True)
    else:
        mira.eval('WoWStatusRoster.setSharing')(False)
    net.advance(40)
    assert talent_snapshot(thora) is None
    assert not thora.eval('WoWStatusTalents.waiting')('Mira-TestRealm')


def test_bad_or_unsolicited_talent_parts_and_oversized_builds_are_refused():
    net = network()
    thora = net.clients['Thora']
    group = thora.eval('(next(character().group_ids))')
    pid = net.clients['Mira'].eval('WoWStatusDB.roster.id')
    assert not thora.eval('WoWStatusRoster.receive')(f'B {group} {pid} D deadbeef 1 1 1793000000 bad', 'Mira-TestRealm', 'WHISPER')
    decode = thora.eval('WoWStatusTalents.decode')
    for text in ('bad', 'x'*20000, '1|classic|1|0|24|41726d73|1,0,icon,0,0,9,1,1,0,|'):
        assert decode(text) is None


def test_an_unavailable_reply_does_not_block_an_older_valid_capture():
    net = network()
    mira, thora = net.clients['Mira'], net.clients['Thora']
    mira.execute('__saved_build=character().talent_profile; character().talent_profile=nil; GetNumTalentTabs=function() return nil end')
    assert thora.eval('WoWStatusTalents.request')('Mira-TestRealm')
    net.advance(35)
    assert talent_snapshot(thora) is None
    assert thora.eval('select(2,WoWStatusTalents.get("Mira-TestRealm"))') == 'unavailable'
    mira.execute('character().talent_profile=__saved_build')
    assert thora.eval('WoWStatusTalents.request')('Mira-TestRealm')
    net.advance(35)
    assert talent_snapshot(thora).at == mira.eval('__saved_build.at')


def test_four_large_builds_finish_with_the_slower_instance_budget():
    net = Network('Mira', 'Thora', 'Bob', 'Ada', 'Eldrin')
    mira = net.clients['Mira']
    mira.execute(CLASSIC + """
        local build={mode="modern",class=1,spec=0,level=24,labels={"Arms"},nodes={},edges={}}
        for id=1,280 do
            build.nodes[id]={id=id,spell=90000+id,icon="132400",x=id,y=id,
                rank=1,max=1,tree=1,spent=1,name=""}
        end
        build.at=WoWStatusSafe.now();build.encoded=WoWStatusTalents.encode(build)
        assert(WoWStatusTalents.decode(build.encoded))
        character().talent_profile=build
        GetNumTalentTabs=function() return nil end
        function IsInInstance() return true end
    """)
    net.advance(80)
    for name, lua in net.clients.items():
        if name != 'Mira':
            assert lua.eval('WoWStatusTalents.request')('Mira-TestRealm')
    net.advance(1000)
    for name, lua in net.clients.items():
        if name != 'Mira':
            assert len(talent_snapshot(lua).nodes) == 280
