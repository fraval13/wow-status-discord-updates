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
    service.add_argument('--discord', action='store_true', help='Requires bot token and server/channel IDs')
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
    for name in ('create-link', 'outbox', 'resolve', 'simulate', 'export', 'recap', 'resolve-recap', 'weekly', 'resolve-weekly'):
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
    return root


def main():
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        if args.command == 'desktop':
            from .gui import launch
            launch()
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
                    from .discord_bot import StatusBot
                    token = os.environ.get('DISCORD_BOT_TOKEN')
                    if not token:
                        raise ValueError('Set DISCORD_BOT_TOKEN before using --discord')
                    client = StatusBot(store, int(os.environ['DISCORD_GUILD_ID']),
                                       int(os.environ['DISCORD_CHANNEL_ID']))

                    async def bot():
                        async with client:
                            await client.start(token)
                asyncio.run(serve(store, args.host, args.port, bot))
            elif args.command == 'create-link':
                print(store.create_link(args.owner))
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
