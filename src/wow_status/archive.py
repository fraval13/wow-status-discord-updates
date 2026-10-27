"""Privacy-filtered per-character JSON history, with explicit Norwegian timestamps."""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .companion import atomic_json

TIMEZONE = 'Europe/Oslo'
GROUPS = {
    'introduction': ('enrollment', 'introductions'),
    'level': ('progression', 'level_history'),
    'loot': ('items', 'loot'),
    'equipment': ('items', 'equipment_changes'),
    'death': ('activity', 'deaths'),
    'zone': ('activity', 'zones'),
    'session': ('activity', 'addon_sessions'),
    'lfg': ('activity', 'looking_for_group'),
}


def timestamp(value):
    return {'iso': datetime.fromtimestamp(value, ZoneInfo(TIMEZONE)).isoformat(timespec='seconds'),
            'unix': int(value), 'timezone': TIMEZONE}


def item_reference(link):
    """Keep the original link and extract stable joins without claiming verified metadata."""
    result = {'link': link, 'item_id': None, 'enchant_id': None}
    match = re.search(r'item:(\d+)(?::(-?\d+))?', link)
    if match:
        result['item_id'] = int(match.group(1))
        if match.group(2) is not None:
            result['enchant_id'] = int(match.group(2))
    label = re.search(r'\|h(.*?)\|h', link)
    if label:
        result['display_name'] = label.group(1).strip('[]')
    return result


def fields_document(fields):
    result = dict(fields)
    if 'gear' in result:
        result['gear'] = {str(slot): item_reference(link)
                          for slot, link in result['gear'].items()}
    return result


def event_document(data):
    result = dict(data)
    if 'item' in result:
        result['item_reference'] = item_reference(result['item'])
    return result


def character_document(store, cid):
    row = store.db.execute('SELECT * FROM characters WHERE id=?', (cid,)).fetchone()
    if not row:
        return None
    char = store.decode(row)
    from .people import character_role, person
    result = {
        'schema_version': 1,
        'timezone': TIMEZONE,
        'character': {'id': cid, **char['identity'], 'discord_owner_id': char['owner'],
                      'friend': person(store, char['owner']), 'role': character_role(store, cid)},
        'sharing': char['settings'],
        'profile': {'current': fields_document(char['snapshot']), 'last_exported_at': timestamp(char['exported']),
                    'last_uploaded_at': timestamp(char['uploaded']), 'snapshot_history': []},
        'enrollment': {'introductions': []},
        'progression': {'level_history': []},
        'items': {'loot': [], 'equipment_changes': []},
        'activity': {'deaths': [], 'zones': [], 'addon_sessions': [], 'looking_for_group': []},
        'daily_recaps': [], 'weekly_recaps': [],
    }
    for snap in store.db.execute('SELECT * FROM snapshots WHERE character=? ORDER BY exported,id',
                                 (cid,)):
        result['profile']['snapshot_history'].append({
            'id': snap['id'], 'exported_at': timestamp(snap['exported']),
            'uploaded_at': timestamp(snap['uploaded']), 'fields': fields_document(json.loads(snap['snapshot'])),
            'sharing_at_export': json.loads(snap['settings']),
            'evidence': {'source': 'addon_snapshot', 'certainty': 'observed_at_export'}})
    for event in store.db.execute('SELECT * FROM events WHERE character=? AND suppressed=0 '
                                  'ORDER BY at,id', (cid,)):
        group, category = GROUPS[event['kind']]
        delivery = store.db.execute('SELECT status,attempts,message_id FROM outbox '
                                    'WHERE character=? AND event_id=?',
                                    (cid, event['id'])).fetchone()
        result[group][category].append({
            'event_id': event['id'], 'recorded_at': timestamp(event['at']),
            'first_uploaded_at': timestamp(event['received']), 'data': event_document(json.loads(event['data'])),
            'evidence': {'source': ('addon_test' if json.loads(event['data']).get('synthetic')
                                     else 'addon_event'), 'certainty': 'player_reported',
                         'client': char['identity']['client']},
            'immediate_delivery': dict(delivery) if delivery else {'status': 'not_queued'}})
    for recap in store.db.execute('SELECT p.*,d.start,d.end,d.generated FROM digest_parts p '
                                  'JOIN digests d USING(day,timezone) WHERE character=? ORDER BY day',
                                  (cid,)):
        from .daily import report
        result['daily_recaps'].append({
            'day': recap['day'], 'timezone': recap['timezone'],
            'window_start': timestamp(recap['start']), 'window_end_exclusive': timestamp(recap['end']),
            'prepared_at': timestamp(recap['generated']), 'delivery_status': recap['status'],
            'discord_message_id': recap['message_id'],
            'summary': report(store, cid, recap['day'], recap['generated'])})
    for recap in store.db.execute('SELECT * FROM weekly_parts WHERE character=? ORDER BY week',
                                  (cid,)):
        from .weekly import week_report
        result['weekly_recaps'].append({
            'week_start': recap['week'], 'timezone': TIMEZONE,
            'prepared_at': timestamp(recap['generated']), 'delivery_status': recap['status'],
            'discord_message_id': recap['message_id'],
            'summary': week_report(store, cid, recap['week'], recap['generated'])})
    return result


def write_character(store, cid, directory=None):
    document = character_document(store, cid)
    if document is None:
        return
    directory = Path(directory) if directory else store.archive_directory
    atomic_json(directory / f'{cid}.json', document)


def export_characters(store, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    for char in store.characters():
        write_character(store, char['id'], directory)
        files.append({'character_id': char['id'], 'file': f"{char['id']}.json"})
    atomic_json(directory / 'manifest.json', {
        'schema_version': 1, 'timezone': TIMEZONE, 'exported_at': timestamp(time.time()),
        'characters': files,
        'note': 'Only consented, retained data. This export is a private copy; manage its deletion.'})
    return len(files)
