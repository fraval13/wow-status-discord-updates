"""Monday 00:05 Oslo group highlights, using the same consented records as daily recaps."""
import json
from collections import Counter
from datetime import date, datetime, time as day_time, timedelta
from zoneinfo import ZoneInfo

from .archive import TIMEZONE, timestamp
from .daily import render_group, report, window


def week_report(store, cid, week, generated):
    start_date = date.fromisoformat(week) if isinstance(week, str) else week
    days = [report(store, cid, start_date + timedelta(days=i), generated) for i in range(7)]
    if not days[0]:
        return None
    result = dict(days[-1])
    counts = Counter()
    for day in days:
        counts.update(day['event_counts'])
    result['event_counts'] = dict(counts)
    result['events'] = [event for day in days for event in day['events']]
    result['day'] = str(start_date)
    result['period'] = 'week'
    start, _ = window(start_date)
    _, end = window(start_date + timedelta(days=6))
    result['window_start'] = timestamp(start)
    result['window_end_exclusive'] = timestamp(end)
    result['snapshot_exports'] = sum(day['snapshot_exports'] for day in days)
    before = store.db.execute('SELECT snapshot FROM snapshots WHERE character=? AND exported<? '
                              'AND uploaded<=? ORDER BY exported DESC,id DESC LIMIT 1',
                              (cid, start, min(generated, end + 300))).fetchone()
    progress = {'source': 'snapshot_comparison', 'certainty': 'inferred_between_exports'}
    if before:
        previous = json.loads(before['snapshot'])
        current = result['profile_at_day_end']
        if 'level' in previous and 'level' in current and previous['level'] != current['level']:
            progress['level'] = {'from': previous['level'], 'to': current['level']}
    result['progress_between_exports'] = progress
    return result


class WeeklyRecaps:
    def __init__(self, store):
        self.store = store

    def prepare(self, week, generated=None):
        week = date.fromisoformat(week) if isinstance(week, str) else week
        if week.weekday() != 0:
            raise ValueError('Week must start on a Monday')
        generated = generated if generated is not None else int(datetime.now().timestamp())
        _, end = window(week + timedelta(days=6))
        with self.store.db:
            for char in self.store.characters():
                first = self.store.db.execute('SELECT min(uploaded) FROM snapshots WHERE character=?',
                                               (char['id'],)).fetchone()[0]
                if char['settings']['enabled'] and first is not None and first < end:
                    self.store.db.execute('INSERT OR IGNORE INTO weekly_parts(week,character,generated) '
                                          'VALUES(?,?,?)', (str(week), char['id'], generated))
        self.store.sync_archives()

    def schedule(self, now=None):
        now = (now or datetime.now(ZoneInfo(TIMEZONE))).astimezone(ZoneInfo(TIMEZONE))
        due = now.date() - timedelta(days=now.weekday() + 7)
        if now.weekday() == 0 and now.time() < day_time(0, 5):
            due -= timedelta(days=7)
        first = self.store.db.execute('SELECT min(uploaded) FROM snapshots').fetchone()[0]
        if first is None:
            return
        key = 'weekly_cursor:' + TIMEZONE
        cursor = self.store.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        if cursor:
            candidate = date.fromisoformat(cursor['value']) + timedelta(days=7)
        else:
            candidate = datetime.fromtimestamp(first, ZoneInfo(TIMEZONE)).date()
            candidate -= timedelta(days=candidate.weekday())
        for _ in range(4):
            if candidate > due:
                break
            self.prepare(candidate, int(now.timestamp()))
            with self.store.db:
                self.store.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, str(candidate)))
            candidate += timedelta(days=7)

    def pending(self):
        rows = self.store.db.execute("SELECT * FROM weekly_parts WHERE status='pending' "
            'AND next_try<=? ORDER BY week,character LIMIT 25', (datetime.now().timestamp(),)).fetchall()
        reports, members = [], []
        week = rows[0]['week'] if rows else None
        for row in rows:
            if row['week'] != week:
                break
            recap = week_report(self.store, row['character'], week, row['generated'])
            if recap is None:
                self.delivery({'week': week, 'character': row['character']}, 'discarded')
                continue
            candidate = render_group(self.store, reports + [recap],
                                     f'Weekly adventures · week of {week}')
            if reports and len(candidate) > 1950:
                break
            reports.append(recap)
            members.append(row['character'])
        if not reports:
            return None
        return {'key': {'week': week, 'characters': members, 'character': members[0]},
                'reports': reports, 'report': reports[0],
                'text': render_group(self.store, reports, f'Weekly adventures · week of {week}')}

    def delivery(self, key, status, message_id=None, delay=0):
        members = key.get('characters', [key['character']])
        with self.store.db:
            for cid in members:
                self.store.db.execute('UPDATE weekly_parts SET status=?,message_id=?,next_try=? '
                    'WHERE week=? AND character=?',
                    (status, message_id, datetime.now().timestamp() + delay, key['week'], cid))
        for cid in members:
            self.store.sync_archive(cid)
