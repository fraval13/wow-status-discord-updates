"""Read only WoWStatus SavedVariables, filter, and retry from disk after restarts."""
import asyncio
import hashlib
import json
import os
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from .savedvariables import MAX_BYTES, ParseError, parse
from .schema import MAX_CLOCK_OFFSET, ValidationError, integer, realm_now, string, validate


def endpoint(url):
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Service URL must not contain credentials, query, or fragment')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and
            parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ValueError('HTTPS is required except on localhost')
    return url.rstrip('/')


def scoped_claim_secret(payload, url):
    """Give each destination its own value derived from the addon's claim secret, so a
    value seen by one service or group can't take the character over on another (#11).
    Equivalent spellings of one URL give the same value."""
    if 'claim_secret' not in payload:
        return payload
    parsed = urlparse(url)
    default = {'https': 443, 'http': 80}.get(parsed.scheme)
    port = f':{parsed.port}' if parsed.port and parsed.port != default else ''
    destination = f'{parsed.scheme}://{parsed.hostname}{port}{parsed.path.rstrip("/")}'
    secret = hashlib.sha256(f'wow-status-claim:{destination}:{payload["claim_secret"]}'
                            .encode()).hexdigest()[:32]
    return dict(payload, claim_secret=secret)


# Characters of encoded JSON gathered before each write in atomic_json.
WRITE_BATCH = 1 << 20


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    # The incremental encoder, unlike json.dumps, lets other threads run while it encodes
    # a large archive. Its many small pieces are written in large batches: a write per
    # piece released and retook the GIL so often that the event loop waited for it, and
    # one write of the whole text would hold a second copy of a large archive (#2).
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        batch, size = [], 0
        for piece in json.JSONEncoder(ensure_ascii=False, indent=2,
                                      sort_keys=True).iterencode(data):
            batch.append(piece)
            size += len(piece)
            if size >= WRITE_BATCH:
                stream.write(''.join(batch))
                batch, size = [], 0
        stream.write(''.join(batch))
    os.replace(temp, path)
    if os.name != 'nt':
        path.chmod(0o600)


def _after(item, since):
    # An entry without an integer timestamp cannot be shown to postdate consent or be
    # uploaded, so it is dropped rather than blocking every character in the file.
    at = item.get('at', 0)
    return type(at) is int and at >= since


def exports(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError('SavedVariables file exceeds 32 MiB')
    db = parse(raw.decode('utf-8-sig'))
    if db.get('version') != 1 or not isinstance(db.get('characters'), dict):
        raise ValidationError('Unsupported addon data')
    batches = []
    batch_id = hashlib.sha256(raw).hexdigest()
    for char in db['characters'].values():
        if not isinstance(char, dict):
            raise ValidationError('Invalid character table')
        settings = char.get('settings', {})
        # Addon 0.8.1–0.8.3 enabled sharing by default but only set the enrollment
        # flag after a checkbox click. Recover those exports without enrolling
        # disabled characters or overriding an explicit false enrollment flag.
        enabled_without_flag = ('enrolled' not in char and isinstance(settings, dict)
                                and settings.get('enabled') is True)
        if char.get('enrolled') is not True and not enabled_without_flag:
            continue
        if not isinstance(settings, dict):
            raise ValidationError('Invalid character settings')
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
            raise ValidationError('Invalid addon history')
        events = history.get('events', payload.get('events', {}))
        if not isinstance(events, dict):
            raise ValidationError('Invalid addon events')
        if not all(isinstance(event, dict) for event in events.values()):
            raise ValidationError('Invalid addon event')
        # The addon's stamps are realm time; this PC's clock can differ from it.
        clock_offset = integer(char.get('clock_offset', 0), 'clock offset', -MAX_CLOCK_OFFSET, MAX_CLOCK_OFFSET)
        since = char.get('discord_since', 0)
        if type(since) is not int or since:
            if type(char.get('exported_at')) is not int:
                raise ValidationError('Invalid export time')
            since = integer(since, 'Discord sharing start', 1, char['exported_at'] + 300)
        records = [event for event in events.values()
                   if event.get('kind') != 'session' and _after(event, since)]
        if 'tracking' in history:
            tracking = history['tracking']
            if not isinstance(tracking, dict):
                raise ValidationError('Invalid level tracking')
            points = tracking.get('points', {})
            if isinstance(points, dict):
                points = list(points.values())
            if not isinstance(points, list) or not all(isinstance(p, dict) for p in points):
                raise ValidationError('Invalid level tracking')
            payload['tracking'] = dict(tracking, points=[p for p in points if _after(p, since)])
        # The persistent local history can exceed the rolling buffer/API batch size.
        for offset in range(0, max(1, len(records)), 100):
            batch = records[offset:offset + 100]
            result = validate(dict(payload, events=batch), now=realm_now(clock_offset))
            result['_clock_offset'] = clock_offset
            if 'group_ids' in char and char.get('legacy_upload') is not True:
                from .group_routing import memberships
                result['_groups'] = memberships(char['group_ids'], result['exported_at'])
                name = db.get('player_name', char.get('player_name', ''))
                result['_player_name'] = string(name, 'player name', 40) if name else ''
                targets = {}
                for event in batch:
                    ids = event.get('group_ids')
                    if ids is not None and not isinstance(ids, dict):
                        raise ValidationError('Invalid event group targets')
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
                    payloads = list(exports(path))
                except Exception as exc:
                    # One missing, unreadable or malformed file must never stop the upload loop.
                    # Only our own fixed validation messages are logged, never file content.
                    detail = f': {exc}' if isinstance(exc, (ValidationError, ParseError)) else ''
                    print(f'Skipped unreadable SavedVariables ({type(exc).__name__}{detail}); will retry later.')
                    if not isinstance(exc, (OSError, ValueError)):
                        # Unexpected errors are likely bugs: show where, but not the message or values.
                        print(''.join(traceback.format_tb(exc.__traceback__)), end='')
                    failed = True
                    status(connection='Waiting: check the SavedVariables file path; will retry.'
                           if isinstance(exc, OSError) else
                           'Waiting: SavedVariables could not be read; retrying until the addon saves a valid file.')
                    continue
                try:
                    for payload in payloads:
                        status(last_export=payload['exported_at'])
                        encoded = json.dumps(payload, sort_keys=True)
                        key = hashlib.sha256((json.dumps(payload['identity'], sort_keys=True)
                                              + config.get('token', '')
                                              + (payload['events'][0]['id'] if payload['events'] else ':snapshot'))
                                             .encode()).hexdigest()
                        fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
                        if dry_run:
                            # Output may be pasted into bug reports; keep the secret out.
                            shown = dict(payload, claim_secret='<hidden>') if 'claim_secret' in payload else payload
                            print(json.dumps(shown, indent=2))
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
                        body = scoped_claim_secret(
                            {k: v for k, v in payload.items() if not k.startswith('_')}, url)
                        async with session.post(url + '/v1/upload', json=body,
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
