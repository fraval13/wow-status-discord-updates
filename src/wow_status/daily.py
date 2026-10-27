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
    baseline_rows = [row for row in snapshots if row['exported'] < start]
    baseline = baseline_rows[-1] if baseline_rows else None
    before = json.loads(baseline['snapshot']) if baseline else {}
    after = json.loads(latest['snapshot']) if latest else {}
    progress = {'source': 'snapshot_comparison', 'certainty': 'inferred_between_exports'}
    if 'level' in before and 'level' in after and before['level'] != after['level']:
        progress['level'] = {'from': before['level'], 'to': after['level']}
    if 'gear' in before and 'gear' in after:
        progress['equipment_slots_changed'] = [slot for slot, item in after['gear'].items()
                                                if before['gear'].get(slot) != item]
    events = store.db.execute('''SELECT * FROM events WHERE character=? AND suppressed=0
        AND received<=? AND ((at>=? AND at<? AND received<?)
        OR (at<? AND received>=? AND received<?))
        ORDER BY at,id''', (cid, cutoff, start, end, end + 300, start, start + 300, end + 300)).fetchall()
    events = [row for row in events if json.loads(row['data']).get('synthetic') is not True]
    return {
        'schema_version': 1, 'timezone': TIMEZONE, 'day': str(day),
        'window_start': timestamp(start), 'window_end_exclusive': timestamp(end),
        'character_id': cid, 'owner': char['owner'], 'identity': char['identity'],
        'progress_between_exports': progress,
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
        first = self.store.db.execute("SELECT day FROM digest_parts WHERE status='pending' "
                                      'ORDER BY day LIMIT 1').fetchone()
        if first is None:
            return None
        rows = self.store.db.execute('''SELECT p.*,d.generated FROM digest_parts p
            JOIN digests d USING(day,timezone) JOIN characters c ON c.id=p.character
            WHERE p.status='pending' AND p.day=? AND d.next_try<=?
            ORDER BY c.owner,p.character LIMIT 25''',
            (first['day'], datetime.now().timestamp())).fetchall()
        reports, members = [], []
        for row in rows:
            recap = report(self.store, row['character'], row['day'], row['generated'])
            if recap is None:
                self.delivery(dict(row), 'discarded')
                continue
            candidate = render_group(self.store, reports + [recap], f"Daily recap · {first['day']}")
            if reports and len(candidate) > 1950:
                break
            reports.append(recap)
            members.append(row['character'])
        if not reports:
            return None
        key = {'day': first['day'], 'timezone': TIMEZONE,
               'character': members[0], 'characters': members}
        return {'key': key, 'report': reports[0], 'reports': reports,
                'text': render_group(self.store, reports, f"Daily recap · {first['day']}")}

    def delivery(self, key, status, message_id=None, delay=0):
        with self.store.db:
            for cid in key.get('characters', [key['character']]):
                self.store.db.execute('UPDATE digest_parts SET status=?,message_id=? '
                'WHERE day=? AND timezone=? AND character=?',
                (status, message_id, key['day'], key['timezone'], cid))
            if delay:
                self.store.db.execute('UPDATE digests SET next_try=? WHERE day=? AND timezone=?',
                    (datetime.now().timestamp() + delay, key['day'], key['timezone']))
        for cid in key.get('characters', [key['character']]):
            self.store.sync_archive(cid)


def render_group(store, reports, title):
    from .people import character_role, person
    ordered = sorted(reports, key=lambda r: (person(store, r['owner'])['display_name'].casefold(),
                                             r['owner'], character_role(store, r['character_id']) != 'main',
                                             r['identity']['name'].casefold()))
    counts = Counter()
    for recap in reports:
        counts.update(recap['event_counts'])
    lines = [f'**{title} · Europe/Oslo**',
             f"Group highlights on this page: {counts['level']} level-ups, "
             f"{counts['loot']} loot events, {counts['introduction']} new adventurers."]
    previous = None
    for recap in ordered:
        if previous != recap['owner']:
            lines.append('\n**' + safe(person(store, recap['owner'])['display_name'])[:90] + '**')
        identity, snapshot = recap['identity'], recap['profile_at_day_end']
        role = character_role(store, recap['character_id'])
        level = f" · level {snapshot['level']}" if 'level' in snapshot else ''
        klass = f" {safe(snapshot['class'])[:35]}" if 'class' in snapshot else ''
        lines.append(f"• **{safe(identity['name'])[:70]}** ({role}){level}{klass} · "
                     f"{safe(identity['realm'])[:60]}")
        progress = recap['progress_between_exports']
        changes = []
        if 'level' in progress:
            change = progress['level']
            changes.append(f"level {change['from']} → {change['to']} (snapshot comparison)")
        if progress.get('equipment_slots_changed'):
            changes.append(f"{len(progress['equipment_slots_changed'])} equipment slots changed (snapshots)")
        events = recap['event_counts']
        if events:
            changes.append(', '.join(f'{kind}: {count}' for kind, count in sorted(events.items())))
        else:
            changes.append('no recorded events; this does not prove inactivity')
        lines.append('  ' + '; '.join(changes)[:260])
        items = [e for e in recap['events'] if e['type'] == 'loot']
        if items:
            best = max(items, key=lambda e: e['data'].get('quality', 0))
            lines.append('  Loot highlight: ' + safe(best['data']['item'])[:90])
        known = recap['last_known_export_at']
        if known:
            lines.append('  Last export: ' + known['iso'])
        previous = recap['owner']
    lines.append('\nFull timelines and level-up times are kept in each character’s JSON.')
    return '\n'.join(lines)
