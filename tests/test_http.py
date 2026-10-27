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
