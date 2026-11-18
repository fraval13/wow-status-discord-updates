"""Numbered saved-data migrations and the option schema (#231)."""
from pathlib import Path

import pytest
from test_addon import STUBS, make_lua

from wow_status.companion import load
from wow_status.savedvariables import parse

ROOT = Path(__file__).resolve().parents[1]
# Saved by the release before migrations existed (see the file's header).
V1 = (ROOT / 'tests/fixtures/WoWStatusDB-v1.lua').read_text(encoding='utf-8')
KEY = 'classic-era:Test Realm:Player-123-0001'


def plain(value):
    """A Lua table as nested Python dicts (keys as they are), other values unchanged."""
    if hasattr(value, 'items'):
        return {key: plain(item) for key, item in value.items()}
    return value


def is_list(value):
    return isinstance(value, dict) and list(value) == list(range(1, len(value) + 1))


def differences(before, after, path=()):
    """Paths whose value changed or vanished between before and after; additions are fine."""
    if is_list(before) and is_list(after) and before:
        # Logs gain entries at the front; every saved entry must still be there.
        return [path + (index,) for index, item in before.items() if item not in after.values()]
    if isinstance(before, dict) and isinstance(after, dict):
        found = []
        for key, value in before.items():
            if key not in after:
                found.append(path + (key,))
            else:
                found += differences(value, after[key], path + (key,))
        return found
    return [] if before == after else [path]


def login(saved=V1, extra=''):
    return make_lua(stubs=STUBS + saved + extra + '''
        __level=2
        __now=1793000600
        function time() return math.floor(__now) end
    ''')


# The fixture's data from the current release ---------------------------------

def test_release_data_loads_unchanged_and_keeps_its_options():
    lua = login()
    before = plain(parse(V1))
    after = plain(lua.eval('WoWStatusDB'))
    # Only what every login rewrites anyway may differ: stamps of this login and
    # the play session it starts. Nothing the player chose or recorded changes.
    character = ('characters', KEY)
    login_time = {character + ('exported_at',), character + ('equipment_profile', 'at'),
                  character + ('roster_info', 'at'), character + ('history', 'tracking', 'observed_until'),
                  ('popups', 'last_send'), ('journal', 'request_serial'),
                  ('whats_new_seen',)}  # Moves on with every release.
    changed = {path for path in differences(before, after)
               if not any(path[:len(stamp)] == stamp for stamp in login_time)
               and path[:3] != character + ('session',)}
    assert changed == set(), changed
    # Progress is kept beside version, which older releases require to stay 1.
    assert lua.eval('WoWStatusDB.version') == 1
    assert after['version'] == 1 and after['schema_version'] == 3
    assert after['characters'][KEY]['schema_version'] == 4
    assert after['characters'][KEY]['events'] == before['characters'][KEY]['events']
    assert lua.execute('''
        local P = WoWStatusPopups
        assert(P.duration() == 12 and not P.options().big_banners)
        local hours = P.quietHours()
        assert(hours.enabled and hours.start == 1380 and hours.stop == 360)
        local c = WoWStatusDB.characters[{KEY!r}]
        assert(WoWStatusSettings.get("loot_quality", c) == 4)
        assert(WoWStatusSettings.get("level_interval", c) == 5)
        return true
    '''.replace('{KEY!r}', repr(KEY))) is True


def test_second_login_runs_no_step_again():
    lua = login(extra='''
        __runs = 0
    ''')
    lua.execute('''
        local function count(steps)
            for _, step in ipairs(steps) do
                local run = step.run
                step.run = function(...) __runs = __runs + 1; return run(...) end
            end
        end
        count(WoWStatusMigrations.account); count(WoWStatusMigrations.character)
        assert(WoWStatusMigrations.upgradeAccount(WoWStatusDB))
        assert(WoWStatusMigrations.upgradeCharacter(character(), WoWStatusDB))
        assert(__runs == 0)
    ''')


