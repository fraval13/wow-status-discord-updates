"""A malformed SavedVariables file is skipped and retried; it never stops the companion loop."""
import asyncio
import copy
import json
import time
from pathlib import Path

import pytest

from wow_status import companion
from wow_status.companion import exports, upload
from wow_status.schema import ValidationError, validate

FIXTURE = (Path(__file__).parent / 'fixtures/WoWStatus.lua').read_text(encoding='utf-8')
# The issue's two reproductions: a history event that is a string, and a table-valued client.
EVENTS_OOPS = FIXTURE.replace('["exported_at"] = 1793000000,',
                              '["exported_at"] = 1793000000, history = { events = { "oops" } },')
CLIENT_TABLE = FIXTURE.replace('client="classic-era"', 'client={}')


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return path


def test_issue_fixtures_are_rejected_as_value_errors(tmp_path):
    with pytest.raises(ValueError):
        list(exports(write(tmp_path, 'oops.lua', EVENTS_OOPS)))
    with pytest.raises(ValidationError):
        list(exports(write(tmp_path, 'client.lua', CLIENT_TABLE)))


@pytest.mark.parametrize('source', [EVENTS_OOPS, CLIENT_TABLE], ids=['events-oops', 'client-table'])
def test_dry_run_reports_failure_without_raising(tmp_path, capsys, source):
    path = write(tmp_path, 'WoWStatus.lua', source)
    assert asyncio.run(upload([path], None, None, once=True, dry_run=True)) is False
    assert 'Skipped unreadable SavedVariables' in capsys.readouterr().out


def test_malformed_file_does_not_block_other_files(tmp_path, capsys):
    bad = write(tmp_path, 'bad.lua', EVENTS_OOPS)
    good = write(tmp_path, 'good.lua', FIXTURE)
    assert asyncio.run(upload([bad, good], None, None, once=True, dry_run=True)) is False
    output = capsys.readouterr().out
    assert 'Skipped unreadable SavedVariables' in output
    assert '"name": "Thora"' in output


@pytest.mark.parametrize('error', [AttributeError, TypeError, KeyError, RecursionError])
def test_any_parse_error_is_contained(tmp_path, monkeypatch, error):
    def broken(path):
        raise error('boom')
        yield  # pragma: no cover

    monkeypatch.setattr(companion, 'exports', broken)
    path = write(tmp_path, 'WoWStatus.lua', FIXTURE)
    assert asyncio.run(upload([path], None, None, once=True, dry_run=True)) is False


class _Response:
    status = 200
    headers = {}

    async def read(self):
        return b''


class _Request:
    async def __aenter__(self):
        return _Response()

    async def __aexit__(self, *exc):
        return False


def test_loop_retries_the_file_after_it_is_fixed(tmp_path, monkeypatch, capsys):
    path = write(tmp_path, 'WoWStatus.lua', EVENTS_OOPS)
    credentials = tmp_path / 'credentials.json'
    credentials.write_text(json.dumps({'url': 'https://example.test', 'token': 't'}), encoding='utf-8')
    posted = []

    class Session:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, **kwargs):
            posted.append(kwargs['json'])
            return _Request()

    async def run():
        stop = asyncio.Event()

        async def sleep(seconds):
            # The addon rewrites SavedVariables on the next /reload or logout.
            path.write_text(FIXTURE, encoding='utf-8')
            if posted:
                stop.set()

        monkeypatch.setattr(companion.asyncio, 'sleep', sleep)
        return await upload([path], credentials, tmp_path / 'state.json', interval=1, stop_event=stop)

    monkeypatch.setattr(companion.aiohttp, 'ClientSession', Session)
    assert asyncio.run(run()) is True
    assert 'Skipped unreadable SavedVariables' in capsys.readouterr().out
    assert len(posted) == 1 and posted[0]['identity']['name'] == 'Thora'


@pytest.mark.parametrize('path,value', [
    (('identity', 'client'), {}),
    (('identity', 'client'), []),
    (('events', 0, 'kind'), {}),
])
def test_unhashable_required_values_raise_validation_error(payload, path, value):
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        validate(payload)


def test_unhashable_optional_values_are_dropped(payload):
    payload['settings']['fields']['professions'] = True
    payload['snapshot']['class_id'] = []
    payload['snapshot']['professions'] = [{'name': 'Mining', 'key': {}}]
    result = validate(payload)
    assert 'class_id' not in result['snapshot']
    assert result['snapshot']['professions'] == [{'name': 'Mining', 'source': 'player_entered'}]


