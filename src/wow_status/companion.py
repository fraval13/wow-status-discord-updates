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
from .schema import integer, string, validate


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
        raise ValueError('SavedVariables file exceeds 32 MiB')
    db = parse(raw.decode('utf-8-sig'))
    if db.get('version') != 1 or not isinstance(db.get('characters'), dict):
        raise ValueError('Unsupported addon data')
    batches = []
    batch_id = hashlib.sha256(raw).hexdigest()
    for char in db['characters'].values():
        if not isinstance(char, dict):
            raise ValueError('Invalid character table')
        settings = char.get('settings', {})
        # Addon 0.8.1–0.8.3 enabled sharing by default but only set the enrollment
        # flag after a checkbox click. Recover those exports without enrolling
        # disabled characters or overriding an explicit false enrollment flag.
        enabled_without_flag = ('enrolled' not in char and isinstance(settings, dict)
                                and settings.get('enabled') is True)
        if char.get('enrolled') is not True and not enabled_without_flag:
            continue
        opted_in = settings.get('discord_enabled') is True
        previously_enabled = (char.get('discord_enrolled') is True
                              or ('discord_enabled' not in settings and char.get('enrolled') is True))
        if not opted_in and not previously_enabled:
            continue
        payload = dict(char, version=1)
        payload['settings'] = dict(settings, enabled=settings.get('enabled') is True and opted_in)
        payload['settings']['discord_delivery'] = 'summary'
        payload['upload_batch'] = batch_id
        snapshot = payload.get('snapshot', {})
        if isinstance(snapshot, dict) and isinstance(snapshot.get('professions'), dict):
            snapshot['professions'] = list(snapshot['professions'].values())
        history = char.get('history', {})
        if not isinstance(history, dict):
            raise ValueError('Invalid addon history')
        events = history.get('events', payload.get('events', {}))
        if not isinstance(events, dict):
            raise ValueError('Invalid addon events')
        records = list(events.values())
        since = char.get('discord_since', 0)
        if since:
            since = integer(since, 'Discord sharing start', 1, char['exported_at'] + 300)
            records = [event for event in records if event.get('at', 0) >= since]
        if 'tracking' in history:
            tracking = history['tracking']
            if not isinstance(tracking, dict):
                raise ValueError('Invalid level tracking')
            points = tracking.get('points', {})
            if isinstance(points, dict):
                points = list(points.values())
            payload['tracking'] = dict(tracking, points=[p for p in points if p.get('at', 0) >= since])
        # The persistent local history can exceed the rolling buffer/API batch size.
        for offset in range(0, max(1, len(records)), 100):
            batch = records[offset:offset + 100]
            result = validate(dict(payload, events=batch))
            if 'group_ids' in char and char.get('legacy_upload') is not True:
                from .group_routing import memberships
                result['_groups'] = memberships(char['group_ids'], result['exported_at'])
                name = db.get('player_name', char.get('player_name', ''))
                result['_player_name'] = string(name, 'player name', 40) if name else ''
                targets = {}
                for event in batch:
                    ids = event.get('group_ids')
                    if ids is not None and not isinstance(ids, dict):
                        raise ValueError('Invalid event group targets')
                    targets[event['id']] = list(ids) if ids is not None else None
                result['_event_targets'] = targets
            result['_discord_since'] = since
            if not opted_in:
                result['_discord_opt_out'] = True
            batches.append(result)
    # A complete batch is explicit: large histories must not produce one message per chunk.
    active = [p for p in batches if p['settings']['enabled']]
    grouped_batches = {}
    for result in batches:
        result['_group_parts'] = {}
    for index, result in enumerate(active, 1):
        result['upload_part'], result['upload_parts'] = index, len(active)
        for target in result.get('_groups', {}):
            grouped_batches.setdefault(target, []).append(result)
    for target, selected in grouped_batches.items():
        for part, result in enumerate(selected, 1):
            result['_group_parts'][target] = (part, len(selected))
    yield from batches


