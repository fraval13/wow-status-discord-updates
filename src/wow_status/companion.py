"""Read only WoWStatus SavedVariables, filter, and retry from disk after restarts."""
import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from .savedvariables import MAX_BYTES, parse
from .schema import validate


def endpoint(url):
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Service URL must not contain credentials, query, or fragment')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and
            parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('HTTPS is required except on localhost')
    return url.rstrip('/')


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temp, path)
    if os.name != 'nt':
        path.chmod(0o600)


def exports(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('SavedVariables file exceeds 2 MiB')
    db = parse(raw.decode('utf-8-sig'))
    if db.get('version') != 1 or not isinstance(db.get('characters'), dict):
        raise ValueError('Unsupported addon data')
    for char in db['characters'].values():
        if not isinstance(char, dict):
            raise ValueError('Invalid character table')
        if char.get('enrolled') is not True:
            continue
        payload = dict(char, version=1)
        events = payload.get('events', {})
        if not isinstance(events, dict):
            raise ValueError('Invalid addon events')
        payload['events'] = list(events.values())
        yield validate(payload)


async def link(url, code, credentials):
    url = endpoint(url)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(url + '/v1/link', json={'code': code},
                                allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError(f'Linking failed (HTTP {response.status})')
            token = (await response.json())['token']
    atomic_json(credentials, {'url': url, 'token': token})


async def upload(paths, credentials, state, once=False, dry_run=False, interval=5):
    config = {} if dry_run else json.loads(Path(credentials).read_text())
    url = endpoint(config['url']) if config else None
    cache = {} if dry_run or not Path(state).exists() else json.loads(Path(state).read_text())
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            failed = False
            for path in paths:
                try:
                    for payload in exports(path):
                        encoded = json.dumps(payload, sort_keys=True)
                        key = hashlib.sha256((json.dumps(payload['identity'], sort_keys=True)
                                              + config.get('token', '')).encode()).hexdigest()
                        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
                        if dry_run:
                            print(json.dumps(payload, indent=2))
                            continue
                        if cache.get(key) == fingerprint:
                            continue
                        async with session.post(url + '/v1/upload', json=payload,
                            headers={'Authorization': 'Bearer ' + config['token']},
                            allow_redirects=False) as response:
                            if response.status != 200:
                                # Never log request bodies or authentication headers.
                                print(f'Upload not accepted (HTTP {response.status}); export retained.')
                                failed = True
                                continue
                            await response.read()
                        cache[key] = fingerprint
                        atomic_json(state, cache)
                        print(f'Uploaded selected character data at {int(time.time())}.')
                except (OSError, ValueError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    print(f'Upload deferred ({type(exc).__name__}); will retry from SavedVariables.')
                    failed = True
            if once or dry_run:
                return not failed
            await asyncio.sleep(max(interval, 30 if failed else interval))
