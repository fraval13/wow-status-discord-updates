"""Discord identities own characters; display names are labels, never authentication."""
from .schema import ValidationError, string


def remember(store, owner, display_name, source='discord'):
    owner = string(str(owner), 'Discord owner', 120)
    display_name = string(display_name, 'Discord display name', 80)
    old = store.db.execute('SELECT display_name,source FROM people WHERE owner=?', (owner,)).fetchone()
    if old and old['display_name'] == display_name and old['source'] == source:
        return
    with store.db:
        store.db.execute('INSERT INTO people(owner,display_name,source) VALUES(?,?,?) '
                         'ON CONFLICT(owner) DO UPDATE SET display_name=excluded.display_name,source=excluded.source',
                         (owner, display_name, source))
    for char in store.characters(owner):
        store.sync_archive(char['id'])


def nickname(store, owner, name=None):
    if name is not None:
        name = string(name.strip(), 'nickname', 40)
    with store.db:
        # A local test owner can set a nickname before a Discord account was remembered.
        store.db.execute('INSERT OR IGNORE INTO people(owner,display_name) VALUES(?,?)',
                         (owner, 'Linked friend'))
        store.db.execute('UPDATE people SET nickname=? WHERE owner=?', (name, owner))
    for char in store.characters(owner):
        store.sync_archive(char['id'])


def person(store, owner):
    row = store.db.execute('SELECT * FROM people WHERE owner=?', (owner,)).fetchone()
    return {'discord_user_id': None if owner.startswith('group:') else owner,
            'display_name': (row['nickname'] or row['display_name']) if row else 'Linked friend',
            'name_source': ('nickname' if row['nickname'] else row['source']) if row else 'unavailable'}


def character_role(store, cid):
    row = store.db.execute('SELECT role FROM character_labels WHERE character=?', (cid,)).fetchone()
    return row['role'] if row else 'alt'


def set_role(store, owner, cid, role, source='discord'):
    if role not in ('main', 'alt'):
        raise ValidationError('Role must be main or alt')
    row = store.db.execute('SELECT owner FROM characters WHERE id=?', (cid,)).fetchone()
    if not row or row['owner'] != owner:
        raise ValidationError('Choose one of your own linked characters')
    with store.db:
        if role == 'main':
            store.db.execute("UPDATE character_labels SET role='alt' WHERE character IN "
                             '(SELECT id FROM characters WHERE owner=?)', (owner,))
        store.db.execute('INSERT INTO character_labels VALUES(?,?,?) ON CONFLICT(character) '
                         'DO UPDATE SET role=excluded.role,source=excluded.source', (cid, role, source))
    for char in store.characters(owner):
        store.sync_archive(char['id'])


def decorate(store, char):
    return dict(char, friend=person(store, char['owner']), role=character_role(store, char['id']))
