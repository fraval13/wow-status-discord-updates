"""ID-only group onboarding with private per-installation upload credentials."""
import asyncio
import json
import time
from pathlib import Path

import aiohttp

from .companion import atomic_json, endpoint
from .group_routing import for_group, withdrawal


def configure(url, credentials):
    url = endpoint(url)
    path = Path(credentials)
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if old.get('groups') and old.get('url') != url:
        raise ValueError('Existing group credentials belong to another service; preserve them and use a separate credentials file')
    config = old if old.get('url') == url and old.get('mode') == 'groups' else {'groups': {}}
    config.update(url=url, mode='groups')
    atomic_json(path, config)


def identity_key(payload):
    identity = payload['identity']
    return json.dumps([identity['client'], identity['realm'], identity['guid']])


class GroupUploader:
    def __init__(self, config, credentials, cache, state, session, status):
        self.config, self.credentials, self.cache, self.state = config, credentials, cache, state
        self.session, self.status = session, status
        self.failed = False

    async def route(self, target, player_name, label):
        routes = self.config.setdefault('groups', {})
        route = routes.get(target)
        if route and route.get('blocked'):
            self.status(connection='A selected group is paused locally. Use Resume in the companion.')
            return None
        if route and route.get('token'):
            return route
        if route and route.get('retry_enroll_at', 0) > time.time():
            self.failed = True
            self.status(connection='Enrollment is temporarily limited; retained data will retry automatically.')
            return None
        url = endpoint(self.config['url']) + '/groups/' + target
        async with self.session.post(url + '/v1/group-enroll',
            json={'group_id': target, 'group_name': label, 'player_name': player_name},
            headers={'X-WoW-Group': target}, allow_redirects=False) as response:
            if response.status == 429:
                from .companion import retry_seconds
                routes[target] = dict(route or {}, retry_enroll_at=time.time() + retry_seconds(response))
                atomic_json(self.credentials, self.config)
            if response.status != 200:
                self.status(connection=f'Group enrollment rejected (HTTP {response.status}); check the selected ID.')
                self.failed = True
                return None
            body = await response.json()
        route = {'label': label, 'url': url, 'token': body['token'], 'owner': body['owner'], 'blocked': False,
                 'min_joined_at': route.get('min_joined_at', 0) if route else 0}
        routes[target] = route
        atomic_json(self.credentials, self.config)
        return route

    async def send(self, target, route, payload, fingerprint_key=None):
        import hashlib
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if fingerprint_key and self.cache.get(fingerprint_key) == fingerprint:
            return True
        if payload['settings']['enabled'] and route.get('retry_upload_at', 0) > time.time():
            self.failed = True
            self.status(connection='Uploads are temporarily limited; retained data will retry automatically.')
            return False
        async with self.session.post(route['url'] + '/v1/upload', json=payload,
            headers={'Authorization': 'Bearer ' + route['token'], 'X-WoW-Group': target},
            allow_redirects=False) as response:
            if response.status == 429:
                from .companion import retry_seconds
                route['retry_upload_at'] = time.time() + retry_seconds(response)
                atomic_json(self.credentials, self.config)
            if response.status != 200:
                self.failed = True
                self.status(connection=f'Group upload rejected (HTTP {response.status}); data remains local.')
                return False
            await response.read()
        route.pop('retry_upload_at', None)
        atomic_json(self.credentials, self.config)
        if fingerprint_key:
            self.cache[fingerprint_key] = fingerprint
        atomic_json(self.state, self.cache)
        self.status(connection='Selected group upload accepted', last_upload=int(time.time()))
        return True

    async def upload(self, payload):
        key = identity_key(payload)
        known = self.cache.setdefault('_memberships', {}).setdefault(key, {})
        selected = payload.get('_groups', {})
        # Withdraw from removed groups, even though they are no longer selected.
        for target in list(known):
            if target in selected:
                continue
            try:
                route = self.config.get('groups', {}).get(target)
                if route and route.get('blocked'):
                    del known[target]  # remote privacy pause already scrubbed and stopped this owner
                elif route and route.get('token') and await self.send(target, route, withdrawal(payload, target)):
                    del known[target]
                else:
                    self.failed = True
                    self.status(connection='A removed group still needs its withdrawal uploaded; keep the companion running.')
            except (OSError, ValueError, aiohttp.ClientError, asyncio.TimeoutError):
                self.failed = True
                self.status(connection='Withdrawal is deferred; other group destinations continue.')
        if not selected:
            self.status(connection='No group IDs selected; this character is not routed anywhere.')
        for target in selected:
            try:
                route = await self.route(target, payload.get('_player_name', ''), selected[target]['label'])
                if not route:
                    continue
                known[target] = {'joined_at': selected[target]['joined_at']}
                atomic_json(self.state, self.cache)
                minimum = route.get('min_joined_at', 0)
                if payload['exported_at'] < minimum:
                    self.status(connection='Run /reload to export current data after resuming this group.')
                    continue
                scoped = for_group(payload, target, minimum)
                first = scoped['events'][0]['id'] if scoped['events'] else ':snapshot'
                cache_key = 'group:' + target + ':' + route['token'] + ':' + key + ':' + first
                # Hash keys so upload-state files never contain bearer credentials.
                import hashlib
                cache_key = hashlib.sha256(cache_key.encode()).hexdigest()
                if await self.send(target, route, scoped, cache_key):
                    known[target] = {'joined_at': selected[target]['joined_at']}
            except (OSError, ValueError, aiohttp.ClientError, asyncio.TimeoutError):
                self.failed = True
                self.status(connection='A group upload is deferred; other selected groups continue.')
        atomic_json(self.state, self.cache)
        if self.failed:
            self.status(connection='Some group updates are pending; accepted destinations continue independently.')
        return not self.failed


async def privacy_action(credentials, target, action):
    import aiohttp
    path = Path(credentials)
    config = json.loads(path.read_text(encoding='utf-8'))
    route = config.get('groups', {}).get(target)
    if not route or action not in ('pause', 'resume', 'delete'):
        raise ValueError('Choose an existing group and privacy action')
    if not route.get('token'):
        if action == 'resume':
            route['blocked'] = False
            route['min_joined_at'] = int(time.time())
            atomic_json(path, config)
            return
        raise ValueError('This group has already been deleted locally')
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(route['url'] + '/v1/privacy', json={'action': action},
            headers={'Authorization': 'Bearer ' + route['token'], 'X-WoW-Group': target},
            allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError('Privacy action was not accepted; keep credentials to retry')
    route['blocked'] = action in ('pause', 'delete')
    if action in ('pause', 'resume', 'delete'):
        route['min_joined_at'] = int(time.time())
    if action == 'delete':
        route.pop('token', None)
        route.pop('owner', None)
    atomic_json(path, config)
