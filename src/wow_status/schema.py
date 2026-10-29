"""Shared protocol validation and a second privacy filter at the server boundary."""
import json
import re
import time

FIELDS = {'level', 'class', 'race', 'faction', 'guild', 'gear', 'zone', 'playtime', 'professions', 'deaths', 'quests'}
LEVEL_CAPS = {'classic-era': 60, 'forever': 60}
KINDS = {'introduction', 'level', 'loot', 'equipment', 'death', 'zone', 'session', 'lfg', 'quest', 'profession', 'status', 'dungeon', 'mount', 'reputation', 'unlock', 'pvp', 'discovery'}
STATUS_FIELDS = {
    'level': ('level','level'), 'xp_current': ('level','level'), 'xp_max': ('level','level'),
    'class': ('class','introduction'), 'class_id': ('class','introduction'),
    'race': ('race','introduction'), 'sex': ('race','introduction'),
    'faction': ('faction','introduction'), 'zone': ('zone','zone'),
    'professions': ('professions','profession'), 'deaths': ('deaths','death'),
    'quests_completed': ('quests','quest'),
}



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
    if 'player_name' in payload:
        clean['player_name'] = '' if payload['player_name'] == '' else string(payload['player_name'], 'player name', 40)
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
    for section in ('collection', 'announcements'):
        for removed in ('discovery', 'lfg'):
            clean['settings'][section][removed] = False
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
                if key in ('level', 'playtime', 'deaths', 'quests'):
                    integer(val, key, 0 if key != 'level' else 1,
                            cap if key == 'level' else 2_000_000_000)
                elif key == 'professions':
                    if not isinstance(val, list) or len(val) > 6:
                        raise ValidationError('Invalid professions')
                    professions = []
                    for profession in val:
                        if not isinstance(profession, dict):
                            raise ValidationError('Invalid profession')
                        entry = {'name': string(profession.get('name'), 'profession name', 50),
                                 'source': 'game_api' if profession.get('source') == 'game_api' else 'player_entered'}
                        if 'skill' in profession:
                            entry['max_skill'] = integer(profession.get('max_skill'), 'profession maximum', 1, 2000)
                            entry['skill'] = integer(profession['skill'], 'profession skill', 0, entry['max_skill'])
                        if profession.get('key') in {'alchemy','blacksmithing','enchanting','engineering',
                                'herbalism','leatherworking','mining','skinning','tailoring','cooking','first_aid','fishing'}:
                            entry['key'] = profession['key']
                        professions.append(entry)
                    val = professions
                elif key == 'gear':
                    if not isinstance(val, dict) or len(val) > 20:
                        raise ValidationError('Invalid gear')
                    for slot, item in val.items():
                        string(str(slot), 'gear slot', 2)
                        string(item, 'gear item', 500)
                else:
                    string(val, key, 200)
                clean['snapshot'][key] = val
    if clean['settings']['enabled']:
        if clean['settings']['fields']['race'] and snapshot.get('sex') in ('Male', 'Female'):
            clean['snapshot']['sex'] = snapshot['sex']
        if clean['settings']['fields']['class'] and snapshot.get('class_id') in {
                'WARRIOR','PALADIN','HUNTER','ROGUE','PRIEST','SHAMAN','MAGE','WARLOCK','DRUID'}:
            clean['snapshot']['class_id'] = snapshot['class_id']
        if clean['settings']['fields']['level'] and 'xp_current' in snapshot:
            maximum = integer(snapshot.get('xp_max'), 'XP maximum', 1, 2_000_000_000)
            xp = integer(snapshot['xp_current'], 'XP', 0, maximum)
            clean['snapshot'].update(xp_current=xp, xp_max=maximum, xp_percent=round(xp/maximum*100,1))
        if clean['settings']['fields']['deaths'] and 'deaths' in snapshot:
            clean['snapshot']['deaths'] = integer(snapshot['deaths'], 'total deaths', 0, 2_000_000_000)
            clean['snapshot']['deaths_since'] = integer(snapshot.get('deaths_since'), 'death tracking start', 1, clean['exported_at']+300)
        if clean['settings']['fields']['quests'] and 'quests_completed' in snapshot:
            clean['snapshot']['quests_completed'] = integer(snapshot['quests_completed'], 'completed quests', 0, 2_000_000_000)
            if snapshot.get('quests_source') not in ('game_api', 'tracked_since'):
                raise ValidationError('Invalid quest count source')
            clean['snapshot']['quests_source'] = snapshot['quests_source']
            clean['snapshot']['quests_since'] = integer(snapshot.get('quests_since'), 'quest tracking start', 1, clean['exported_at']+300)
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
        if not clean['settings']['enabled'] or (kind != 'status' and not clean['settings']['collection'][kind]):
            continue
        if kind == 'introduction' and not clean['settings']['introduction_confirmed']:
            continue
        data = event.get('data', {})
        if not isinstance(data, dict):
            raise ValidationError('Invalid event data')
        if kind == 'dungeon' and data.get('source') != 'game_api':
            continue
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
        elif kind == 'death' and clean['settings']['fields']['deaths'] and 'total_deaths' in data:
            filtered = {'total_deaths': integer(data['total_deaths'], 'total deaths', 0, 2_000_000_000)}
        elif kind == 'quest':
            if 'completed' in data:
                if not clean['settings']['fields']['quests']:
                    continue
                completed = integer(data['completed'], 'quest milestone', 100, 2_000_000_000)
                if completed % 100:
                    raise ValidationError('Invalid quest milestone')
                filtered = {'completed': completed}
                if data.get('source') in ('game_api', 'tracked_since'):
                    filtered['source'] = data['source']
            else:
                filtered = {'quest_id': integer(data.get('quest_id'), 'quest ID', 1, 2_000_000_000)}
        elif kind == 'profession':
            maximum = integer(data.get('max_skill'), 'profession maximum', 1, 2000)
            filtered = {'name': string(data.get('name'), 'profession name', 50),
                        'skill': integer(data.get('skill'), 'profession skill', 0, maximum), 'max_skill': maximum}
            if data.get('title') in ('Apprentice', 'Journeyman', 'Expert', 'Artisan'):
                filtered['title'] = data['title']
        elif kind in {'dungeon', 'mount', 'reputation', 'unlock', 'pvp', 'discovery'}:
            filtered = {'text': string(data.get('text'), 'milestone text', 160)}
            if data.get('source') in ('game_api', 'player_entered', 'collection', 'observed_ride'):
                filtered['source'] = data['source']
            if kind == 'dungeon' and 'instance_id' in data:
                filtered['instance_id'] = integer(data['instance_id'], 'dungeon instance', 1, 1_000_000_000)
                filtered['name'] = string(data.get('name'), 'dungeon name', 80)
                filtered['text'] = 'First clear: ' + filtered['name']
            if kind == 'unlock' and 'spell_id' in data:
                filtered['spell_id'] = integer(data['spell_id'], 'unlock spell', 1, 2_000_000_000)
            if kind == 'reputation' and 'standing' in data:
                filtered['standing'] = integer(data['standing'], 'reputation standing', 6, 8)
            if kind == 'pvp' and 'rank' in data:
                filtered['rank'] = integer(data['rank'], 'PvP rank', 1, 100)
        elif kind == 'status':
            changes = data.get('changed', [])
            if not isinstance(changes, list) or len(changes) > len(STATUS_FIELDS):
                raise ValidationError('Invalid status changes')
            permitted = []
            for key in changes:
                if not isinstance(key, str) or key not in STATUS_FIELDS:
                    raise ValidationError('Invalid status field')
                field, category = STATUS_FIELDS[key]
                if clean['settings']['fields'][field] and clean['settings']['announcements'][category]:
                    permitted.append(key)
            if not permitted:
                continue
            filtered = {'changed': permitted}
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
    if event['kind'] in ('discovery', 'lfg'):
        return False
    if event['kind'] == 'dungeon' and event['data'].get('source') != 'game_api':
        return False
    if settings.get('discord_delivery') == 'summary':
        if event['kind'] == 'session':
            return False
        if event['kind'] == 'status':
            return settings['enabled'] and any(
                key in STATUS_FIELDS and settings['fields'][STATUS_FIELDS[key][0]]
                and settings['announcements'][STATUS_FIELDS[key][1]]
                for key in event['data'].get('changed', []))
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
