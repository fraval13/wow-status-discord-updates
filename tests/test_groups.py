import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from wow_status.archive import character_document
from wow_status.group_routing import for_group, group_key, memberships, withdrawal
from wow_status.schema import ValidationError
from wow_status.server import create_app
from wow_status.store import Store


def routed(payload, clone):
    value = clone(payload)
    first, second = group_key('Weekend Crew'), group_key('Old friends #2')
    value['_groups'] = {
        first: {'label': 'Weekend Crew', 'joined_at': value['exported_at'] - 10},
        second: {'label': 'Old friends #2', 'joined_at': value['exported_at'] - 10}}
    value['_player_name'] = 'Frank'
    value['_event_targets'] = {event['id']: [first] for event in value['events']}
    return value, first, second


def test_group_names_are_free_text_and_exact():
    assert len(group_key('Weekend Crew')) == 22
    assert group_key('  Weekend Crew  ') == group_key('Weekend Crew')
    assert group_key('Weekend Crew') == group_key('weekend crew')
    assert group_key('RONKALOT') == group_key('ronkalot')
    assert group_key('NavSquad') == group_key('navsquad')
    assert group_key('ÆRLIG GJENG') == group_key('ærlig gjeng')
    assert len(group_key('Ærlig gjeng! 🎮')) == 22
    with pytest.raises(ValidationError):
        group_key('line\nbreak')


def test_only_selected_event_targets_are_sent_and_other_ids_stay_private(payload, clone):
    source, first, second = routed(payload, clone)
    one, two = for_group(source, first), for_group(source, second)
    assert any(e['kind'] == 'level' for e in one['events'])
    assert not any(e['kind'] == 'level' for e in two['events'])
    assert second not in json.dumps(one)
    assert first not in json.dumps(two)
    assert '_groups' not in one and '_event_targets' not in one
    source['_groups'][first]['joined_at'] = source['exported_at'] + 1
    assert not any(e['kind'] == 'level' for e in for_group(source, first)['events'])
    paused = withdrawal(source, first)
    assert paused['settings']['enabled'] is False and paused['events'] == []


def test_membership_labels_must_match_their_routing_key(payload):
    key = group_key('Weekend Crew')
    assert memberships({key: {'label': 'Weekend Crew', 'joined_at': payload['exported_at']}},
                       payload['exported_at'])[key]['label'] == 'Weekend Crew'
    with pytest.raises(ValidationError):
        memberships({key: {'label': 'Wrong group', 'joined_at': payload['exported_at']}},
                    payload['exported_at'])


async def test_two_group_services_keep_tokens_and_data_isolated(tmp_path, payload, clone):
    source, first, second = routed(payload, clone)
    a, b = Store(tmp_path / 'a.sqlite3'), Store(tmp_path / 'b.sqlite3')
    ca = TestClient(TestServer(create_app(a, first, 'Weekend Crew')))
    cb = TestClient(TestServer(create_app(b, second, 'Old friends #2')))
    await ca.start_server()
    await cb.start_server()
    try:
        response = await ca.post('/v1/group-enroll',
            json={'group_id': first, 'group_name': 'Weekend Crew', 'player_name': 'Frank'},
            headers={'X-WoW-Group': first})
        assert response.status == 200  # no /link code or Discord user ID
        token = (await response.json())['token']
        headers = {'X-WoW-Group': first, 'Authorization': 'Bearer ' + token}
        assert (await ca.post('/v1/upload', json=for_group(source, first), headers=headers)).status == 200
        assert a.characters() and not b.characters()
        assert (await cb.post('/v1/upload', json=for_group(source, second),
            headers={'X-WoW-Group': second, 'Authorization': 'Bearer ' + token})).status == 401
        assert (await ca.post('/v1/upload', json=for_group(source, first),
            headers={'X-WoW-Group': second, 'Authorization': 'Bearer ' + token})).status == 403
        document = character_document(a, a.characters()[0]['id'])
        assert document['group_name'] == 'Weekend Crew'
        assert second not in json.dumps(document)
        assert document['character']['discord_owner_id'] is None
        assert document['character']['friend']['name_source'] == 'addon'
        assert (await ca.post('/v1/privacy', json={'action': 'pause'}, headers=headers)).status == 200
        assert (await ca.post('/v1/upload', json=for_group(source, first), headers=headers)).status == 403
        assert (await ca.post('/v1/privacy', json={'action': 'resume'}, headers=headers)).status == 200
        assert (await ca.post('/v1/privacy', json={'action': 'delete'}, headers=headers)).status == 200
        assert a.characters() == [] and a.owner(token) is None
    finally:
        await ca.close()
        await cb.close()
        a.close()
        b.close()


