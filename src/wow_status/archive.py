"""Privacy-filtered per-character JSON history, with explicit Norwegian timestamps."""
import json
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .companion import atomic_json

log = logging.getLogger(__name__)
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
    'quest': ('activity', 'quests_completed'),
    'profession': ('activity', 'profession_changes'),
    'status': ('activity', 'status_updates'),
    'dungeon': ('activity', 'dungeon_milestones'),
    'mount': ('activity', 'mount_milestones'),
    'reputation': ('activity', 'reputation_milestones'),
    'unlock': ('activity', 'unlock_milestones'),
    'pvp': ('activity', 'pvp_milestones'),
    'discovery': ('activity', 'discovery_milestones'),

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


def snapshot_entry(snapshot_id, exported, uploaded, fields, settings):
    return {'id': snapshot_id, 'exported_at': timestamp(exported), 'uploaded_at': timestamp(uploaded),
            'fields': fields_document(fields), 'sharing_at_export': settings,
            'evidence': {'source': 'addon_snapshot', 'certainty': 'observed_at_export'}}


def event_entry(event_id, at, received, data, client, delivery=None):
    return {'event_id': event_id, 'recorded_at': timestamp(at),
            'first_uploaded_at': timestamp(received), 'data': event_document(data),
            'evidence': {'source': ('addon_test' if data.get('synthetic')
                                     else data.get('source', 'addon_event')),
                         'certainty': 'player_reported', 'client': client},
            'immediate_delivery': delivery or {'status': 'not_queued'}}


# Snapshot and event entries sit three levels deep in a character archive.
ENTRY_DEPTH = 3


def archived_bytes(entry, depth=ENTRY_DEPTH):
    """Bytes that ``entry`` adds to an archive file, where it sits ``depth`` levels deep in
    a list: its pretty-printed JSON, the indentation of each line and the ``,\n`` after it."""
    text = json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True)
    return len(text.encode('utf-8')) + (text.count('\n') + 1) * 2 * depth + 2


def character_document(store, cid):
    row = store.db.execute('SELECT * FROM characters WHERE id=?', (cid,)).fetchone()
    if not row:
        return None
    char = store.decode(row)
    from .people import character_role, person
    result = {
        'schema_version': 1,
        'timezone': TIMEZONE,
        'group_id': (store.db.execute("SELECT value FROM meta WHERE key='active_group_id'").fetchone() or [None])[0],
        'group_name': (store.db.execute("SELECT value FROM meta WHERE key='active_group_name'").fetchone() or [None])[0],
        'character': {'id': cid, **char['identity'], 'owner_id': char['owner'],
                      'discord_owner_id': person(store, char['owner'])['discord_user_id'],
                      'friend': person(store, char['owner']), 'role': character_role(store, cid)},
        'sharing': char['settings'],
        'profile': {'current': fields_document(char['snapshot']), 'last_exported_at': timestamp(char['exported']),
                    'last_uploaded_at': timestamp(char['uploaded']), 'snapshot_history': []},
        'enrollment': {'introductions': []},
        'progression': {'level_history': []},
        'items': {'loot': [], 'equipment_changes': []},
        'activity': {'deaths': [], 'zones': [], 'addon_sessions': [], 'looking_for_group': [],
                         'quests_completed': [], 'profession_changes': [], 'status_updates': [],
                         'dungeon_milestones': [], 'mount_milestones': [], 'reputation_milestones': [], 'unlock_milestones': [], 'pvp_milestones': [], 'discovery_milestones': []},
        'daily_recaps': [], 'weekly_recaps': [],
    }
    for snap in store.db.execute('SELECT * FROM snapshots WHERE character=? ORDER BY exported,id',
                                 (cid,)):
        result['profile']['snapshot_history'].append(snapshot_entry(
            snap['id'], snap['exported'], snap['uploaded'], json.loads(snap['snapshot']),
            json.loads(snap['settings'])))
    # One query for the events and their deliveries, not one more query per event (#2).
    for event in store.db.execute(
            'SELECT e.id,e.kind,e.at,e.received,e.data,o.id AS delivery,o.status,o.attempts,'
            'o.message_id FROM events e LEFT JOIN outbox o '
            'ON o.character=e.character AND o.event_id=e.id '
            'WHERE e.character=? AND e.suppressed=0 ORDER BY e.at,e.id', (cid,)):
        group, category = GROUPS[event['kind']]
        delivery = None if event['delivery'] is None else {
            'status': event['status'], 'attempts': event['attempts'],
            'message_id': event['message_id']}
        result[group][category].append(event_entry(
            event['id'], event['at'], event['received'], json.loads(event['data']),
            char['identity']['client'], delivery))
    from .progression import timeline
    tracking_row = store.db.execute('SELECT data FROM level_tracking WHERE character=?',
                                     (cid,)).fetchone()
    result['progression']['level_timeline'] = timeline(
        json.loads(tracking_row['data']) if tracking_row else {})
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


