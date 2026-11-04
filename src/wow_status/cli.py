"""One entry point for service, companion, and offline operator tools."""
import argparse
import asyncio
import getpass
import json
import logging
import os
from pathlib import Path

from .archive import export_characters
from .companion import link, upload
from .daily import DailyRecaps
from .formatting import announcement
from .locking import FileLock
from .people import person
from .schema import LEVEL_CAPS, ValidationError
from .server import serve
from .store import Store


def parser():
    root = argparse.ArgumentParser(description='Opt-in WoW character status and Discord updates')
    commands = root.add_subparsers(dest='command', required=True)
    commands.add_parser('desktop', help='Open the optional companion window (run at home)')
    service = commands.add_parser('serve', help='Run ingestion and optional Discord bot')
    service.add_argument('--db', default='state/service.sqlite3')
    service.add_argument('--host', default='127.0.0.1')
    service.add_argument('--port', type=int, default=8080)
    service.add_argument('--group', default=os.environ.get('DISCORD_GROUP_NAME'),
                         help='Exact free-text group name, for example Weekend Crew')
    key = commands.add_parser('group-key', help='Print the routing key for a free-text group name')
    key.add_argument('name')
    service.add_argument('--group-id', default=os.environ.get('DISCORD_GROUP_ID'),
                         help='One group ID for this service/database; use a different instance per group')
    service.add_argument('--trust-proxy', action='store_true',
                         help='Trust X-WoW-Client-IP only from a local proxy that overwrites it')
    service.add_argument('--discord', action='store_true', help='Requires bot token and server/channel IDs')
    config = commands.add_parser('configure', help='Set the shared service URL; groups are selected in WoW')
    config.add_argument('--url', required=True)
    config.add_argument('--credentials', default=str(Path.home() / '.wow-status/credentials.json'))
    privacy = commands.add_parser('group-privacy', help='Pause, resume or delete your data in one ID-joined group')
    privacy.add_argument('--group', required=True)
    privacy.add_argument('--state', default=str(Path.home() / '.wow-status/upload-state.json'))
    privacy.add_argument('action', choices=['pause', 'resume', 'delete'])
    privacy.add_argument('--credentials', default=str(Path.home() / '.wow-status/credentials.json'))
    enroll = commands.add_parser('link', help='Redeem a private /link code; credentials stay on disk')
    enroll.add_argument('--url', required=True)
    enroll.add_argument('--credentials', default=str(Path.home() / '.wow-status/credentials.json'))
    companion = commands.add_parser('companion', help='Watch exported addon data')
    companion.add_argument('--saved-variables', action='append', required=True)
    companion.add_argument('--credentials', default=str(Path.home() / '.wow-status/credentials.json'))
    companion.add_argument('--state', default=str(Path.home() / '.wow-status/upload-state.json'))
    companion.add_argument('--once', action='store_true')
    companion.add_argument('--dry-run', action='store_true')
    companion.add_argument('--interval', type=int, default=5)
    for name in ('create-link', 'outbox', 'resolve', 'simulate', 'export', 'recap', 'resolve-recap', 'weekly', 'resolve-weekly',
                 'release-character', 'owners'):
        command = commands.add_parser(name)
        command.add_argument('--db', default='state/service.sqlite3')
        if name == 'export':
            command.add_argument('--directory', required=True)
        if name in ('recap', 'resolve-recap'):
            command.add_argument('--day', required=True, help='Oslo calendar date YYYY-MM-DD')
        if name in ('weekly', 'resolve-weekly'):
            command.add_argument('--week', required=True, help='Week starting Monday YYYY-MM-DD, Oslo')
        if name in ('resolve-recap', 'resolve-weekly'):
            command.add_argument('--character-id', required=True)
            command.add_argument('resolution', choices=['retry', 'sent', 'discard'])
        if name == 'create-link':
            command.add_argument('--owner', required=True, help='Discord user ID, or local test owner')
        if name == 'resolve':
            command.add_argument('delivery_id', type=int)
            command.add_argument('resolution', choices=['retry', 'sent', 'discard'])
        if name == 'release-character':
            command.description = ('Recover a character claimed by the wrong owner. Without '
                                   '--to-owner it is deleted, and the next upload from anyone '
                                   'but its current owner claims it.')
            command.add_argument('--character-id', help='ID from the character JSON archive')
            command.add_argument('--name', help='Character name, with --realm')
            command.add_argument('--realm')
            command.add_argument('--client', choices=sorted(LEVEL_CAPS),
                                 help='Only needed when several clients match')
            command.add_argument('--to-owner', help='Move it with its history to this owner ID '
                                 '(see the owners command); for a deleted character, let that '
                                 'owner claim it again')
        if name == 'owners':
            command.description = 'List owner IDs with their names, for release-character --to-owner'

    return root