def test_brand_new_account_starts_at_the_latest_versions():
    lua = make_lua()
    assert lua.eval('WoWStatusDB.schema_version') == lua.eval('WoWStatusMigrations.ACCOUNT_LATEST') == 3
    assert lua.eval('WoWStatusDB.version') == 1
    assert lua.eval('character().schema_version') == lua.eval('WoWStatusMigrations.CHARACTER_LATEST') == 4
    # A new character still gets every switch a migrated one has.
    assert lua.eval('character().settings.in_game.pvp') is True
    assert lua.eval('character().settings.collection.reputation') is True
    assert lua.eval('character().settings.in_game.recap') is False


def test_newer_saved_data_is_used_and_never_downgraded():
    lua = login(V1.replace('\n    version = 1,\n', '\n    schema_version = 99,\n    version = 1,\n'))
    assert lua.eval('WoWStatusDB.schema_version') == 99
    assert lua.eval('WoWStatusPopups.duration()') == 12
    assert lua.eval('character() ~= nil')


@pytest.mark.parametrize('broken', ['nil', '"two"', '0', '1.5', '-3', '1/0', '1e300 * 1e300', '0/0'])
def test_missing_or_broken_version_counts_as_one(broken):
    lua = login(V1.replace('\n    version = 1,\n', f'\n    schema_version = {broken},\n    version = 1,\n'))
    assert lua.eval('WoWStatusDB.schema_version') == 3


@pytest.mark.parametrize('saved', ['"x"', '{}', '{version = 1, characters = "x"}'])
def test_data_that_is_not_the_addons_is_left_alone_with_one_message(saved):
    lua = make_lua(STUBS + f'''
        __said = {{}}
        DEFAULT_CHAT_FRAME = {{AddMessage = function(_, text) table.insert(__said, text) end}}
        WoWStatusDB = {saved}
    ''')
    lua.execute('__before = WoWStatusDB')
    for event in ('PLAYER_ENTERING_WORLD', 'PLAYER_REGEN_ENABLED'):
        lua.eval('fire')(event)
    said = list(lua.eval('__said').values())
    assert sum('Saved data is unreadable' in text for text in said) == 1
    assert lua.eval('rawequal(WoWStatusDB, __before)') is True
    # Nothing was upgraded or started on it.
    assert lua.eval('type(WoWStatusDB) ~= "table" or (WoWStatusDB.schema_version == nil and WoWStatusDB.popups == nil)')


# The runner ---------------------------------------------------------------------

RUNNER = '''
    local M = WoWStatusMigrations
    __log = {}
    M.account = {
        {version = 2, name = "two", run = function(db) table.insert(__log, 2) end},
        {version = 3, name = "three", run = function(db) if __fail then error("broken") end table.insert(__log, 3) end},
        {version = 4, name = "four", run = function(db) table.insert(__log, 4) end},
    }
'''


def test_steps_run_in_order_once_and_save_each_version():
    lua = make_lua()
    lua.execute(RUNNER + '''
        local db = {schema_version = 1}
        assert(M.upgradeAccount(db))
        assert(table.concat(__log, ",") == "2,3,4" and db.schema_version == 4)
        assert(M.upgradeAccount(db) and #__log == 3)
        db = {schema_version = 3}; __log = {}
        assert(M.upgradeAccount(db) and table.concat(__log, ",") == "4")
    ''')


def test_text_or_broken_versions_are_saved_as_numbers():
    lua = make_lua()
    lua.execute(RUNNER + '''
        local db = {schema_version = "4"}
        assert(M.upgradeAccount(db) and db.schema_version == 4 and #__log == 0)
        db = {schema_version = 99}
        assert(M.upgradeAccount(db) and db.schema_version == 99)
    ''')


@pytest.mark.parametrize('saved', ['nil', '2', '"1"'])
def test_account_version_is_always_saved_as_one(saved):
    lua = login(V1.replace('\n    version = 1,\n', f'\n    version = {saved},\n'))
    assert lua.eval('WoWStatusDB.version') == 1 and lua.eval('character() ~= nil')


def test_failed_step_keeps_its_version_and_runs_again_next_time():
    lua = make_lua()
    lua.execute(RUNNER + '''
        local db = {schema_version = 1}
        __fail = true
        local ok, step, problem = M.upgradeAccount(db)
        assert(not ok and step.version == 3 and tostring(problem):find("broken", 1, true))
        assert(db.schema_version == 2 and table.concat(__log, ",") == "2")
        __fail = false
        assert(M.upgradeAccount(db) and db.schema_version == 4 and table.concat(__log, ",") == "2,3,4")
    ''')