class ArchiveWriter:
    """Keeps each character's JSON archive in step with the database.

    ``mark`` records that an archive is out of date. With no writer thread running
    (operator commands, tests) the archive is rebuilt at once, in the caller's thread.
    While the service runs, ``start`` gives one background thread, with its own SQLite
    connection, that rebuilds marked archives. Uploads and the event loop then never wait
    for a rebuild, and several marks of one character before the thread gets to it cost
    one rebuild. ``mark(cid, now=True)`` rebuilds at once even then: data a player
    withdrew leaves the file before the change is answered. ``drop`` deletes an archive.

    Every rebuild and drop takes a number when it starts. A file is written only by a
    rebuild numbered after whatever last wrote or dropped it, so an older read of the
    database never overwrites a newer one, and a rebuild that read the database before a
    drop never writes the file back.
    """

    def __init__(self, store):
        self.store = store
        # Lock order: _files, then _state. mark() only takes _state, so it never waits
        # for a file write.
        self._files = threading.Lock()
        self._state = threading.Lock()
        self._changed = threading.Condition(self._state)
        self._dirty = {}  # character IDs in marking order
        self._sequence = 0  # the number of the latest rebuild or drop to start
        self._written = {}  # character ID -> number of the rebuild or drop that last wrote it
        self._busy = False
        self._thread = None
        self._stopping = False

    def path(self, cid):
        return self.store.archive_directory / f'{cid}.json'

    def mark(self, cid, now=False):
        with self._state:
            if self._thread is not None and not now:
                self._dirty[cid] = None
                self._changed.notify_all()
                return
            # The rebuild below reads everything a waiting mark would have.
            self._dirty.pop(cid, None)
        self._rebuild(cid)

    def drop(self, cid):
        with self._files, self._state:
            self._written[cid] = self._sequence
            self._dirty.pop(cid, None)
            self.path(cid).unlink(missing_ok=True)

    def _rebuild(self, cid):
        with self._state:
            self._sequence += 1
            sequence = self._sequence
        db = self.store.db
        # One read transaction, so a commit from the store thread can't land between two
        # of the document's queries; the caller may already be inside one.
        own = not db.in_transaction
        if own:
            db.execute('BEGIN')
        try:
            document = character_document(self.store, cid)
        finally:
            if own:
                db.rollback()
        with self._files:
            with self._state:
                if sequence <= self._written.get(cid, 0):
                    return
                self._written[cid] = sequence
            if document is not None:
                atomic_json(self.path(cid), document)

    def start(self):
        with self._state:
            if self._thread is not None:
                return
            self._stopping = False
            self._thread = threading.Thread(target=self._run, name='wow-status-archives',
                                            daemon=True)
            self._thread.start()

    def _run(self):
        try:
            while True:
                with self._state:
                    while not self._dirty and not self._stopping:
                        self._changed.wait()
                    if self._stopping:
                        # Cleared with the check, so a later mark() rebuilds in its caller.
                        # What is still marked waits for the startup rebuild: withdrawn
                        # data never waits here, as its mark rebuilds at once.
                        self._thread = None
                        self._dirty.clear()
                        self._changed.notify_all()
                        return
                    cid = next(iter(self._dirty))
                    del self._dirty[cid]
                    self._busy = True
                try:
                    self._rebuild(cid)
                except Exception as exc:
                    # The database stays the source of truth; the next mark or the
                    # startup rebuild writes this archive again. Never log its content.
                    log.error('Character archive could not be written (%s)', type(exc).__name__)
                finally:
                    with self._state:
                        self._busy = False
                        self._changed.notify_all()
        except BaseException:
            log.error('Archive thread stopped unexpectedly')
            raise
        finally:
            # Nothing may stay marked for a thread that is gone; the next startup
            # rebuild writes what was.
            with self._state:
                if self._thread is threading.current_thread():
                    self._thread = None
                self._dirty.clear()
                self._busy = False
                self._changed.notify_all()
            self.store.close_thread_connection()

    def flush(self):
        """Wait until every marked archive is written."""
        with self._state:
            while self._thread is not None and (self._dirty or self._busy):
                self._changed.wait(1)

    def stop(self):
        """End the thread once the rebuild in progress is written; later marks rebuild at
        once. A shutdown doesn't wait for every marked archive, since startup rebuilds
        them all."""
        with self._state:
            thread = self._thread
            if thread is None:
                return
            self._stopping = True
            self._changed.notify_all()
        thread.join()


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
