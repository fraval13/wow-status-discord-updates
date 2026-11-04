"""Upload-triggered cumulative group standings, frozen once per group day."""
import json
from datetime import datetime, timedelta
from datetime import time as day_time
from zoneinfo import ZoneInfo

from .archive import TIMEZONE

# An observation this far before the cutoff is shown with its date instead of
# being presented as the character's present state.
STALE_SECONDS = 172_800


def midnight(day):
    return int(datetime.combine(day, day_time.min, ZoneInfo(TIMEZONE)).timestamp())


def state(store, cid, cutoff):
    """Cumulative level/deaths from consented observations strictly before cutoff."""
    level = deaths = None
    observed = None
    identity = klass = None
    row = store.db.execute('SELECT identity FROM characters WHERE id=?', (cid,)).fetchone()
    if row:
        identity = json.loads(row['identity'])
    snapshot = store.db.execute('SELECT * FROM snapshots WHERE character=? AND exported<? '
                                'ORDER BY exported DESC,id DESC LIMIT 1', (cid, cutoff)).fetchone()
    if snapshot:
        fields = json.loads(snapshot['snapshot'])
        # Absence means the field was never consented or never observed, not zero.
        level = fields.get('level')
        deaths = fields.get('deaths')
        klass = fields.get('class_id') or fields.get('class')
        observed = snapshot['exported']
    for kind, key, current in (('level', 'level', level), ('death', 'total_deaths', deaths)):
        event = store.db.execute('''SELECT at,data FROM events WHERE character=? AND kind=?
            AND suppressed=0 AND at<? ORDER BY at DESC,id DESC LIMIT 1''',
            (cid, kind, cutoff)).fetchone()
        if event is None:
            continue
        data = json.loads(event['data'])
        if data.get('synthetic') is True or key not in data:
            continue
        # Both values are cumulative, so a later event cannot lower them.
        value = data[key] if current is None else max(current, data[key])
        if kind == 'level':
            level = value
        else:
            deaths = value
        observed = event['at'] if observed is None else max(observed, event['at'])
    return {'character_id': cid, 'identity': identity or {}, 'class': klass,
            'level': level, 'deaths': deaths, 'observed': observed,
            'stale': observed is not None and observed < cutoff - STALE_SECONDS}


def level_order(row):
    identity = row['identity']
    return (row['level'] is None, -(row['level'] or 0),
            identity.get('name', '').casefold(), identity.get('realm', '').casefold(),
            identity.get('client', '').casefold())


def death_order(row):
    identity = row['identity']
    return (row['deaths'] is None, -(row['deaths'] or 0),
            identity.get('name', '').casefold(), identity.get('realm', '').casefold(),
            identity.get('client', '').casefold())


class GroupStatusReports:
    """One frozen cumulative report per group day, suppressed when nothing changed."""

    def __init__(self, store):
        self.store = store

    def covered_until(self):
        row = self.store.db.execute('SELECT max(cutoff) AS cutoff FROM status_reports').fetchone()
        return row['cutoff'] if row and row['cutoff'] is not None else 0

    def new_observations(self, since, cutoff):
        """True when data covering this report's own period arrived after the cutoff."""
        snapshot = self.store.db.execute('SELECT 1 FROM snapshots WHERE uploaded>=? AND exported<? '
                                         'AND exported>=? LIMIT 1', (cutoff, cutoff, since)).fetchone()
        if snapshot:
            return True
        event = self.store.db.execute('''SELECT 1 FROM events WHERE received>=? AND at<? AND at>=?
            AND suppressed=0 LIMIT 1''', (cutoff, cutoff, since)).fetchone()
        return event is not None

    def prepare(self, now=None):
        now = (now or datetime.now(ZoneInfo(TIMEZONE))).astimezone(ZoneInfo(TIMEZONE))
        day = now.date() - timedelta(days=1)
        cutoff = midnight(now.date())
        if int(now.timestamp()) < cutoff:
            return
        if self.store.db.execute('SELECT 1 FROM status_reports WHERE day=? AND timezone=?',
                                 (str(day), TIMEZONE)).fetchone():
            return
        since = self.covered_until()
        if not self.new_observations(since, cutoff):
            return
        rows = []
        for char in self.store.characters():
            if not char['settings']['enabled']:
                continue
            row = state(self.store, char['id'], cutoff)
            if row['observed'] is None:
                continue
            rows.append(row)
        if not rows:
            return
        with self.store.db:
            inserted = self.store.db.execute('INSERT OR IGNORE INTO status_reports'
                '(day,timezone,cutoff,covers_from,generated) VALUES(?,?,?,?,?)',
                (str(day), TIMEZONE, cutoff, since, int(now.timestamp()))).rowcount
            if not inserted:
                return
            for row in rows:
                self.store.db.execute('INSERT INTO status_report_rows(day,timezone,character,state) '
                                      'VALUES(?,?,?,?)', (str(day), TIMEZONE, row['character_id'],
                                                          json.dumps(row)))

    def pending(self):
        report = self.store.db.execute('''SELECT * FROM status_reports WHERE status='pending'
            AND next_try<=? ORDER BY day LIMIT 1''', (datetime.now().timestamp(),)).fetchone()
        if report is None:
            return None
        rows = self.store.db.execute('''SELECT r.state FROM status_report_rows r
            JOIN characters c ON c.id=r.character WHERE r.day=? AND r.timezone=?''',
            (report['day'], report['timezone'])).fetchall()
        frozen = [json.loads(row['state']) for row in rows]
        # Consent withdrawn since freezing removes the character from the unsent report.
        consented = [row for row in frozen
                     if self.consented(row['character_id'])]
        if not consented:
            self.delivery({'day': report['day'], 'timezone': report['timezone']}, 'discarded')
            return None
        return {'key': {'day': report['day'], 'timezone': report['timezone']},
                'cutoff': report['cutoff'], 'rows': consented}

    def consented(self, cid):
        row = self.store.db.execute('SELECT settings FROM characters WHERE id=?', (cid,)).fetchone()
        return bool(row) and json.loads(row['settings'])['enabled']

    def delivery(self, key, status, message_ids=None, delay=0):
        with self.store.db:
            self.store.db.execute('UPDATE status_reports SET status=?,message_ids=? '
                'WHERE day=? AND timezone=?',
                (status, json.dumps(message_ids or []), key['day'], key['timezone']))
            if delay:
                self.store.db.execute('UPDATE status_reports SET next_try=? WHERE day=? AND timezone=?',
                    (datetime.now().timestamp() + delay, key['day'], key['timezone']))
