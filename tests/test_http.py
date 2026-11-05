import logging

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from wow_status.server import create_app


async def test_authenticated_pipeline_privacy_and_replay(store, payload):
    client = TestClient(TestServer(create_app(store)))
    await client.start_server()
    try:
        assert (await client.post('/v1/upload', json=payload)).status == 401
        code = store.create_link('12345')
        response = await client.post('/v1/link', json={'code': code})
        token = (await response.json())['token']
        headers = {'Authorization': 'Bearer ' + token}
        response = await client.post('/v1/upload', json=payload, headers=headers)
        assert response.status == 200
        assert (await response.json())['accepted'] == 2
        response = await client.post('/v1/upload', json=payload, headers=headers)
        assert (await response.json())['accepted'] == 0
        assert 'zone' not in store.characters()[0]['snapshot']
        store.delete('12345')
        assert (await client.post('/v1/upload', json=payload, headers=headers)).status == 401
    finally:
        await client.close()


async def test_body_limit_and_expired_code(store):
    client = TestClient(TestServer(create_app(store)))
    await client.start_server()
    try:
        response = await client.post('/v1/link', json={'code': 'not-real'})
        assert response.status == 400
        response = await client.post('/v1/link', data='x' * 256_001,
                                     headers={'Content-Type': 'application/json'})
        assert response.status == web.HTTPRequestEntityTooLarge.status_code
    finally:
        await client.close()


# #26: the guards below had no tests.
NAME = 'Weekend Crew'


def group_app(store, name=NAME):
    from wow_status.group_routing import group_key
    return create_app(store, group_key(NAME), name)


def test_a_database_stays_bound_to_its_first_group_and_name(store):
    from wow_status.group_routing import group_key
    group = group_key(NAME)
    group_app(store)
    group_app(store)  # The same group and name again: a restart.
    group_app(store, NAME.upper())  # Names are case-insensitive.
    with pytest.raises(ValueError, match='separate database for each group'):
        create_app(store, group_key('Other Crew'))
    with pytest.raises(ValueError, match='does not match group key'):
        create_app(store, group, 'Other Crew')
    # Only a database whose stored name differs reaches the collision guard: one key
    # can't come from two canonical names here, so the stored name is changed directly.
    with store.db:
        store.db.execute("UPDATE meta SET value='Weekend Crew 2' WHERE key='active_group_name'")
    with pytest.raises(ValueError, match='Group name collision'):
        group_app(store)
    assert store.db.execute("SELECT value FROM meta WHERE key='active_group_id'").fetchone()[0] == group


async def started(app):
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


async def test_enrollment_needs_the_right_group_header_id_and_name(store):
    from wow_status.group_routing import group_key
    group = group_key(NAME)
    client = await started(group_app(store))
    try:
        right = {'group_id': group, 'group_name': NAME}
        for headers, body, status in [
                ({}, right, 403),
                ({'X-WoW-Group': group_key('Other Crew')}, right, 403),
                ({'X-WoW-Group': group}, dict(right, group_id=group_key('Other Crew')), 400),
                ({'X-WoW-Group': group}, ['not', 'an', 'object'], 400),
                ({'X-WoW-Group': group}, dict(right, group_name='Other Crew'), 403),
                ({'X-WoW-Group': group}, dict(right, group_name='WEEKEND CREW'), 200)]:
            response = await client.post('/v1/group-enroll', json=body, headers=headers)
            assert response.status == status, (headers, body)
        # Only the last request enrolled anyone.
        assert store.db.execute('SELECT count(*) FROM installations').fetchone()[0] == 1
    finally:
        await client.close()


async def test_uploads_must_name_the_services_group(store, payload):
    from wow_status.group_routing import group_key
    group = group_key(NAME)
    client = await started(group_app(store))
    try:
        response = await client.post('/v1/group-enroll', headers={'X-WoW-Group': group},
                                     json={'group_id': group, 'group_name': NAME})
        auth = {'X-WoW-Group': group,
                'Authorization': 'Bearer ' + (await response.json())['token']}
        right = dict(payload, group_id=group, group_name=NAME)
        for headers, body, status in [
                ({'Authorization': auth['Authorization']}, right, 403),
                (auth, dict(right, group_id=group_key('Other Crew')), 400),
                (auth, {key: value for key, value in right.items() if key != 'group_id'}, 400),
                (auth, dict(right, group_name='Other Crew'), 403),
                (auth, dict(right, player_name=7), 400)]:
            response = await client.post('/v1/upload', json=body, headers=headers)
            assert response.status == status, body.get('group_id')
        assert store.characters() == []
        # Without a group name the service's own name applies.
        body = {key: value for key, value in right.items() if key != 'group_name'}
        assert (await client.post('/v1/upload', json=body, headers=auth)).status == 200
    finally:
        await client.close()


async def test_posts_must_be_json(store):
    client = await started(create_app(store))
    try:
        response = await client.post('/v1/link', data='code=abc',
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        assert response.status == 415
        assert (await client.post('/v1/link', data=b'{}')).status == 415  # No type at all.
        assert (await client.get('/health')).status == 200  # GET needs no body type.
    finally:
        await client.close()


async def test_unexpected_failures_answer_500_without_logging_the_request(store, monkeypatch,
                                                                          caplog):
    secret = 'code-that-must-not-be-logged'

    def broken(code):
        raise RuntimeError('database is locked: ' + code)

    monkeypatch.setattr(store, 'redeem', broken)
    client = await started(create_app(store))
    try:
        with caplog.at_level(logging.DEBUG):
            response = await client.post('/v1/link', json={'code': secret})
        assert response.status == 500
        assert await response.json() == {'error': 'Internal error'}
        assert 'Internal request failure' in caplog.text and secret not in caplog.text
        assert (await client.get('/health')).status == 200  # The service keeps serving.
    finally:
        await client.close()
