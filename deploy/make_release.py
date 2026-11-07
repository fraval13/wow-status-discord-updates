"""GitHub runner only: build a tracked-source tar plus private deployment metadata.

Discord settings come from one JSON repository secret, WOW_STATUS_DISCORD_CONFIG:

    {"<instance>": {"bot_token": "...", "guild_id": "...", "channel_id": "...", "route": "..."}}

The optional route (the group's route key) is only for the post-deploy bot check
(scripts/report_discord_state.py) and is not sent to the server. Instances are the labels in the server's private groups.json (deploy/SERVER.md), so
no group name appears in Git or in the workflow. Without the secret the archive
carries no Discord settings and the server keeps the ones it has.
"""
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from install_release import DISCORD, INSTANCE, RESERVED, discord_value

ROUTE = re.compile(r'[0-9a-f]{22}')

SHAPE = ('WOW_STATUS_DISCORD_CONFIG must map each group instance to an object with '
         'bot_token, guild_id and channel_id values')


def discord_config(raw):
    """Settings per instance, checked as the receiver will; errors never echo the secret."""
    if not raw or not raw.strip():
        print('::warning title=Discord settings unchanged::WOW_STATUS_DISCORD_CONFIG is not set, '
              'so the server keeps its existing Discord settings.')
        return {}
    try:
        config = json.loads(raw)
    except ValueError:
        raise SystemExit('WOW_STATUS_DISCORD_CONFIG is not valid JSON') from None
    if not isinstance(config, dict):
        raise SystemExit(SHAPE)
    result = {}
    for instance, values in config.items():
        if not isinstance(values, dict) or not set(values) <= {*DISCORD, 'route'}:
            raise SystemExit(SHAPE)
        # No label in the message: a migrated label can be an old group name, and this log is public.
        if not INSTANCE.fullmatch(instance) or instance in RESERVED:
            raise SystemExit('WOW_STATUS_DISCORD_CONFIG has a key that is not a group instance label '
                             '(lowercase letters, digits and -, see deploy/SERVER.md)')
        result[instance] = {}
        for key, value in values.items():
            if key == 'route':  # only for the runner's post-deploy bot check; the server has it
                if not isinstance(value, str) or not ROUTE.fullmatch(value):
                    raise SystemExit('WOW_STATUS_DISCORD_CONFIG has an invalid route')
                print('::add-mask::' + value)
                continue
            # Discord IDs are often pasted as JSON numbers; the receiver expects text.
            if key != 'bot_token' and type(value) is int:
                value = str(value)
            try:
                discord_value(key, value)
            except ValueError:
                raise SystemExit(f'WOW_STATUS_DISCORD_CONFIG has an invalid {key}') from None
            if key == 'bot_token' and value:
                # GitHub masks the whole JSON secret, not a token printed on its own.
                print('::add-mask::' + value)
            result[instance][key] = value
    return result


# The receiver accepts at most 64 MiB and only needs the application, the edition
# TOCs and the built homepage (whose ZIPs carry the full addon). Leave out the
# caption sources and generated caption banks, which grow with each personality.
ARCHIVE_PATHSPEC = ('.', ':(exclude)docs/caption-personalities', ':(exclude,glob)addon/**/Flavour*.lua')


def main():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], encoding='utf-8').strip()
    homepage = Path('dist/homepage')
    manifest = json.loads((homepage / 'downloads/release.json').read_text(encoding='utf-8'))
    if manifest.get('addon_revision') != revision:
        raise ValueError('Rebuild the homepage for the exact revision being deployed')
    config = discord_config(os.environ.get('WOW_STATUS_DISCORD_CONFIG', ''))
    archive = subprocess.check_output(['git', 'archive', '--format=tar', revision, '--', *ARCHIVE_PATHSPEC])
    path = Path(sys.argv[1])
    path.write_bytes(archive)
    path.chmod(0o600)
    with tarfile.open(path, 'a') as output:
        for name, content in [('.deploy/REVISION', revision.encode()),
                              ('.deploy/CONFIG.json', json.dumps(config).encode())]:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(content), 0o600
            output.addfile(info, io.BytesIO(content))
        for source in sorted(homepage.rglob('*')):
            if source.is_symlink():
                raise ValueError('Homepage may not contain symlinks')
            if source.is_file():
                output.add(source, arcname='.deploy/HOMEPAGE/' + source.relative_to(homepage).as_posix(), recursive=False)


if __name__ == '__main__':
    main()
