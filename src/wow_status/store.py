"""Transactional enrollment, privacy, deduplication and announcement outbox."""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path

from . import limits
from .schema import STATUS_FIELDS, ValidationError, should_announce, validate


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
        CREATE TABLE IF NOT EXISTS resource_usage(
            scope TEXT NOT NULL, bucket INTEGER NOT NULL, amount INTEGER NOT NULL,
            PRIMARY KEY(scope,bucket));
        CREATE TABLE IF NOT EXISTS posting_cooldowns(scope TEXT PRIMARY KEY, next_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS level_claims(
            character TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
            claim TEXT NOT NULL, PRIMARY KEY(character,claim));
        CREATE TABLE IF NOT EXISTS group_pauses(owner TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS level_tracking(
            character TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS people(
            owner TEXT PRIMARY KEY, display_name TEXT NOT NULL, nickname TEXT,
            source TEXT NOT NULL DEFAULT 'discord');
        CREATE TABLE IF NOT EXISTS character_claims(
            character TEXT PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
            secret_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS former_owners(
            character TEXT NOT NULL, owner TEXT NOT NULL, PRIMARY KEY(character,owner));
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
        CREATE TABLE IF NOT EXISTS upload_receipts(
            owner TEXT NOT NULL, batch TEXT NOT NULL, part INTEGER NOT NULL,
            total INTEGER NOT NULL, received INTEGER NOT NULL,
            PRIMARY KEY(owner,batch,part));
        CREATE TABLE IF NOT EXISTS outbox_batches(
            delivery INTEGER PRIMARY KEY REFERENCES outbox(id) ON DELETE CASCADE,
            owner TEXT NOT NULL, batch TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS outbox_batch_lookup ON outbox_batches(owner,batch);
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
        CREATE TABLE IF NOT EXISTS status_reports(
            day TEXT NOT NULL, timezone TEXT NOT NULL, cutoff INTEGER NOT NULL,
            covers_from INTEGER NOT NULL, generated INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', next_try REAL NOT NULL DEFAULT 0,
            message_ids TEXT NOT NULL DEFAULT '[]', PRIMARY KEY(day,timezone));
        CREATE TABLE IF NOT EXISTS status_report_rows(
            day TEXT NOT NULL, timezone TEXT NOT NULL, character TEXT NOT NULL
            REFERENCES characters(id) ON DELETE CASCADE, state TEXT NOT NULL,
            PRIMARY KEY(day,timezone,character),
            FOREIGN KEY(day,timezone) REFERENCES status_reports(day,timezone) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS digest_parts(
            day TEXT NOT NULL, timezone TEXT NOT NULL, character TEXT NOT NULL
            REFERENCES characters(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending', message_id TEXT,
            PRIMARY KEY(day,timezone,character),
            FOREIGN KEY(day,timezone) REFERENCES digests(day,timezone) ON DELETE CASCADE);
        ''')
        if 'source' not in {row['name'] for row in self.db.execute('PRAGMA table_info(people)')}:
            self.db.execute("ALTER TABLE people ADD COLUMN source TEXT NOT NULL DEFAULT 'discord'")
        self.recover_interrupted_sends()
        # Backfill deduplication markers without rewriting existing event IDs or history.
        if not self.db.execute("SELECT 1 FROM meta WHERE key='level_claims_v1'").fetchone():
            with self.db:
                for row in self.db.execute("SELECT character,data FROM events WHERE kind='level' AND suppressed=0").fetchall():
                    data = json.loads(row['data'])
                    if type(data.get('level')) is int:
                        self.db.execute('INSERT OR IGNORE INTO level_claims VALUES(?,?)',
                            (row['character'], self.level_claim(data)))
                self.db.execute("INSERT INTO meta VALUES('level_claims_v1','1')")
        self.sync_archives()
        known = {char['id'] for char in self.characters()}
        for archive in self.archive_directory.glob('*.json'):
            if archive.stem not in known:
                self.drop_archive(archive.stem)

    def close(self):
        self.db.close()

    def recover_interrupted_sends(self):
        """A process or bot session that ended after sending, but before recording
        success, may or may not have posted: mark those rows for operator review.
        Returns how many rows changed."""
        with self.db:
            return sum(self.db.execute(f"UPDATE {table} SET status='uncertain' "
                                       "WHERE status='sending'").rowcount
                       for table in ('outbox', 'digest_parts', 'weekly_parts', 'status_reports'))

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def character_id(identity):
        return Store.digest(json.dumps([identity['client'], identity['realm'], identity['guid']]))

    @staticmethod
    def claim_hash(cid, secret):
        # Bound to the character, so one stored hash never matches another character.
        return Store.digest(json.dumps(['claim', cid, secret]))

    @staticmethod
    def level_claim(data):
        # Separate local test observations from real progress. Markers contain no profile data.
        return Store.digest(f"level:{data['level']}:{data.get('synthetic') is True}")

    def request_budget(self, scope, count, seconds):
        with self.db:
            limits.charge(self.db, [(scope, count, seconds, 1)], time.time())

    def can_post(self, character=None, now=None):
        now = time.time() if now is None else now
        scopes = ['group'] + (['character:' + character] if character else [])
        return not any(self.db.execute('SELECT 1 FROM posting_cooldowns WHERE scope=? AND next_at>?',
                                      (scope, now)).fetchone() for scope in scopes)

    def reserve_post(self, character=None):
        now = time.time()
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO posting_cooldowns VALUES(?,?)',
                            ('group', now + limits.GROUP_POST_SECONDS))
            if character:
                owner = self.db.execute('SELECT owner FROM characters WHERE id=?', (character,)).fetchone()
                if owner:
                    self.db.execute('INSERT OR REPLACE INTO posting_cooldowns VALUES(?,?)',
                                    ('owner:' + owner['owner'], now))
                self.db.execute('INSERT OR REPLACE INTO posting_cooldowns VALUES(?,?)',
                                ('character:' + character, now + limits.CHARACTER_POST_SECONDS))

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

    def ingest(self, owner, payload, name=None):
        """Store one upload. ``name`` is an optional ``(display_name, source)`` owner label,
        written in the upload's transaction: a rejected upload, or one for a new character
        that stores nothing, leaves it unchanged.

        Another owner's character is taken over, with its history, only when the upload
        presents the claim secret stored for it (#11). Without one, it is a 409."""
        from .people import set_role, store_name
        p = validate(payload)
        cid = self.character_id(p['identity'])
        now = int(time.time())
        with self.db:
            old = self.db.execute('SELECT * FROM characters WHERE id=?', (cid,)).fetchone()
            if not old and not p['settings']['enabled']:
                return {'character_id': cid, 'accepted': 0}
            # An installation that lost the character can't take it back (#11).
            if self.barred(cid, owner):
                raise Conflict('Character moved to another installation; ask the operator to move it back')
            proof = self.claim_hash(cid, p['claim_secret']) if 'claim_secret' in p else None
            takeover = bool(old) and old['owner'] != owner
            if takeover:
                claimed = self.db.execute('SELECT secret_hash FROM character_claims WHERE character=?',
                                          (cid,)).fetchone()
                # A character stored before claim secrets existed needs the operator command.
                if not (proof and claimed and hmac.compare_digest(claimed['secret_hash'], proof)):
                    raise Conflict('Character already belongs to another linked user')
                # Another installation must not undo the old one's group privacy pause.
                if self.paused(old['owner']):
                    raise Conflict('Character owner paused sharing; resume from that installation')
            # A takeover needs a strictly newer export, so two installations reading the
            # same SavedVariables can't pass the character back and forth.
            if old and (p['exported_at'] <= old['exported'] if takeover
                        else p['exported_at'] < old['exported']):
                raise Conflict('Stale export rejected; export current settings with /reload')
            if takeover:
                # The previous owner's main/alt choice does not carry over, and the old
                # installation can't take the character back, even with the secret.
                self.db.execute('DELETE FROM character_labels WHERE character=?', (cid,))
                self.db.execute('INSERT OR IGNORE INTO former_owners VALUES(?,?)',
                                (cid, old['owner']))
            # Any later rejection inside this transaction rolls the label back too.
            renamed = name is not None and store_name(self.db, owner, *name)
            self.db.execute('''INSERT INTO characters(id,owner,identity,settings,snapshot,exported,uploaded) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET owner=excluded.owner,identity=excluded.identity,
                settings=excluded.settings,snapshot=excluded.snapshot,
                exported=excluded.exported,uploaded=excluded.uploaded''',
                (cid, owner, json.dumps(p['identity']), json.dumps(p['settings']),
                 json.dumps(p['snapshot']), p['exported_at'], now))
            if proof:
                # The current owner's latest secret wins, e.g. after a SavedVariables reset.
                self.db.execute('INSERT INTO character_claims VALUES(?,?) ON CONFLICT(character) '
                                'DO UPDATE SET secret_hash=excluded.secret_hash', (cid, proof))
            if (not p['settings']['enabled'] or not p['settings']['fields']['level']
                    or not p['settings']['collection']['level']):
                self.db.execute('DELETE FROM level_tracking WHERE character=?', (cid,))
            elif 'tracking' in p:
                self.db.execute('INSERT OR REPLACE INTO level_tracking VALUES(?,?)',
                                (cid, json.dumps(p['tracking'])))
            # Archive each distinct consented export; retries do not create extra history.
            snapshot_id = self.digest(json.dumps([cid, p['exported_at'], p['snapshot'],
                                                  p['settings']], sort_keys=True))
            snapshot_added = self.db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?,?,?)',
                            (snapshot_id, cid, p['exported_at'], now,
                             json.dumps(p['snapshot']), json.dumps(p['settings']))).rowcount
            # Privacy changes scrub old snapshots too, without discarding permitted history.
            if old and json.loads(old['settings']) != p['settings']:
                for row in self.db.execute('SELECT * FROM snapshots WHERE character=?', (cid,)).fetchall():
                    old_snapshot = json.loads(row['snapshot'])
                    kept = validate(dict(p, snapshot=old_snapshot, events=[]))['snapshot']
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
                    if permitted:
                        self.db.execute('UPDATE events SET data=? WHERE character=? AND id=?',
                            (json.dumps(permitted[0]['data']), cid, row['id']))
                    if permitted and not self.should_announce(p['settings'], permitted[0]):
                        self.db.execute("DELETE FROM outbox WHERE character=? AND event_id=? "
                                        "AND status NOT IN ('sent','simulated')", (cid, row['id']))
                    if not permitted:
                        self.db.execute('DELETE FROM outbox WHERE character=? AND event_id=?',
                                        (cid, row['id']))
                        # Keep an empty deduplication marker; never resurrect a discarded event.
                        self.db.execute("UPDATE events SET data='{}',suppressed=1 WHERE character=? AND id=?",
                                        (cid, row['id']))
            accepted, new_bytes = 0, 0
            batch = None
            if p['settings'].get('discord_delivery') == 'summary' and p['settings']['enabled']:
                batch = p.get('upload_batch') or self.digest(json.dumps([cid, p['exported_at']]))
                total, part = p.get('upload_parts', 1), p.get('upload_part', 1)
                previous = self.db.execute('SELECT total FROM upload_receipts WHERE owner=? AND batch=? LIMIT 1',
                                           (owner, batch)).fetchone()
                if previous and previous['total'] != total:
                    raise Conflict('Upload batch changed; export current data again')
                receipt_added = self.db.execute('INSERT OR IGNORE INTO upload_receipts VALUES(?,?,?,?,?)',
                                               (owner, batch, part, total, now)).rowcount
                new_bytes += 160 * receipt_added
                self.db.execute('''DELETE FROM upload_receipts WHERE received<? AND NOT EXISTS
                    (SELECT 1 FROM outbox_batches b JOIN outbox o ON o.id=b.delivery
                     WHERE b.owner=upload_receipts.owner AND b.batch=upload_receipts.batch AND o.status='pending')''',
                    (now - 604800,))
            for event in p['events']:
                eid = 'introduction' if event['kind'] == 'introduction' else event['id']
                claim = self.level_claim(event['data']) if event['kind'] == 'level' else None
                if claim and self.db.execute('SELECT 1 FROM level_claims WHERE character=? AND claim=?',
                                             (cid, claim)).fetchone():
                    continue
                inserted = self.db.execute('INSERT OR IGNORE INTO events(character,id,kind,at,received,data) VALUES(?,?,?,?,?,?)',
                    (cid, eid, event['kind'], event['at'], now, json.dumps(event['data']))).rowcount
                if inserted:
                    new_bytes += len(json.dumps(event).encode('utf-8'))
                    if claim:
                        self.db.execute('INSERT INTO level_claims VALUES(?,?)', (cid, claim))
                if inserted and self.should_announce(p['settings'], event):
                    cursor = self.db.execute('INSERT INTO outbox(character,event_id) VALUES(?,?)', (cid, eid))
                    if batch:
                        self.db.execute('INSERT INTO outbox_batches VALUES(?,?,?)',
                                        (cursor.lastrowid, owner, batch))
                accepted += inserted
            if batch:
                before = json.loads(old['snapshot']) if old else {}
                changed = [key for key in STATUS_FIELDS if key in p['snapshot']
                           and p['snapshot'][key] != before.get(key)]
                status_event = {'kind': 'status', 'data': {'changed': changed}}
                if changed and self.should_announce(p['settings'], status_event):
                    eid = 'status:' + self.digest(json.dumps([cid, batch]))
                    added = self.db.execute('INSERT OR IGNORE INTO events(character,id,kind,at,received,data) VALUES(?,?,?,?,?,?)',
                        (cid,eid,'status',p['exported_at'],now,json.dumps(status_event['data']))).rowcount
                    if added:
                        accepted += 1
                        new_bytes += 160
                        cursor = self.db.execute('INSERT INTO outbox(character,event_id) VALUES(?,?)',(cid,eid))
                        self.db.execute('INSERT INTO outbox_batches VALUES(?,?,?)',(cursor.lastrowid,owner,batch))
            if batch:
                # A newer complete export also absorbs any older unsent backlog for
                # this character, including legacy per-event and incomplete batches.
                self.db.execute("""INSERT OR REPLACE INTO outbox_batches(delivery,owner,batch)
                    SELECT id,?,? FROM outbox WHERE character=? AND status='pending'""", (owner, batch, cid))
                self.db.execute("UPDATE digest_parts SET status='discarded' WHERE character=? AND status='pending'", (cid,))
                self.db.execute("UPDATE weekly_parts SET status='discarded' WHERE character=? AND status='pending'", (cid,))
            # A retry costs no storage budget. Disabled-sharing uploads can always scrub
            # retained data even after the owner's daily growth budget has been exhausted.
            if p['settings']['enabled']:
                new_bytes += len(json.dumps({k: p[k] for k in
                    ('identity', 'snapshot', 'settings', 'exported_at')}).encode('utf-8')) if snapshot_added else 0
                limits.charge(self.db, [
                    ('characters:' + owner, limits.NEW_CHARACTERS_PER_OWNER_DAY, 86400,
                     int(old is None or takeover)),
                    ('characters:group', limits.NEW_CHARACTERS_PER_GROUP_DAY, 86400, int(old is None)),
                    ('events:' + owner, limits.NEW_EVENTS_PER_OWNER_DAY, 86400, accepted),
                    ('events:group', limits.NEW_EVENTS_PER_GROUP_DAY, 86400, accepted),
                    ('bytes:' + owner, limits.NEW_BYTES_PER_OWNER_DAY, 86400, new_bytes),
                    ('bytes:group', limits.NEW_BYTES_PER_GROUP_DAY, 86400, new_bytes),
                ], now)
        role = p['settings'].get('character_role')
        old_role = self.db.execute('SELECT source,role FROM character_labels WHERE character=?',
                                   (cid,)).fetchone()
        discord_main = self.db.execute("SELECT 1 FROM character_labels l JOIN characters c "
            "ON c.id=l.character WHERE c.owner=? AND l.source='discord' AND l.role='main'",
            (owner,)).fetchone()
        # validate() always sets a role; the addon may only change its own label.
        role_changed = not discord_main and (
            not old_role or (old_role['source'] == 'addon' and old_role['role'] != role))
        if role_changed:
            set_role(self, owner, cid, role, source='addon', sync=False)
        # A new label shows on every owner archive; a new main also demotes the siblings.
        if renamed or (role_changed and role == 'main'):
            self.sync_owner_archives(owner)
        else:
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
        if cid:
            self.sync_archive(cid)
        else:
            self.sync_owner_archives(owner)

    def delete(self, owner):
        ids = [char['id'] for char in self.characters(owner)]
        with self.db:
            self.db.execute('DELETE FROM characters WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM installations WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM links WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM upload_receipts WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM people WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM group_pauses WHERE owner=?', (owner,))
            self.db.execute('DELETE FROM former_owners WHERE owner=?', (owner,))
            self.db.executemany('DELETE FROM former_owners WHERE character=?', [(cid,) for cid in ids])
        for cid in ids:
            self.drop_archive(cid)

    def paused(self, owner):
        """Whether this owner paused sharing in an ID-joined group."""
        return self.db.execute('SELECT 1 FROM group_pauses WHERE owner=?', (owner,)).fetchone() is not None

    def barred(self, cid, owner):
        """Whether this owner lost the character to a takeover or an operator release."""
        return self.db.execute('SELECT 1 FROM former_owners WHERE character=? AND owner=?',
                               (cid, owner)).fetchone() is not None

    def drop_archive(self, cid):
        (self.archive_directory / f'{cid}.json').unlink(missing_ok=True)

    def character(self, cid):
        row = self.db.execute('SELECT * FROM characters WHERE id=?', (cid,)).fetchone()
        return self.decode(row) if row else None

    def find_characters(self, name, realm, client=None):
        """Characters whose identity matches, ignoring case; for operator commands.
        Python's casefold() also matches non-ASCII names, which SQL NOCASE does not."""
        def same(a, b):
            return a.casefold() == b.casefold()
        matches = []
        for row in self.db.execute('SELECT id,owner,identity FROM characters'):
            identity = json.loads(row['identity'])
            if (same(identity['name'], name) and same(identity['realm'], realm)
                    and (client is None or same(identity['client'], client))):
                matches.append({'id': row['id'], 'owner': row['owner'], 'identity': identity})
        return matches

    def release(self, cid, owner=None):
        """Operator recovery for a squatted or orphaned character (#11); returns what it did.

        Without ``owner`` the character and all its data are deleted, and its current owner
        can't claim it again, so the next upload from anyone else claims it fresh. With
        ``owner`` it moves to that owner with its history, the current owner can't take it
        back, and the stored claim is dropped so the new owner's next upload binds its own
        secret. For a deleted character, ``owner`` only lifts that owner's block."""
        char = self.character(cid)
        if char is None:
            if owner is None or not self.barred(cid, owner):
                raise ValidationError('Unknown character')
            with self.db:
                self.db.execute('DELETE FROM former_owners WHERE character=? AND owner=?', (cid, owner))
            return 'unblocked'
        if owner is None:
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO former_owners VALUES(?,?)', (cid, char['owner']))
                self.db.execute('DELETE FROM characters WHERE id=?', (cid,))
            self.drop_archive(cid)
            return 'deleted'
        if owner == char['owner']:
            raise ValidationError('Character already belongs to that owner')
        if not self.db.execute('SELECT 1 FROM installations WHERE owner=? UNION ALL '
                               'SELECT 1 FROM people WHERE owner=?', (owner, owner)).fetchone():
            raise ValidationError('Unknown owner')
        if self.paused(owner):
            raise ValidationError('Owner has paused sharing; they must resume first')
        with self.db:
            self.db.execute('UPDATE characters SET owner=? WHERE id=?', (owner, cid))
            self.db.execute('DELETE FROM character_claims WHERE character=?', (cid,))
            self.db.execute('DELETE FROM character_labels WHERE character=?', (cid,))
            self.db.execute('INSERT OR IGNORE INTO former_owners VALUES(?,?)', (cid, char['owner']))
            self.db.execute('DELETE FROM former_owners WHERE character=? AND owner=?', (cid, owner))
        self.sync_archive(cid)
        return 'moved'

    def owners(self):
        """Every known owner with label, character count and pause; for operator commands."""
        from .people import person
        rows = self.db.execute('''SELECT o.owner, COUNT(c.id) AS characters,
            EXISTS(SELECT 1 FROM group_pauses g WHERE g.owner=o.owner) AS paused
            FROM (SELECT owner FROM installations UNION SELECT owner FROM people
                  UNION SELECT owner FROM characters) o
            LEFT JOIN characters c ON c.owner=o.owner GROUP BY o.owner ORDER BY o.owner''').fetchall()
        return [{'owner': row['owner'], 'name': person(self, row['owner'])['display_name'],
                 'characters': row['characters'], 'paused': bool(row['paused'])} for row in rows]

    def sync_archive(self, cid):
        from .archive import write_character
        write_character(self, cid)

    def sync_owner_archives(self, owner):
        for char in self.characters(owner):
            self.sync_archive(char['id'])

    def sync_archives(self):
        for char in self.characters():
            self.sync_archive(char['id'])

    def pending(self, ready_only=False):
        if ready_only and not self.can_post():
            return None
        readiness = ("AND NOT EXISTS (SELECT 1 FROM posting_cooldowns pc "
                     "WHERE pc.scope='character:' || c.id AND pc.next_at>?) " if ready_only else '')
        ordering = ("COALESCE((SELECT next_at FROM posting_cooldowns pc WHERE pc.scope='owner:' || c.owner),0), "
                    if ready_only else '')
        row = self.db.execute('''SELECT o.id AS delivery_id,e.id AS event_id,e.kind,e.at,e.data,c.*
            FROM outbox o JOIN characters c ON c.id=o.character
            JOIN events e ON e.character=o.character AND e.id=o.event_id
            WHERE o.status='pending' AND e.suppressed=0 AND o.next_try<=?
            AND NOT EXISTS (SELECT 1 FROM outbox_batches b WHERE b.delivery=o.id AND
                (SELECT COUNT(*) FROM upload_receipts r WHERE r.owner=b.owner AND r.batch=b.batch)
                 < (SELECT MAX(total) FROM upload_receipts r WHERE r.owner=b.owner AND r.batch=b.batch)) ''' + readiness +
            'ORDER BY ' + ordering + 'o.id LIMIT 1', (time.time(), time.time()) if ready_only else (time.time(),)).fetchone()
        if not row:
            return None
        item = self.decode(row)
        item['data'] = json.loads(item['data'])
        from .people import decorate
        return decorate(self, item)

    def summary_items(self, item):
        """All still-permitted rows in this completed account export; never split it into messages."""
        if item['settings'].get('discord_delivery') != 'summary':
            return [item]
        batch = self.db.execute('SELECT owner,batch FROM outbox_batches WHERE delivery=?',
                                (item['delivery_id'],)).fetchone()
        if batch is None:
            return [item]
        rows = self.db.execute("""SELECT o.id AS delivery_id,e.id AS event_id,e.kind,e.at,e.data,c.*
            FROM outbox_batches b JOIN outbox o ON o.id=b.delivery
            JOIN characters c ON c.id=o.character JOIN events e ON e.character=c.id AND e.id=o.event_id
            WHERE b.owner=? AND b.batch=? AND o.status='pending' AND e.suppressed=0
            ORDER BY c.id,e.at,o.id""", (batch['owner'], batch['batch'])).fetchall()
        from .people import decorate
        values = []
        for row in rows:
            value = self.decode(row)
            value['data'] = json.loads(value['data'])
            if self.should_announce(value['settings'], value):
                values.append(decorate(self, value))
        return values

    def deliver_many(self, items, status, delay=0, message_id=None):
        # One transaction makes uncertain sends apply to the whole summary on restart.
        with self.db:
            if status == 'sending':
                for cid in {item['id'] for item in items}:
                    self.reserve_post(cid)
            for item in items:
                self.db.execute("""UPDATE outbox SET status=?,next_try=?,message_id=?,attempts=attempts+?
                    WHERE id=?""", (status, time.time()+delay, message_id, int(status == 'sending'),
                                    item['delivery_id']))
        for cid in {item['id'] for item in items}:
            self.sync_archive(cid)

    def delivery(self, delivery_id, status, delay=0, message_id=None):
        if status == 'sending':
            row = self.db.execute('SELECT character FROM outbox WHERE id=?', (delivery_id,)).fetchone()
            if row:
                self.reserve_post(row['character'])
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
        if (settings.get('discord_delivery') != 'summary' and mode == 'celebrations'
                and event['kind'] not in ('introduction', 'level', 'loot')):
            return False
        if not should_announce(settings, event):
            return False
        if event['kind'] == 'level':
            if settings.get('discord_delivery') == 'summary':
                return True
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
