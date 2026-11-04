"""The addon keeps one random claim secret per character and exports it (#11)."""
import re

from test_addon import STUBS, make_lua

from wow_status.companion import exports

SAVE = '''function()
    local function literal(value)
        if type(value)=="table" then
            local parts={}
            for k,v in pairs(value) do parts[#parts+1]="["..literal(k).."]="..literal(v) end
            return "{"..table.concat(parts,",").."}"
        elseif type(value)=="string" then return string.format("%q",value)
        else return tostring(value) end
    end
    return "WoWStatusDB = "..literal(WoWStatusDB)
end'''


def saved(lua):
    return lua.eval(SAVE)()


def test_secret_is_generated_once_persisted_and_exported(tmp_path):
    lua = make_lua(discord_feature=True)
    secret = lua.eval('character().claim_secret')
    assert re.fullmatch('[0-9a-f]{32}', secret)
    lua.execute('character().settings.discord_enabled=true; character().discord_enrolled=true')
    lua.eval('fire')('PLAYER_LOGOUT')
    reloaded = make_lua(STUBS + saved(lua), discord_feature=True)
    assert reloaded.eval('character().claim_secret') == secret
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(saved(reloaded), encoding='utf-8')
    payloads = list(exports(path))
    assert payloads and {payload['claim_secret'] for payload in payloads} == {secret}


def test_every_saved_character_gets_its_own_secret_and_bad_ones_are_replaced():
    lua = make_lua()
    first = lua.eval('character().claim_secret')
    lua.execute('''
        local other=WoWStatusHistory.copy(character())
        other.identity.guid="Player-other"; other.claim_secret="NOT-A-SECRET"
        WoWStatusDB.characters.other=other
        local alt=WoWStatusHistory.copy(character())
        alt.identity.guid="Player-alt"; alt.claim_secret=nil
        WoWStatusDB.characters.alt=alt
    ''')
    reloaded = make_lua(STUBS + saved(lua))
    secrets = {guid: reloaded.eval(f'''function()
        for _, c in pairs(WoWStatusDB.characters) do
            if c.identity.guid == "{guid}" then return c.claim_secret end
        end
    end''')() for guid in ('Player-123-0001', 'Player-other', 'Player-alt')}
    assert secrets.pop('Player-123-0001') == first
    for value in secrets.values():
        assert re.fullmatch('[0-9a-f]{32}', value)
    assert len({first, *secrets.values()}) == 3


def test_secret_is_never_sent_in_game():
    lua = make_lua()
    secret = lua.eval('character().claim_secret')
    lua.execute('WoWStatusGroups.update("Crew", "Frank")')
    lua.eval('clickSharing')()
    lua.eval('fire')('PLAYER_LEVEL_UP', 10)
    texts = [lua.eval(f'__sent[{index}].text') for index in range(1, lua.eval('#__sent') + 1)]
    assert texts
    assert not any(secret in text for text in texts)
