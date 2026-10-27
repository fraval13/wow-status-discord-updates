"""Service entry point: ingestion starts now; Discord starts when all its settings exist."""
import os
import sys
from pathlib import Path

args = [str(Path(sys.executable).parent / 'wow-status'), 'serve',
        '--db', os.environ['WOW_STATUS_DATABASE'], '--host', '127.0.0.1',
        '--port', os.environ['WOW_STATUS_PORT'], '--group', os.environ['DISCORD_GROUP_NAME']]
if all(os.environ.get(key) for key in ('DISCORD_BOT_TOKEN', 'DISCORD_GUILD_ID', 'DISCORD_CHANNEL_ID')):
    args.append('--discord')
os.execv(args[0], args)