def release_character(store, args):
    """Operator recovery for #11; returns the line to print."""
    if args.character_id:
        char = store.character(args.character_id)
        # A deleted character can't be listed, but --to-owner may still lift a block.
        matches = [char] if char else ([{'id': args.character_id}] if args.to_owner else [])
    elif args.name and args.realm:
        matches = store.find_characters(args.name, args.realm, args.client)
    else:
        raise SystemExit('Give --character-id, or --name with --realm.')

    def describe(char):
        if 'identity' not in char:
            return f"character {char['id']}"
        identity = char['identity']
        return (f"{identity['name']} ({identity['realm']}, {identity['client']}) {char['id']}, "
                f"owner {char['owner']} ({person(store, char['owner'])['display_name']})")
    if len(matches) != 1:
        for char in matches:
            print(describe(char))
        raise SystemExit('No character matches.' if not matches else
                         'Several characters match; choose one with --character-id.')
    char = matches[0]
    try:
        result = store.release(char['id'], args.to_owner)
    except ValidationError as exc:
        raise SystemExit(f'Not released: {exc}.') from None
    return {
        'unblocked': f'Owner {args.to_owner} may claim {describe(char)} again.',
        'moved': (f'Moved {describe(char)} to owner {args.to_owner}. '
                  'Their next upload binds their claim secret.'),
        'deleted': (f'Released {describe(char)}. Its data is deleted; the next upload from '
                    'another owner claims it.'),
    }[result]


def main():
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        if args.command == 'desktop':
            from .gui import launch
            launch()
            return
        if args.command == 'group-key':
            from .group_routing import group_key
            print(group_key(args.name))
            return
        if args.command == 'configure':
            from .group_client import configure
            configure(args.url, args.credentials)
            print('Service saved. Select group IDs in WoW; no Discord link code is required.')
            return
        if args.command == 'group-privacy':
            from .group_client import privacy_action
            with FileLock(args.state):
                asyncio.run(privacy_action(args.credentials, args.group, args.action))
            print('Group privacy action completed.')
            return
        if args.command == 'link':
            asyncio.run(link(args.url, getpass.getpass('Private linking code: '), args.credentials))
            print('Linked. Credentials stored privately; do not share this file.')
            return
        if args.command == 'companion':
            with FileLock(args.state):
                ok = asyncio.run(upload(args.saved_variables, args.credentials, args.state,
                                        args.once, args.dry_run, max(2, args.interval)))
            if not ok:
                raise SystemExit(1)
            return
        lock = FileLock(args.db)
        lock.__enter__()
        store = None
        try:
            store = Store(args.db)
            if args.command == 'serve':
                bot = None
                if args.discord:
                    from .discord_bot import session
                    token = os.environ.get('DISCORD_BOT_TOKEN')
                    if not token:
                        raise ValueError('Set DISCORD_BOT_TOKEN before using --discord')
                    bot = session(store, int(os.environ['DISCORD_GUILD_ID']),
                                  int(os.environ['DISCORD_CHANNEL_ID']), token)
                from .group_routing import group_key
                selected_group = group_key(args.group) if args.group else args.group_id
                asyncio.run(serve(store, args.host, args.port, bot, selected_group, args.group, args.trust_proxy))
            elif args.command == 'create-link':
                print(store.create_link(args.owner))
            elif args.command == 'release-character':
                print(release_character(store, args))
            elif args.command == 'owners':
                for row in store.owners():
                    print(f"{row['owner']}\t{row['name']}\t{row['characters']} characters"
                          + ('\tpaused' if row['paused'] else ''))
            elif args.command == 'outbox':
                rows = store.db.execute('SELECT id,status,attempts,message_id FROM outbox').fetchall()
                recaps = store.db.execute('SELECT * FROM digest_parts').fetchall()
                weekly = store.db.execute('SELECT * FROM weekly_parts').fetchall()
                print(json.dumps({'events': [dict(row) for row in rows],
                                  'recaps': [dict(row) for row in recaps],
                                  'weekly': [dict(row) for row in weekly]}, indent=2))
            elif args.command == 'export':
                count = export_characters(store, args.directory)
                print(f'Exported {count} structured character JSON files.')
            elif args.command == 'recap':
                recaps = DailyRecaps(store)
                recaps.prepare(args.day)
                while item := recaps.pending():
                    print(item['text'])
                    recaps.delivery(item['key'], 'simulated')
            elif args.command in ('weekly', 'resolve-weekly'):
                from .weekly import WeeklyRecaps
                weekly = WeeklyRecaps(store)
                if args.command == 'weekly':
                    weekly.prepare(args.week)
                    while item := weekly.pending():
                        print(item['text'])
                        weekly.delivery(item['key'], 'simulated')
                else:
                    weekly.delivery({'week': args.week, 'character': args.character_id},
                        {'retry': 'pending', 'sent': 'sent', 'discard': 'discarded'}[args.resolution])
            elif args.command == 'resolve-recap':
                DailyRecaps(store).delivery(
                    {'day': args.day, 'timezone': 'Europe/Oslo', 'character': args.character_id},
                    {'retry': 'pending', 'sent': 'sent', 'discard': 'discarded'}[args.resolution])
            elif args.command == 'resolve':
                store.delivery(args.delivery_id,
                               {'retry': 'pending', 'sent': 'sent', 'discard': 'discarded'}[args.resolution])
            elif args.command == 'simulate':
                while item := store.pending():
                    print(announcement(item))
                    store.delivery(item['delivery_id'], 'simulated')
        finally:
            if store:
                store.close()
            lock.__exit__()
    except KeyboardInterrupt:
        pass
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(f'Could not complete command ({type(exc).__name__}); check configuration.') from None
