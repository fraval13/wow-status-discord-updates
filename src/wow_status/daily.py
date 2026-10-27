"""Daily recap windows use Oslo local midnight, including 23/25-hour DST days."""
import json
from collections import Counter
from datetime import date, datetime, time as day_time, timedelta
from zoneinfo import ZoneInfo

from .archive import TIMEZONE, event_document, fields_document, timestamp
from .formatting import safe


def window(day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    zone = ZoneInfo(TIMEZONE)
    start = datetime.combine(day, day_time.min, zone)
    end = datetime.combine(day + timedelta(days=1), day_time.min, zone)
    return int(start.timestamp()), int(end.timestamp())


def report(store, cid, day, generated=None):
    start, end = window(day)
    row = store.db.execute('SELECT * FROM characters WHERE id=?', (cid,)).fetchone()
    if not row:
        return None
    char = store.decode(row)
    if not char['settings']['enabled']:
        return None
    cutoff = min(generated if generated is not None else int(datetime.now().timestamp()), end + 300)
    snapshots = store.db.execute('''SELECT * FROM snapshots WHERE character=? AND exported<?
        AND uploaded<=? ORDER BY exported,id''', (cid, end, cutoff)).fetchall()
    latest = snapshots[-1] if snapshots else None
    events = store.db.execute('''SELECT * FROM events WHERE character=? AND suppressed=0
        AND received<=? AND ((at>=? AND at<? AND received<?)
        OR (at<? AND received>=? AND received<?))
        ORDER BY at,id''', (cid, cutoff, start, end, end + 300, start, start + 300, end + 300)).fetchall()
    return {
        'schema_version': 1, 'timezone': TIMEZONE, 'day': str(day),
        'window_start': timestamp(start), 'window_end_exclusive': timestamp(end),
        'character_id': cid, 'identity': char['identity'],
        'profile_at_day_end': fields_document(json.loads(latest['snapshot'])) if latest else {},
        'last_known_export_at': timestamp(latest['exported']) if latest else None,
        'snapshot_exports': sum(start <= row['exported'] < end for row in snapshots),
        'event_counts': dict(Counter(row['kind'] for row in events)),
        'events': [{'event_id': row['id'], 'type': row['kind'],
                    'recorded_at': timestamp(row['at']), 'first_uploaded_at': timestamp(row['received']),
                    'late_upload': row['at'] < start, 'data': event_document(json.loads(row['data']))} for row in events],
    }


def render(recap):
    identity, profile = recap['identity'], recap['profile_at_day_end']
    lines = [f"**Daily recap · {recap['day']} · Europe/Oslo**",
             f"**{safe(identity['name'])}** · {safe(identity['realm'])} · {safe(identity['client'])}"]
    details = ' · '.join(f'{key.title()}: {safe(profile[key])}'
                         for key in ('level', 'class', 'race', 'guild') if key in profile)
    if details:
        lines.append(details)
    counts = recap['event_counts']
    if not counts:
        lines.append('No recorded events received for this day. This does not prove inactivity.')
    else:
        lines.append('Recorded: ' + ', '.join(f'{key}: {value}' for key, value in sorted(counts.items())))
        levels = [e for e in recap['events'] if e['type'] == 'level']
        if levels:
            lines.append('Levels: ' + ', '.join(
                f"{e['data']['level']} at {e['recorded_at']['iso'][11:16]}"
                + (' (late upload)' if e['late_upload'] else '') for e in levels[:12]))
        for event in [e for e in recap['events'] if e['type'] in ('loot', 'equipment', 'lfg')][:4]:
            value = event['data'].get('item', event['data'].get('text', ''))
            lines.append(f"{event['type'].title()}: {safe(value)[:200]}")
        late = sum(e['late_upload'] for e in recap['events'])
        if late:
            lines.append(f'{late} event(s) arrived late from earlier days; dates are kept in JSON.')
    known = recap['last_known_export_at']
    if known:
        lines.append(f"Last known export: {known['iso']}. Full consented history is saved in JSON.")
    return '\n'.join(lines)[:1900]


class DailyRecaps:
    def __init__(self, store):
        self.store = store

    def prepare(self, day, generated=None):
        start, end = window(day)
        generated = generated if generated is not None else int(datetime.now().timestamp())
        with self.store.db:
            inserted = self.store.db.execute('INSERT OR IGNORE INTO digests '
                '(day,timezone,start,end,generated) VALUES(?,?,?,?,?)',
                (str(day), TIMEZONE, start, end, generated)).rowcount
            if not inserted:
                return
            # Include every enrolled, currently shared character already known by day's end.
            for char in self.store.characters():
                first = self.store.db.execute('SELECT min(uploaded) FROM snapshots WHERE character=?',
                                               (char['id'],)).fetchone()[0]
                if char['settings']['enabled'] and first is not None and first < end:
                    self.store.db.execute('INSERT INTO digest_parts(day,timezone,character) '
                                          'VALUES(?,?,?)', (str(day), TIMEZONE, char['id']))
        self.store.sync_archives()

    def schedule(self, now=None):
        now = now or datetime.now(ZoneInfo(TIMEZONE))
        now = now.astimezone(ZoneInfo(TIMEZONE))
        due = now.date() - timedelta(days=1 if now.time() >= day_time(0, 5) else 2)
        first = self.store.db.execute('SELECT min(uploaded) FROM snapshots').fetchone()[0]
        if first is None:
            return
        cursor_key = 'daily_cursor:' + TIMEZONE
        cursor = self.store.db.execute('SELECT value FROM meta WHERE key=?', (cursor_key,)).fetchone()
        candidate = (date.fromisoformat(cursor['value']) + timedelta(days=1) if cursor else
                     datetime.fromtimestamp(first, ZoneInfo(TIMEZONE)).date())
        # Bound work per tick; subsequent ticks continue catching up after downtime.
        for _ in range(7):
            if candidate > due:
                break
            self.prepare(candidate, int(now.timestamp()))
            with self.store.db:
                self.store.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',
                                      (cursor_key, candidate.isoformat()))
            candidate += timedelta(days=1)

    def pending(self):
        row = self.store.db.execute('''SELECT p.*,d.generated FROM digest_parts p
            JOIN digests d USING(day,timezone) JOIN characters c ON c.id=p.character
            WHERE p.status='pending' AND d.next_try<=? ORDER BY p.day,p.character LIMIT 1''',
            (datetime.now().timestamp(),)).fetchone()
        if row is None:
            return None
        recap = report(self.store, row['character'], row['day'], row['generated'])
        if recap is None:
            self.delivery(dict(row), 'discarded')
            return None
        return {'key': dict(row), 'report': recap, 'text': render(recap)}

    def delivery(self, key, status, message_id=None, delay=0):
        with self.store.db:
            self.store.db.execute('UPDATE digest_parts SET status=?,message_id=? '
                'WHERE day=? AND timezone=? AND character=?',
                (status, message_id, key['day'], key['timezone'], key['character']))
            if delay:
                self.store.db.execute('UPDATE digests SET next_try=? WHERE day=? AND timezone=?',
                    (datetime.now().timestamp() + delay, key['day'], key['timezone']))
        self.store.sync_archive(key['character'])