def _rich_payload():
    now = int(time.time())
    every = {key: True for key in ('level', 'class', 'race', 'faction', 'guild', 'gear', 'zone',
                                   'playtime', 'professions', 'deaths', 'quests')}
    kinds = {key: True for key in ('introduction', 'level', 'loot', 'equipment', 'death', 'zone',
                                   'quest', 'profession', 'status', 'dungeon', 'mount', 'pvp')}
    return {
        'version': 1, 'upload_batch': 'a' * 64, 'upload_part': 1, 'upload_parts': 1,
        'identity': {'guid': 'Player-1', 'name': 'Thora', 'realm': 'Realm', 'client': 'classic-era',
                     'build': '1.15', 'interface': 11500},
        'settings': {'enabled': True, 'introduction_confirmed': True, 'fields': every,
                     'collection': kinds, 'announcements': kinds, 'discord_delivery': 'summary',
                     'character_role': 'main', 'loot_quality': 3, 'level_interval': 5},
        'exported_at': now,
        'snapshot': {'level': 10, 'class': 'Warrior', 'class_id': 'WARRIOR', 'race': 'Dwarf',
                     'sex': 'Male', 'faction': 'Alliance', 'guild': 'Guild', 'zone': 'Dun Morogh',
                     'gear': {'1': 'item:1'}, 'playtime': 10, 'playtime_recorded_at': now,
                     'professions': [{'name': 'Mining', 'key': 'mining', 'skill': 1, 'max_skill': 75}],
                     'deaths': 1, 'deaths_since': now, 'xp_current': 1, 'xp_max': 10,
                     'quests_completed': 1, 'quests_source': 'game_api', 'quests_since': now},
        'events': [
            {'id': 'a', 'kind': 'level', 'at': now, 'data': {'level': 10, 'zone': 'Z', 'played_level_seconds': 1}},
            {'id': 'b', 'kind': 'loot', 'at': now, 'data': {'quality': 4, 'item': 'item:1'}},
            {'id': 'c', 'kind': 'equipment', 'at': now, 'data': {'quality': 4, 'item': 'item:1'}},
            {'id': 'd', 'kind': 'death', 'at': now, 'data': {'total_deaths': 2}},
            {'id': 'e', 'kind': 'quest', 'at': now, 'data': {'completed': 100, 'source': 'game_api'}},
            {'id': 'f', 'kind': 'profession', 'at': now, 'data': {'name': 'Mining', 'skill': 1,
                                                                   'max_skill': 75, 'title': 'Apprentice'}},
            {'id': 'g', 'kind': 'status', 'at': now, 'data': {'changed': ['level']}},
            {'id': 'h', 'kind': 'dungeon', 'at': now, 'data': {'source': 'game_api', 'text': 'x',
                                                                'instance_id': 1, 'name': 'Deadmines'}},
            {'id': 'i', 'kind': 'pvp', 'at': now, 'data': {'text': 'x', 'rank': 1}},
            {'id': 'j', 'kind': 'zone', 'at': now, 'data': {'zone': 'Z'}},
        ],
        'tracking': {'observed_until': now, 'points': [
            {'kind': 'level', 'level': 10, 'at': now, 'segment': 's', 'event_id': 'a'}]},
    }


def _paths(value, prefix=()):
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = enumerate(value)
    else:
        return
    for key, child in items:
        yield prefix + (key,)
        yield from _paths(child, prefix + (key,))


def test_rich_payload_is_valid():
    result = validate(_rich_payload())
    assert len(result['events']) == 10 and result['tracking']['points']


@pytest.mark.parametrize('replacement', [{}, [], 'x', None, 1.5, True, -1],
                         ids=['table', 'list', 'text', 'nil', 'float', 'bool', 'negative'])
def test_wrong_type_anywhere_only_raises_validation_error(replacement):
    base = _rich_payload()
    for path in _paths(base):
        mutated = copy.deepcopy(base)
        target = mutated
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = copy.deepcopy(replacement)
        try:
            validate(mutated)
        except ValidationError:
            pass
        except Exception as exc:  # pragma: no cover - the failure message names the path
            pytest.fail(f'{path} = {replacement!r} raised {type(exc).__name__}: {exc}')
