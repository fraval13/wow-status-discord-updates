"""Shared-journal relay (#49): dated level/death checkpoints observed in game.

Opted-in companions upload the group-scoped entries of their account's activity
log, including friends' entries that were shared with that group in game. Rows
keep the original event ID and time and are deduplicated per group database and
client edition, whichever companion uploads them first. Only level and death
checkpoints are kept: they feed the daily cumulative status report for
characters that never upload directly, and add dated checkpoints for those that do.
"""
import re
import time

from .schema import LEVEL_CAPS, ValidationError, integer, string

KINDS = ('level', 'death')
MAX_ENTRIES = 500
EVENT_ID = re.compile(r'[A-Za-z0-9:._-]{1,96}')
SENDER = re.compile(r'[^\s|\-]{1,40}-[^\s|]{1,40}')
DEATHS = re.compile(r'Total deaths: (\d{1,6})')
EARLIEST = 1_577_836_800  # 2020-01-01

SCHEMA = '''
CREATE TABLE IF NOT EXISTS journal_entries(
    client TEXT NOT NULL, id TEXT NOT NULL, sender TEXT NOT NULL, sender_key TEXT NOT NULL,
    kind TEXT NOT NULL, at INTEGER NOT NULL, level INTEGER, deaths INTEGER,
    received INTEGER NOT NULL, uploader TEXT NOT NULL, PRIMARY KEY(client,id));
CREATE INDEX IF NOT EXISTS journal_entries_sender ON journal_entries(client,sender_key,at);
CREATE INDEX IF NOT EXISTS journal_entries_received ON journal_entries(received,at);
CREATE TABLE IF NOT EXISTS status_report_peer_rows(
    day TEXT NOT NULL, timezone TEXT NOT NULL, peer TEXT NOT NULL, state TEXT NOT NULL,
    PRIMARY KEY(day,timezone,peer),
    FOREIGN KEY(day,timezone) REFERENCES status_reports(day,timezone) ON DELETE CASCADE);
'''


def sender_key(sender):
    return sender.casefold().replace(' ', '')


def entries(payload, now=None):
    """Validated rows from one upload; unusable entries are skipped, not fatal."""
    now = int(now or time.time())
    if not isinstance(payload, dict):
        raise ValidationError('Invalid journal upload')
    client = payload.get('client')
    if client not in LEVEL_CAPS:
        raise ValidationError('Invalid client')
    items = payload.get('entries')
    if not isinstance(items, list) or len(items) > MAX_ENTRIES:
        raise ValidationError('Invalid journal entries')
    rows = []
    for item in items:
        try:
            if not isinstance(item, dict) or item.get('kind') not in KINDS:
                continue
            event_id = string(item.get('id'), 'event ID', 96)
            sender = string(item.get('sender'), 'sender', 81)
            if not EVENT_ID.fullmatch(event_id) or not SENDER.fullmatch(sender):
                continue
            at = integer(item.get('at'), 'time', EARLIEST, now + 86_400)
            level = deaths = None
            if item['kind'] == 'level':
                level = integer(item.get('level'), 'level', 1, LEVEL_CAPS[client])
            else:
                match = DEATHS.fullmatch(item.get('text') or '') if isinstance(item.get('text'), str) else None
                deaths = int(match.group(1)) if match else None
            rows.append((client, event_id, sender, sender_key(sender), item['kind'], at, level, deaths))
        except ValidationError:
            continue
    return rows


def ingest(store, owner, payload, now=None):
    now = int(now or time.time())
    rows = entries(payload, now)
    with store.db:
        added = 0
        for row in rows:
            added += store.db.execute(
                'INSERT OR IGNORE INTO journal_entries'
                '(client,id,sender,sender_key,kind,at,level,deaths,received,uploader) '
                'VALUES(?,?,?,?,?,?,?,?,?,?)', (*row, now, owner)).rowcount
    return {'status': 'accepted', 'entries': len(rows), 'new': added}


def checkpoint(store, client, key, cutoff):
    """Highest level and recorded death total before cutoff, and the newest time."""
    row = store.db.execute('''SELECT max(level) AS level, max(deaths) AS deaths, max(at) AS observed
        FROM journal_entries WHERE client=? AND sender_key=? AND at<?''', (client, key, cutoff)).fetchone()
    return (row['level'], row['deaths'], row['observed']) if row else (None, None, None)