def test_failed_step_is_reported_and_login_continues():
    # The account step skips a popups value that is not a table, so make reading it fail once.
    lua = make_lua(STUBS + '''
        __said = {}
        DEFAULT_CHAT_FRAME = {AddMessage = function(_, text) table.insert(__said, text) end}
        WoWStatusDB = {version = 1, characters = {}}
        setmetatable(WoWStatusDB, {__index = function(_, key)
            if key == "popups" and not __passed then __passed = true; error("unreadable") end
        end})
    ''')
    said = '\n'.join(lua.eval('__said').values())
    assert 'Could not upgrade saved data (step 2). It will be tried again later.' in said
    assert 'unreadable' in said
    assert lua.eval('WoWStatusDB.schema_version') == 1
    assert lua.eval('character() ~= nil')  # Everything else still started.


def test_failed_step_is_reported_once_while_login_waits():
    lua = make_lua(STUBS + '''
        __said, __broken, __hidden = {}, true, true
        DEFAULT_CHAT_FRAME = {AddMessage = function(_, text) table.insert(__said, text) end}
        function UnitGUID() if __hidden then return nil end return "Player-123-0001" end
        WoWStatusDB = {version = 1, characters = {}, popups = setmetatable({}, {__index = function(_, key)
            if key == "activity" and __broken then error("unreadable") end
        end})}
    ''')
    for event in ('PLAYER_ENTERING_WORLD', 'PLAYER_REGEN_ENABLED', 'PLAYER_ENTERING_WORLD'):
        lua.eval('fire')(event)
    lua.execute('__broken, __hidden = false, false')
    lua.eval('fire')('PLAYER_ENTERING_WORLD')
    said = '\n'.join(lua.eval('__said').values())
    assert said.count('Could not upgrade saved data (step 2)') == 1
    assert lua.eval('WoWStatusDB.schema_version') == 3 and lua.eval('character() ~= nil')


# Each step on its own -----------------------------------------------------------

def step(lua, kind, version):
    return lua.eval(f'''(function()
        for _, s in ipairs(WoWStatusMigrations.{kind}) do if s.version == {version} then return s.run end end
    end)()''')


def test_account_step_2_drops_retired_kinds_from_the_activity_log():
    lua = make_lua()
    lua.execute('''
        __db = {popups = {activity = {
            {kind = "level", sender = "A"}, {kind = "discovery", sender = "B"},
            {kind = "lfg", sender = "C"}, {kind = "dungeon", automatic = true, sender = "D"},
        }}}
    ''')
    step(lua, 'account', 2)(lua.eval('__db'))
    assert [item['sender'] for item in lua.eval('__db.popups.activity').values()] == ['A', 'D']
    for missing in ('{}', '{popups = {}}', '{popups = {activity = "x"}}'):
        step(lua, 'account', 2)(lua.eval(missing))  # Nothing to do, no error.


def test_character_step_2_fills_new_switches_and_keeps_choices():
    lua = make_lua()
    lua.execute('''
        __c = {enrolled = true, settings = {
            fields = {deaths = false}, collection = {quest = false},
            announcements = {}, in_game = {pvp = false, recap = true},
        }}
    ''')
    step(lua, 'character', 2)(lua.eval('__c'))
    lua.execute('''
        local s = __c.settings
        -- Legacy characters from before the Discord opt-in.
        assert(__c.discord_enrolled == true and s.discord_enabled == false)
        assert(s.fields.deaths == false and s.fields.gold == true and s.fields.collection == true)
        assert(s.collection.quest == false and s.collection.pvp == true and s.announcements.unlock == true)
        assert(s.in_game.pvp == false and s.in_game.recap == true)
        assert(s.in_game.loot == true and s.in_game.level == true and s.in_game.reputation == true)
    ''')


def test_character_step_2_leaves_a_chosen_discord_setting_alone():
    lua = make_lua()
    lua.execute('''
        __c = {enrolled = true, discord_enrolled = false, settings = {discord_enabled = true}}
    ''')
    step(lua, 'character', 2)(lua.eval('__c'))
    assert lua.eval('__c.discord_enrolled') is False
    assert lua.eval('__c.settings.discord_enabled') is True
    assert lua.eval('__c.settings.in_game.recap') is False


