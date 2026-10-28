"""Shared protocol validation and a second privacy filter at the server boundary."""
import json
import re
import time

FIELDS = {'level', 'class', 'race', 'faction', 'guild', 'gear', 'zone', 'playtime', 'professions'}
LEVEL_CAPS = {'classic-era': 60, 'forever': 60}
KINDS = {'introduction', 'level', 'loot', 'equipment', 'death', 'zone', 'session', 'lfg'}


class ValidationError(ValueError):
    pass


def string(value, name, limit=120):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValidationError(f'Invalid {name}')
    if any(ord(c) < 32 for c in value):
        raise ValidationError(f'Control characters in {name}')
    return value


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f'Invalid {name}')
    return value


def validate(payload):
    if (not isinstance(payload, dict) or type(payload.get('version')) is not int
            or payload['version'] != 1):
        raise ValidationError('Unsupported payload version')
    identity = payload.get('identity', {})
    settings = payload.get('settings', {})
    if not isinstance(identity, dict) or not isinstance(settings, dict):
        raise ValidationError('Invalid identity or settings')
    if identity.get('client') not in ('classic-era', 'forever'):
        raise ValidationError('Unsupported client adapter')
    cap = LEVEL_CAPS[identity['client']]
    clean = {'version': 1, 'identity': {k: string(identity.get(k), k) for k in
                                      ('guid', 'name', 'realm', 'client')},
             'settings': {}, 'snapshot': {}, 'events': []}
    if 'upload_batch' in payload:
        batch = payload['upload_batch']
        if not isinstance(batch, str) or not re.fullmatch('[a-f0-9]{64}', batch):
            raise ValidationError('Invalid upload batch')
        clean['upload_batch'] = batch
        clean['upload_parts'] = integer(payload.get('upload_parts', 1), 'upload parts', 1, 10000)
        clean['upload_part'] = integer(payload.get('upload_part', 1), 'upload part', 1,
                                       clean['upload_parts'])
    if 'group_id' in payload:
        target = payload['group_id']
        if not isinstance(target, str) or not re.fullmatch('[a-f0-9]{22}', target):
            raise ValidationError('Invalid group ID')
        clean['group_id'] = target
    if payload.get('group_name'):
        clean['group_name'] = string(payload['group_name'], 'group name', 80)
    if payload.get('player_name'):
        clean['player_name'] = string(payload['player_name'], 'player name', 40)
    if 'build' in identity:
        clean['identity']['build'] = string(identity['build'], 'client build', 40)
    if 'interface' in identity:
        clean['identity']['interface'] = integer(identity['interface'], 'interface', 1, 1_000_000)
    for key in ('enabled', 'introduction_confirmed'):
        clean['settings'][key] = settings.get(key) is True
    for key, allowed in [('fields', FIELDS), ('collection', KINDS), ('announcements', KINDS)]:
        values = settings.get(key, settings.get('announcements', {}) if key == 'collection' else {})
        if not isinstance(values, dict):
            raise ValidationError(f'Invalid {key}')
        clean['settings'][key] = {k: values.get(k) is True for k in sorted(allowed)}
    delivery = settings.get('discord_delivery', 'events')
    if delivery not in ('events', 'summary'):
        raise ValidationError('Invalid Discord delivery mode')
    clean['settings']['discord_delivery'] = delivery
    role = settings.get('character_role', 'alt')
    if role not in ('main', 'alt'):
        raise ValidationError('Invalid character role')
    clean['settings']['character_role'] = role
    clean['settings']['loot_quality'] = integer(settings.get('loot_quality', 4),
                                               'loot_quality', 0, 5)
    clean['settings']['level_interval'] = integer(settings.get('level_interval', 10),
                                                 'level_interval', 1, 100)
    clean['exported_at'] = integer(payload.get('exported_at'), 'exported_at',
                                    1, int(time.time()) + 300)
    snapshot = payload.get('snapshot', {})
    if not isinstance(snapshot, dict):
        raise ValidationError('Invalid snapshot')
    if clean['settings']['enabled']:
        for key in FIELDS:
            if clean['settings']['fields'][key] and key in snapshot:
                val = snapshot[key]
                if key in ('level', 'playtime'):
                    integer(val, key, 0 if key == 'playtime' else 1,
                            2_000_000_000 if key == 'playtime' else cap)
                elif key == 'professions':
                    if not isinstance(val, list) or len(val) > 6:
                        raise ValidationError('Invalid professions')
                    val = [{'name': string(p.get('name'), 'profession name', 50),
                            'source': 'player_entered'} for p in val if isinstance(p, dict)]
                elif key == 'gear':
                    if not isinstance(val, dict) or len(val) > 20:
                        raise ValidationError('Invalid gear')
                    for slot, item in val.items():
                        string(str(slot), 'gear slot', 2)
                        string(item, 'gear item', 500)
                else:
                    string(val, key, 200)
                clean['snapshot'][key] = val
    if (clean['settings']['enabled'] and clean['settings']['fields']['playtime']
            and 'playtime' in clean['snapshot'] and snapshot.get('playtime_recorded_at') is not None):
        clean['snapshot']['playtime_recorded_at'] = integer(snapshot['playtime_recorded_at'],
            'playtime observation', 1, clean['exported_at'] + 300)
    events = payload.get('events', [])
    if not isinstance(events, list) or len(events) > 500:
        raise ValidationError('Maximum 500 events per upload')
    for event in events:
        if not isinstance(event, dict):
            raise ValidationError('Invalid event')
        kind = event.get('kind')
        if kind not in KINDS:
            raise ValidationError('Unsupported event kind')
        eid = string(event.get('id'), 'event ID', 180)
        at = integer(event.get('at'), 'event timestamp', 1, clean['exported_at'] + 300)
        if not clean['settings']['enabled'] or not clean['settings']['collection'][kind]:
            continue
        if kind == 'introduction' and not clean['settings']['introduction_confirmed']:
            continue
        data = event.get('data', {})
        if not isinstance(data, dict):
            raise ValidationError('Invalid event data')
        filtered = {}
        if kind == 'introduction' and data.get('source') == 'group_enrollment':
            filtered = {'source': 'group_enrollment'}
        if kind == 'level':
            if not clean['settings']['fields']['level']:
                continue
            level = integer(data.get('level'), 'event level', 1, cap)
            filtered = {'level': level, 'maximum': level == cap,
                        'synthetic': data.get('synthetic') is True}
        elif kind == 'loot':
            quality = integer(data.get('quality'), 'quality', 0, 5)
            filtered = {'quality': quality, 'item': string(data.get('item'), 'item', 500)}
        elif kind == 'equipment':
            if not clean['settings']['fields']['gear']:
                continue
            filtered = {'item': string(data.get('item'), 'item', 500)}
            if data.get('quality') is not None:
                filtered['quality'] = integer(data['quality'], 'quality', 0, 5)
        elif kind == 'zone':
            if not clean['settings']['fields']['zone']:
                continue
            filtered = {'zone': string(data.get('zone'), 'zone', 200)}
        elif kind == 'lfg':
            filtered = {'text': string(data.get('text'), 'LFG text', 200)}
        elif kind == 'session':
            filtered = {'state': string(data.get('state'), 'session state', 20)}
        if clean['settings']['fields']['zone'] and data.get('zone') is not None:
            filtered['zone'] = string(data['zone'], 'event zone', 200)
        if (kind == 'level' and clean['settings']['fields']['playtime']
                and data.get('played_level_seconds') is not None):
            filtered['played_level_seconds'] = integer(data['played_level_seconds'],
                'played level seconds', 0, 2_000_000_000)
        clean['events'].append({'id': eid, 'kind': kind, 'at': at, 'data': filtered})
    tracking = payload.get('tracking')
    if tracking is not None:
        if not isinstance(tracking, dict) or not isinstance(tracking.get('points', []), list):
            raise ValidationError('Invalid level tracking')
        if len(tracking.get('points', [])) > 2000:
            raise ValidationError('Too many level observations')
        filtered_points = []
        enabled = (clean['settings']['enabled'] and clean['settings']['fields']['level']
                   and clean['settings']['collection']['level'])
        if enabled:
            for point in tracking.get('points', []):
                if not isinstance(point, dict) or point.get('kind') not in ('baseline', 'level'):
                    raise ValidationError('Invalid level observation')
                item = {'kind': point['kind'],
                        'level': integer(point.get('level'), 'observed level', 1, cap),
                        'at': integer(point.get('at'), 'observation time', 1, clean['exported_at'] + 300),
                        'segment': string(point.get('segment'), 'tracking segment', 120)}
                if point.get('event_id') is not None:
                    item['event_id'] = string(point['event_id'], 'observation event ID', 180)
                filtered_points.append(item)
        clean['tracking'] = {'points': filtered_points}
        if enabled and tracking.get('observed_until') is not None:
            clean['tracking']['observed_until'] = integer(tracking['observed_until'],
                'last level observation', 1, clean['exported_at'] + 300)
    if len(json.dumps(clean)) > 256_000:
        raise ValidationError('Payload too large')
    return clean


def should_announce(settings, event):
    if not settings['enabled'] or not settings['announcements'].get(event['kind']):
        return False
    if event['kind'] == 'level':
        if settings.get('discord_delivery') == 'summary':
            return True
        return (event['data']['level'] % settings['level_interval'] == 0
                or event['data'].get('maximum') is True)
    if event['kind'] == 'loot':
        return event['data']['quality'] >= settings['loot_quality']
    return True
