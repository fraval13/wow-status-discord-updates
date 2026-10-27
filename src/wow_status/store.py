"""Transactional enrollment, privacy, deduplication and announcement outbox."""
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path

from .schema import ValidationError, should_announce, validate


class Conflict(ValidationError):
    pass


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.archive_directory = Path(path).parent / (Path(path).stem + '-characters')
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS group_pauses(owner TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS level_tracking(
            character TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS people(
            owner TEXT PRIMARY KEY, display_name TEXT NOT NULL, nickname TEXT,
            source TEXT NOT NULL DEFAULT 'discord');
        CREATE TABLE IF NOT EXISTS character_labels(
            character TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'alt', source TEXT NOT NULL DEFAULT 'addon');
        CREATE TABLE IF NOT EXISTS community_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS weekly_parts(
            week TEXT NOT NULL, character TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            generated INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', message_id TEXT,
            next_try REAL NOT NULL DEFAULT 0, PRIMARY KEY(week,character));
        CREATE TABLE IF NOT EXISTS installations(
            token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS links(
            code_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS characters(
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, identity TEXT NOT NULL,
            settings TEXT NOT NULL, snapshot TEXT NOT NULL, exported INTEGER NOT NULL,
            uploaded INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
            character TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            id TEXT NOT NULL, kind TEXT NOT NULL, at INTEGER NOT NULL, received INTEGER NOT NULL,
            data TEXT NOT NULL, suppressed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(character,id));
        CREATE TABLE IF NOT EXISTS outbox(
            id INTEGER PRIMARY KEY, character TEXT NOT NULL
            REFERENCES characters(id) ON DELETE CASCADE, event_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            next_try REAL NOT NULL DEFAULT 0, message_id TEXT,
            UNIQUE(character,event_id));
        CREATE TABLE IF NOT EXISTS snapshots(
            id TEXT PRIMARY KEY, character TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            exported INTEGER NOT NULL, uploaded INTEGER NOT NULL,
            snapshot TEXT NOT NULL, settings TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS snapshots_character_time ON snapshots(character,exported);
        CREATE INDEX IF NOT EXISTS events_character_time ON events(character,at);
        CREATE TABLE IF NOT EXISTS digests(
            day TEXT NOT NULL, timezone TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
            generated INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', next_try REAL NOT NULL DEFAULT 0,
            PRIMARY KEY(day,timezone));
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS digest_parts(
            day TEXT NOT NULL, timezone TEXT NOT NULL, character TEXT NOT NULL
            REFERENCES characters(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending', message_id TEXT,
            PRIMARY KEY(day,timezone,character),
            FOREIGN KEY(day,timezone) REFERENCES digests(day,timezone) ON DELETE CASCADE);
        ''')
        if 'source' not in {row['name'] for row in self.db.execute('PRAGMA table_info(people)')}:
            self.db.execute("ALTER TABLE people ADD COLUMN source TEXT NOT NULL DEFAULT 'discord'")
        # A previous process might have died after sending but before recording success.
        with self.db:
            self.db.execute("UPDATE outbox SET status='uncertain' WHERE status='sending'")
            self.db.execute("UPDATE digest_parts SET status='uncertain' WHERE status='sending'")
            self.db.execute("UPDATE weekly_parts SET status='uncertain' WHERE status='sending'")
        self.sync_archives()
        known = {char['id'] for char in self.characters()}
        for archive in self.archive_directory.glob('*.json'):
            if archive.stem not in known:
                archive.unlink()

    def close(self):
        self.db.close()

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def character_id(identity):
        return Store.digest(json.dumps([identity['client'], identity['realm'], identity['guid']]))

    def create_link(self, owner):
        code = secrets.token_urlsafe(18)
        with self.db:
            self.db.execute('DELETE FROM links WHERE owner=? OR expires<?', (owner, time.time()))
            self.db.execute('INSERT INTO links VALUES(?,?,?)',
                            (self.digest(code), owner, int(time.time()) + 600))
        return code

    def redeem(self, code):
        with self.db:
            row = self.db.execute('SELECT * FROM links WHERE code_hash=? AND expires>?',
                                  (self.digest(code), time.time())).fetchone()
            if not row:
                raise ValidationError('Invalid or expired linking code')
            token = secrets.token_urlsafe(40)
            self.db.execute('INSERT INTO installations VALUES(?,?,?)',
                            (self.digest(token), row['owner'], int(time.time())))
            self.db.execute('DELETE FROM links WHERE code_hash=?', (self.digest(code),))
        return token

    def owner(self, token):
        row = self.db.execute('SELECT owner FROM installations WHERE token_hash=?',
                              (self.digest(token),)).fetchone()
        return row['owner'] if row else None

    def ingest(self, owner, payload):
        p = validate(payload)
        cid = self.character_id(p['identity'])
        now = int(time.time())
        with self.db:
            old = self.db.execute('SELECT * FROM characters WHERE id=?', (cid,)).fetchone()
            if not old and not p['settings']['enabled']:
                return {'character_id': cid, 'accepted': 0}
            if old and old['owner'] != owner:
                raise Conflict('Character already belongs to another linked user')
            if old and p['exported_at'] < old['exported']:
                raise Conflict('Stale export rejected; export current settings with /reload')
            self.db.execute('''INSERT INTO characters VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET identity=excluded.identity,
                settings=excluded.settings,snapshot=excluded.snapshot,
                exported=excluded.exported,uploaded=excluded.uploaded''',
                (cid, owner, json.dumps(p['identity']), json.dumps(p['settings']),
                 json.dumps(p['snapshot']), p['exported_at'], now))
            if (not p['settings']['enabled'] or not p['settings']['fields']['level']
                    or not p['settings']['collection']['level']):
                self.db.execute('DELETE FROM level_tracking WHERE character=?', (cid,))
            elif 'tracking' in p:
                self.db.execute('INSERT OR REPLACE INTO level_tracking VALUES(?,?)',
                                (cid, json.dumps(p['tracking'])))
            # Archive each distinct consented export; retries do not create extra history.
            snapshot_id = self.digest(json.dumps([cid, p['exported_at'], p['snapshot'],
                                                  p['settings']], sort_keys=True))
            self.db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?)',
                            (snapshot_id, cid, p['exported_at'], now,
                             json.dumps(p['snapshot']), json.dumps(p['settings'])))
            # Privacy changes scrub old snapshots too, without discarding permitted history.
            if old and json.loads(old['settings']) != p['settings']:
                for row in self.db.execute('SELECT * FROM snapshots WHERE character=?', (cid,)).fetchall():
                    old_snapshot = json.loads(row['snapshot'])
                    kept = {k: v for k, v in old_snapshot.items()
                            if p['settings']['enabled'] and p['settings']['fields'].get(k)}
                    self.db.execute('UPDATE snapshots SET snapshot=? WHERE id=?',
                                    (json.dumps(kept), row['id']))
            if not p['settings']['enabled']:
                self.db.execute("UPDATE digest_parts SET status='discarded' WHERE character=? "
                                "AND status IN ('pending','uncertain','failed')", (cid,))
                self.db.execute("UPDATE weekly_parts SET status='discarded' WHERE character=? "
                                "AND status IN ('pending','uncertain','failed')", (cid,))
            # Purge disabled categories and hidden event data, including already delivered history.
            if old and json.loads(old['settings']) != p['settings']:
                for row in self.db.execute('SELECT * FROM events WHERE character=?', (cid,)).fetchall():
                    if row['suppressed']:
                        continue
                    candidate = {key: p[key] for key in
                                 ('version', 'identity', 'settings', 'exported_at')}
                    candidate['events'] = [{'id': row['id'], 'kind': row['kind'],
                                            'at': row['at'], 'data': json.loads(row['data'])}]
                    try:
                        permitted = validate(candidate)['events']
                    except ValidationError:
                        permitted = []
                    if permitted and not self.should_announce(p['settings'], permitted[0]):
                        self.db.execute("DELETE FROM outbox WHERE character=? AND event_id=? "
                                        "AND status NOT IN ('sent','simulated')", (cid, row['id']))
                    if not permitted:
                        self.db.execute('DELETE FROM outbox WHERE character=? AND event_id=?',
                                        (cid, row['id']))
                        # Keep an empty deduplication marker; never resurrect a discarded event.
                        self.db.execute("UPDATE events SET data='{}',suppressed=1 WHERE character=? AND id=?",
                                        (cid, row['id']))
            accepted = 0
            for event in p['events']:
                eid = 'introduction' if event['kind'] == 'introduction' else event['id']
                inserted = self.db.execute('INSERT OR IGNORE INTO events(character,id,kind,at,received,data) VALUES(?,?,?,?,?,?)',
                    (cid, eid, event['kind'], event['at'], now, json.dumps(event['data']))).rowcount
                if inserted and self.should_announce(p['settings'], event):
                    self.db.execute('INSERT INTO outbox(character,event_id) VALUES(?,?)', (cid, eid))
                accepted += inserted
        from .people import set_role
        role = p['settings'].get('character_role')
        old_role = self.db.execute('SELECT source,role FROM character_labels WHERE character=?',
                                   (cid,)).fetchone()
        discord_main = self.db.execute("SELECT 1 FROM character_labels l JOIN characters c "
            "ON c.id=l.character WHERE c.owner=? AND l.source='discord' AND l.role='main'",
            (owner,)).fetchone()
        if role and not discord_main and (not old_role or old_role['source'] == 'addon'):
            if not old_role or old_role['role'] != role:
                set_role(self, owner, cid, role, source='addon')
        self.sync_archive(cid)
        return {'character_id': cid, 'accepted': accepted}

    def characters(self, owner=None):
        rows = self.db.execute('SELECT * FROM characters' + (' WHERE owner=?' if owner else '')
                               + ' ORDER BY uploaded DESC', (owner,) if owner else ()).fetchall()
        return [self.decode(row) for row in rows]

    @staticmethod
    def decode(row):
        data = dict(row)
        for key in ('identity', 'settings', 'snapshot'):
            data[key] = json.loads(data[key])
        return data

    def activity(self, cid):
        rows = self.db.execute('''SELECT e.* FROM events e
            WHERE e.character=? AND e.suppressed=0 ORDER BY e.at DESC LIMIT 20''',
            (cid,)).fetchall()
        return [dict(row, data=json.loads(row['data'])) for row in rows]

    def pause(self, owner, cid=None):
        with self.db:
            for char in self.characters(owner):
                if cid and char['id'] != cid:
                    continue
                char['settings']['enabled'] = False
                self.db.execute("UPDATE characters SET settings=?,snapshot='{}' WHERE id=?",
                                (json.dumps(char['settings']), char['id']))
                self.db.execute('DELETE FROM outbox WHERE character=?', (char['id'],))
                self.db.execute('DELETE FROM level_tracking WHERE character=?', (char['id'],))
                self.db.execute("UPDATE weekly_parts SET status='discarded' WHERE character=? "
                                "AND status IN ('pending','uncertain','failed')", (char['id'],))
                self.db.execute("UPDATE snapshots SET snapshot='{}' WHERE character=?", (char['id'],))
                self.db.execute("UPDATE digest_parts SET status='discarded' WHERE character=? "
                                "AND status IN ('pending','uncertain','failed')", (char['id'],))
                self.db.execute("UPDATE events SET data='{}',suppressed=1 WHERE character=?", (char['id'],))

        self.sync_archives()

    def delete(self, owner):
        ids = [char['id'] for char in self.characters(owner)]
        with self.db:
            self.db.execute('DELETE FROM characters WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM installations WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM links WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM people WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM group_pauses WHERE owner=?', (owner,))
        for cid in ids:
            (self.archive_directory / f'{cid}.json').unlink(missing_ok=True)

    def sync_archive(self, cid):
        from .archive import write_character
        write_character(self, cid)

    def sync_archives(self):
        for char in self.characters():
            self.sync_archive(char['id'])

    def pending(self):
        row = self.db.execute('''SELECT o.id AS delivery_id,e.kind,e.at,e.data,c.*
            FROM outbox o JOIN characters c ON c.id=o.character
            JOIN events e ON e.character=o.character AND e.id=o.event_id
            WHERE o.status='pending' AND e.suppressed=0 AND o.next_try<=? ORDER BY o.id LIMIT 1''',
            (time.time(),)).fetchone()
        if not row:
            return None
        item = self.decode(row)
        item['data'] = json.loads(item['data'])
        from .people import decorate
        return decorate(self, item)

    def delivery(self, delivery_id, status, delay=0, message_id=None):
        with self.db:
            self.db.execute('''UPDATE outbox SET status=?,next_try=?,message_id=?,
                attempts=attempts+? WHERE id=?''',
                (status, time.time() + delay, message_id, int(status == 'sending'), delivery_id))

        row = self.db.execute('SELECT character FROM outbox WHERE id=?',
                              (delivery_id,)).fetchone()
        if row:
            self.sync_archive(row['character'])

    def should_announce(self, settings, event):
        mode = self.community_setting('immediate_mode', 'celebrations')
        if mode == 'daily_only':
            return False
        if mode == 'celebrations' and event['kind'] not in ('introduction', 'level', 'loot'):
            return False
        if not should_announce(settings, event):
            return False
        if event['kind'] == 'level':
            interval = int(self.community_setting('level_interval', '10'))
            return event['data']['level'] % interval == 0 or event['data'].get('maximum') is True
        if event['kind'] == 'loot':
            return event['data']['quality'] >= int(self.community_setting('loot_quality', '4'))
        return True

    def community_setting(self, key, default):
        row = self.db.execute('SELECT value FROM community_settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    def set_community_setting(self, key, value):
        if key not in ('immediate_mode', 'level_interval', 'loot_quality'):
            raise ValidationError('Unknown community setting')
        if key == 'immediate_mode' and value not in ('celebrations', 'daily_only', 'all'):
            raise ValidationError('Unknown announcement mode')
        if key != 'immediate_mode':
            limit = 100 if key == 'level_interval' else 5
            low = 1 if key == 'level_interval' else 0
            if not low <= int(value) <= limit:
                raise ValidationError('Invalid community filter')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO community_settings VALUES(?,?)', (key, str(value)))
            for row in self.db.execute("SELECT o.*,e.kind,e.data,c.settings FROM outbox o "
                'JOIN events e ON e.character=o.character AND e.id=o.event_id '
                "JOIN characters c ON c.id=o.character WHERE o.status IN ('pending','failed','uncertain')").fetchall():
                event = {'kind': row['kind'], 'data': json.loads(row['data'])}
                if not self.should_announce(json.loads(row['settings']), event):
                    self.db.execute("UPDATE outbox SET status='discarded' WHERE id=?", (row['id'],))
        self.sync_archives()