def test_character_step_2_stores_out_of_range_filters_clamped():
    lua = make_lua()
    lua.execute('__c = {settings = {loot_quality = 9, level_interval = "often"}}; __d = {settings = {}}')
    step(lua, 'character', 2)(lua.eval('__c'))
    step(lua, 'character', 2)(lua.eval('__d'))
    assert lua.eval('__c.settings.loot_quality') == 5
    assert dict(lua.eval('__c.settings.loot_rarities')) == {'rare': False, 'epic': False, 'legendary': True}
    assert lua.eval('__c.settings.level_interval') == 10
    assert lua.eval('__d.settings.loot_quality') is None  # Nothing added where nothing was saved.


def test_character_step_2_repairs_settings_parts_that_are_not_tables():
    lua = make_lua()
    lua.execute('__c = {settings = {fields = "x", collection = 3, in_game = false}}')
    step(lua, 'character', 2)(lua.eval('__c'))
    assert lua.eval('__c.settings.fields.deaths') is True
    assert lua.eval('__c.settings.in_game.loot') is True


# The option schema ----------------------------------------------------------------

def test_every_declared_option_is_well_formed():
    lua = make_lua()
    for entry in lua.eval('WoWStatusSettings.schema').values():
        assert entry['scope'] in ('account', 'character'), entry['key']
        assert entry['type'] in ('boolean', 'integer'), entry['key']
        assert lua.eval('WoWStatusSettings.entry')(entry['key']) is not None
        if entry['type'] == 'integer':
            assert entry['min'] <= entry['default'] <= entry['max'], entry['key']
        else:
            assert isinstance(entry['default'], bool), entry['key']
    with pytest.raises(Exception, match='Unknown WoW Status option'):
        lua.eval('WoWStatusSettings.get')('no_such_option', lua.eval('{}'))


@pytest.mark.parametrize('stored, expected', [
    ('nil', 6), ('"long"', 6), ('{}', 6), ('true', 6), ('0/0', 6), ('1/0', 6), ('-1/0', 6),
    ('999', 6), ('2', 6), ('-4', 6), ('0', 0), ('12', 12), ('"15"', 15), ('7.6', 8), ('0.3', 6),
])
def test_out_of_range_values_without_clamp_read_as_the_default(stored, expected):
    lua = make_lua()
    lua.execute(f'WoWStatusDB.popups.popup_duration = {stored}')
    assert lua.eval('WoWStatusSettings.get("popup_duration", WoWStatusDB)') == expected
    assert lua.eval('WoWStatusPopups.duration()') == expected


@pytest.mark.parametrize('stored, expected', [
    ('nil', 3), ('"bad"', 3), ('0/0', 3), ('1/0', 3), ('9', 5), ('-2', 0), ('4', 4), ('"5"', 5), ('2.5', 3),
])
def test_clamped_option_reads_as_the_nearest_bound(stored, expected):
    lua = make_lua()
    lua.execute(f'character().settings.loot_quality = {stored}')
    assert lua.eval('WoWStatusSettings.get("loot_quality", character())') == expected


def test_set_clamps_or_refuses_and_never_stores_a_bad_value():
    lua = make_lua()
    lua.execute('''
        local Z, c = WoWStatusSettings, character()
        -- Clamping option: out of range is stored as the nearest bound.
        assert(Z.set("level_interval", 500, c) and c.settings.level_interval == 100)
        assert(Z.set("level_interval", -1, c) and c.settings.level_interval == 1)
        assert(not Z.valid("level_interval", 500) and Z.valid("level_interval", 50))
        -- Fractions and other kinds are refused; the old value stays.
        assert(not Z.set("level_interval", 2.5, c) and not Z.set("level_interval", "x", c))
        assert(not Z.set("level_interval", 0/0, c) and c.settings.level_interval == 1)
        -- Non-clamping option: out of range is refused.
        assert(not Z.set("quiet_hours_start", 1440, WoWStatusDB) and not Z.set("quiet_hours_start", -1, WoWStatusDB))
        assert(Z.set("quiet_hours_start", 90, WoWStatusDB) and WoWStatusDB.popups.quiet_hours.start == 90)
        -- Booleans accept only booleans.
        assert(not Z.set("big_banners", "no", WoWStatusDB) and not Z.set("big_banners", nil, WoWStatusDB))
        assert(Z.set("big_banners", false, WoWStatusDB) and WoWStatusDB.popups.big_banners == false)
        -- A sparse option does not store its default, and missing tables are made.
        local db = {}
        assert(Z.set("popup_duration", 8, db) and db.popups.popup_duration == 8)
        assert(Z.set("popup_duration", 6, db) and db.popups.popup_duration == nil)
        assert(not Z.set("popup_duration", 8, nil))
        assert(Z.get("popup_duration", nil) == 6)
    ''')