class Response:
    def __init__(self, status=200, body=None):
        self.status, self.body = status, body or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return self.body

    async def read(self):
        return b'{}'


class RecordingSession:
    def __init__(self, failed_key=None):
        self.requests, self.failed_key = [], failed_key

    def post(self, url, json, headers, allow_redirects):
        import aiohttp
        assert allow_redirects is False
        self.requests.append((url, json, headers))
        if self.failed_key and '/groups/' + self.failed_key + '/' in url:
            raise aiohttp.ClientConnectionError('offline')
        if url.endswith('/v1/group-enroll'):
            key = headers['X-WoW-Group']
            return Response(body={'token': 'private-token-' + key, 'owner': 'group:' + key})
        return Response()


async def test_automatic_group_routes_and_removal_do_not_cross_post(tmp_path, payload, clone):
    from wow_status.group_client import GroupUploader
    source, first, second = routed(payload, clone)
    config = {'mode': 'groups', 'url': 'https://example.com', 'groups': {}}
    cache, session = {}, RecordingSession()
    uploader = GroupUploader(config, tmp_path / 'credentials.json', cache,
                             tmp_path / 'upload-state.json', session, lambda **values: None)
    assert await uploader.upload(source)
    uploads = [r for r in session.requests if r[0].endswith('/v1/upload')]
    assert len(uploads) == 2
    for url, body, headers in uploads:
        target = headers['X-WoW-Group']
        assert body['group_id'] == target and '/groups/' + target + '/' in url
        other = second if target == first else first
        assert other not in json.dumps(body)
        assert headers['Authorization'] == 'Bearer private-token-' + target
    assert 'private-token-' not in json.dumps(cache)
    source['_groups'].pop(first)
    session.requests.clear()
    assert await uploader.upload(source)
    withdrawal_requests = [r for r in session.requests
                           if r[1].get('group_id') == first and r[1].get('settings', {}).get('enabled') is False]
    assert len(withdrawal_requests) == 1
    assert first not in next(iter(cache['_memberships'].values()))


async def test_one_offline_group_does_not_stop_the_other_selected_group(tmp_path, payload, clone):
    from wow_status.group_client import GroupUploader
    source, first, second = routed(payload, clone)
    session = RecordingSession(failed_key=first)
    uploader = GroupUploader({'mode': 'groups', 'url': 'https://example.com', 'groups': {}},
        tmp_path / 'credentials.json', {}, tmp_path / 'upload-state.json', session, lambda **values: None)
    assert await uploader.upload(source) is False
    assert any(url.endswith('/v1/upload') and body.get('group_id') == second
               for url, body, headers in session.requests)


async def test_discord_opt_out_withdraws_known_groups_without_enrolling_new_ones(tmp_path, payload, clone):
    from wow_status.group_client import GroupUploader, identity_key
    source, first, second = routed(payload, clone)
    source['_discord_opt_out'] = True
    source['settings']['enabled'] = False
    config = {'mode': 'groups', 'url': 'https://example.com', 'groups': {
        first: {'token': 'existing-token', 'url': 'https://example.com/groups/' + first}}}
    cache = {'_memberships': {identity_key(source): {first: {'joined_at': source['exported_at']}}}}
    session = RecordingSession()
    uploader = GroupUploader(config, tmp_path / 'credentials.json', cache,
                             tmp_path / 'state.json', session, lambda **values: None)
    assert await uploader.upload(source)
    assert len(session.requests) == 1
    url, body, _ = session.requests[0]
    assert url.endswith('/groups/' + first + '/v1/upload')
    assert body['settings']['enabled'] is False
    assert body['events'] == [] and body['snapshot'] == {}
    assert second not in config['groups']