async def link(url, code, credentials):
    url = endpoint(url)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(url + '/v1/link', json={'code': code},
                                allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError(f'Linking failed (HTTP {response.status})')
            token = (await response.json())['token']
    atomic_json(credentials, {'url': url, 'token': token})


def retry_seconds(response):
    try:
        seconds = int(response.headers.get('Retry-After', '60'))
    except (AttributeError, ValueError, TypeError):
        seconds = 60
    return min(86400, max(1, seconds))


async def upload(paths, credentials, state, once=False, dry_run=False, interval=5,
                 status=None, stop_event=None):
    if status is None:
        def status(**values):
            if 'connection' in values:
                print(values['connection'])
    config = {} if dry_run else json.loads(Path(credentials).read_text(encoding='utf-8'))
    url = endpoint(config['url']) if config else None
    grouped = config.get('mode') == 'groups'
    cache = {} if dry_run or not Path(state).exists() else json.loads(Path(state).read_text(encoding='utf-8'))
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        group_uploader = None
        if grouped:
            from .group_client import GroupUploader
            group_uploader = GroupUploader(config, credentials, cache, state, session, status)
        while True:
            if stop_event is not None and stop_event.is_set():
                return True
            failed = False
            if group_uploader:
                group_uploader.failed = False
            for path in paths:
                try:
                    for payload in exports(path):
                        status(last_export=payload['exported_at'])
                        encoded = json.dumps(payload, sort_keys=True)
                        key = hashlib.sha256((json.dumps(payload['identity'], sort_keys=True)
                                              + config.get('token', '')
                                              + (payload['events'][0]['id'] if payload['events'] else ':snapshot'))
                                             .encode()).hexdigest()
                        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
                        if dry_run:
                            print(json.dumps(payload, indent=2))
                            continue
                        if group_uploader:
                            if not await group_uploader.upload(payload):
                                failed = True
                            continue
                        if '_groups' in payload:
                            raise ValueError('Configure group mode before uploading selected group IDs')
                        if cache.get(key) == fingerprint:
                            continue
                        if (payload['settings']['enabled']
                                and cache.get('_retry_upload_at', 0) > time.time()):
                            failed = True
                            status(connection='Temporarily limited; retained data will retry automatically.')
                            continue
                        async with session.post(url + '/v1/upload',
                            json={k: v for k, v in payload.items() if not k.startswith('_')},
                            headers={'Authorization': 'Bearer ' + config['token']},
                            allow_redirects=False) as response:
                            if response.status == 429:
                                cache['_retry_upload_at'] = time.time() + retry_seconds(response)
                                atomic_json(state, cache)
                            if response.status != 200:
                                # Never log request bodies or authentication headers.
                                print(f'Upload not accepted (HTTP {response.status}); export retained.')
                                reason = {401: 'Link again using a new Discord /link code.',
                                          409: 'Run /reload to export current data; check character ownership.'}.get(
                                              response.status, 'Check service configuration and try again.')
                                status(connection=f'Upload rejected (HTTP {response.status}). {reason}')
                                failed = True
                                continue
                            await response.read()
                        cache.pop('_retry_upload_at', None)
                        cache[key] = fingerprint
                        atomic_json(state, cache)
                        print(f'Uploaded selected character data at {int(time.time())}.')
                        status(connection='Connected; latest exported data uploaded',
                               last_upload=int(time.time()))
                except (OSError, ValueError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    print(f'Upload deferred ({type(exc).__name__}); will retry from SavedVariables.')
                    failed = True
                    status(connection='Waiting: check file path or service connection; will retry.')
            if once or dry_run:
                return not failed
            delay = max(interval, 30 if failed else interval)
            for _ in range(delay):
                if stop_event is not None and stop_event.is_set():
                    return True
                await asyncio.sleep(1)