def test_slash_filters_still_refuse_out_of_range_values():
    lua = make_lua(STUBS + '''
        __said = {}
        DEFAULT_CHAT_FRAME = {AddMessage = function(_, text) table.insert(__said, text) end}
    ''')
    lua.execute('''
        SlashCmdList.WOWSTATUS("quality 9")
        assert(__said[#__said]:find("Invalid filter value", 1, true) and character().settings.loot_quality == 3)
        SlashCmdList.WOWSTATUS("interval 2.5")
        assert(__said[#__said]:find("Invalid filter value", 1, true) and character().settings.level_interval == 10)
        SlashCmdList.WOWSTATUS("quality 5")
        assert(character().settings.loot_quality == 5 and not character().settings.loot_rarities.epic)
    ''')


# The companion still reads the saved file ----------------------------------------

def test_companion_reads_upgraded_saved_data(tmp_path):
    lua = make_lua()
    source = (ROOT / 'tests/fixtures/WoWStatus.lua').read_text(encoding='utf-8')
    path = tmp_path / 'WoWStatus.lua'
    path.write_text(source.replace('["version"] = 1,', '["version"] = 1, schema_version = 2,'), encoding='utf-8')
    db, _ = load(path)
    assert db['version'] == lua.eval('WoWStatusDB.version') == 1


def test_character_step_3_turns_achievements_off_on_retail_only():
    lua = make_lua()
    lua.execute('''
        local step = WoWStatusMigrations.character[2]
        assert(step.version == 3)
        local function fresh() return {settings = {collection = {}, announcements = {}, in_game = {achievement = true}}} end
        local c = fresh()
        step.run(c)          -- Classic: nothing is added
        assert(c.settings.collection.achievement == nil and c.settings.in_game.achievement == true)
        WoWStatusAdapter.achievements = true
        c = fresh(); step.run(c)
        assert(c.settings.collection.achievement == false and c.settings.announcements.achievement == false)
        assert(c.settings.in_game.achievement == true)   -- an existing choice is kept
        c = {settings = {}}; step.run(c)
        assert(c.settings.in_game.achievement == false)
        WoWStatusAdapter.achievements = nil
    ''')


@pytest.mark.parametrize('saved', ['nil', 'false', '"broken"', '{}', '{synthetic=true}'])
def test_listing_confirmation_migration_never_enables_or_confirms_a_group(saved):
    lua = make_lua()
    lua.execute('''
        local db={schema_version=2,listing_confirmed='''+saved+''',listed_groups={existing=true},
            account_groups={existing="Synthetic group"},unrelated={keep=true}}
        local old=db.listing_confirmed
        assert(WoWStatusMigrations.upgradeAccount(db))
        assert(db.schema_version==3 and type(db.listing_confirmed)=="table")
        if type(old)=="table" then assert(db.listing_confirmed==old)
        else assert(next(db.listing_confirmed)==nil) end
        assert(not db.listing_confirmed.existing and db.listed_groups.existing and db.unrelated.keep)
    ''')


def test_character_migration_normalizes_manual_hardcore_without_opt_in():
    lua = make_lua()
    lua.execute("""
        local step = WoWStatusMigrations.character[3]
        assert(step.version == 4)
        for _, raw in ipairs({false, "true", 1, {}}) do
            local character = {settings={manual_hardcore=raw}}
            step.run(character)
            assert(character.settings.manual_hardcore == nil)
        end
        local character = {settings={manual_hardcore=true}}
        step.run(character)
        assert(character.settings.manual_hardcore == true)
    """)
