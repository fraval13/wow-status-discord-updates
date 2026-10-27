import copy
import time

import pytest

from wow_status.store import Store


@pytest.fixture
def payload():
    now = int(time.time())
    return {
        'version': 1,
        'identity': {'guid': 'Player-123-0001', 'name': 'Thora', 'realm': 'Test Realm',
                     'client': 'classic-era'},
        'settings': {'enabled': True, 'introduction_confirmed': True,
                     'fields': {'level': True, 'class': True, 'race': True},
                     'announcements': {'introduction': True, 'level': True, 'loot': True},
                     'loot_quality': 4, 'level_interval': 10},
        'snapshot': {'level': 10, 'class': 'Warrior', 'race': 'Dwarf', 'zone': 'PRIVATE'},
        'exported_at': now,
        'events': [{'id': 'intro-1', 'kind': 'introduction', 'at': now, 'data': {}},
                   {'id': 'level-10', 'kind': 'level', 'at': now, 'data': {'level': 10}}],
    }


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / 'service.sqlite3')
    yield value
    value.close()


@pytest.fixture
def clone():
    return copy.deepcopy
