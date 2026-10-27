"""GitHub runner only: build a tracked-source tar plus private deployment metadata."""
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
archive = subprocess.check_output(['git', 'archive', '--format=tar', revision])
config = {group: {key: os.environ.get(f'{group.upper()}_DISCORD_{suffix}', '')
                  for key, suffix in [('bot_token', 'BOT_TOKEN'), ('guild_id', 'GUILD_ID'),
                                      ('channel_id', 'CHANNEL_ID')]}
          for group in ('ronkalot', 'navsquad')}
path = Path(sys.argv[1])
path.write_bytes(archive)
path.chmod(0o600)
with tarfile.open(path, 'a') as output:
    for name, content in [('.deploy/REVISION', revision.encode()),
                          ('.deploy/CONFIG.json', json.dumps(config).encode())]:
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(content), 0o600
        output.addfile(info, io.BytesIO(content))
