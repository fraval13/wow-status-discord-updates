"""Explicit addon group selection; destinations never learn other selected IDs."""
import copy
import re

from .schema import ValidationError, integer

GROUP_ID = re.compile(r'[a-f0-9]{22}\Z')


def group_id(value):
    if not isinstance(value, str) or not GROUP_ID.fullmatch(value):
        raise ValidationError('Invalid internal group key')
    return value


def group_label(value):
    if not isinstance(value, str):
        raise ValidationError('Group name must be text')
    value = value.strip(' \t\r\n\v\f')
    if not value or len(value) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValidationError('Use a group name of 1–80 printable characters')
    return value


def group_key(value):
    """Portable Lua/Python routing key. Exact, case-sensitive UTF-8; not a password hash."""
    value = group_label(value)
    a, b, c = 5381, 2166136261, 104729
    for byte in value.encode('utf-8'):
        a = (a * 33 + byte) % 4294967296
        b = (b * 65599 + byte) % 4294967296
        c = (c * 131 + byte) % 4294967296
    return f'{a:08x}{b:08x}{c % 16777216:06x}'


def memberships(raw, exported_at):
    if not isinstance(raw, dict) or len(raw) > 8:
        raise ValidationError('Choose up to 8 groups')
    result = {}
    for key, data in raw.items():
        group_id(key)
        if not isinstance(data, dict):
            raise ValidationError('Invalid group membership')
        label = group_label(data.get('label'))
        if group_key(label) != key:
            raise ValidationError('Group name does not match its routing key')
        result[key] = {'label': label, 'joined_at': integer(data.get('joined_at'), 'group joined time', 1,
                                             exported_at + 300)}
        if data.get('baseline_level') is not None:
            result[key]['baseline_level'] = integer(data['baseline_level'], 'group baseline', 1, 1000)
    return result


def for_group(payload, target, minimum=0):
    """Only selected, post-join events; never include the routing list on the wire."""
    selected = payload.get('_groups', {})
    member = selected[target]
    since = max(member['joined_at'], minimum)
    result = copy.deepcopy({key: value for key, value in payload.items() if not key.startswith('_')})
    result['group_id'] = group_id(target)
    result['group_name'] = member['label']
    result['player_name'] = payload.get('_player_name', '')
    event_targets = payload.get('_event_targets', {})
    result['events'] = [event for event in result['events']
                        if event['at'] >= since and (event_targets.get(event['id']) is None
                            or target in event_targets[event['id']])]
    settings = result['settings']
    if (settings['enabled'] and settings['collection']['introduction']
            and settings['introduction_confirmed']):
        # One enrollment introduction per group; no claim that a character was just created.
        result['events'] = [e for e in result['events'] if e['kind'] != 'introduction']
        result['events'].append({'id': 'group-intro:' + result['identity']['guid'],
                                  'kind': 'introduction', 'at': since,
                                  'data': {'source': 'group_enrollment'}})
    if 'tracking' in result:
        tracking = result['tracking']
        tracking['points'] = [p for p in tracking['points'] if p['at'] >= since]
        baseline = member.get('baseline_level') if minimum <= member['joined_at'] else None
        baseline_at = since
        if minimum > member['joined_at']:
            baseline = result['snapshot'].get('level')
            baseline_at = result['exported_at']
        allowed = settings['enabled'] and settings['fields']['level'] and settings['collection']['level']
        if baseline is not None and allowed and (not tracking['points'] or
                (tracking['points'][0]['kind'] != 'baseline' and baseline_at <= tracking['points'][0]['at'])):
            segment = (tracking['points'][0]['segment'] if tracking['points'] else 'group:' + target)
            tracking['points'].insert(0, {'kind': 'baseline', 'level': baseline, 'at': baseline_at,
                                          'segment': segment})
    return result


def withdrawal(payload, target):
    result = copy.deepcopy({key: value for key, value in payload.items() if not key.startswith('_')})
    result['group_id'] = group_id(target)
    result['settings']['enabled'] = False
    result['settings']['introduction_confirmed'] = False
    result['events'], result['snapshot'] = [], {}
    result['tracking'] = {'points': []}
    return result
