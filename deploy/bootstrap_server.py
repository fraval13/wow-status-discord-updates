#!/usr/bin/python3
"""One-time root bootstrap. Run only on the target server with an explicit public key."""
import argparse
import os
import pwd
import shutil
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--public-key', required=True, type=Path)
args = parser.parse_args()
if os.geteuid() != 0:
    raise SystemExit('Run bootstrap as root on the target server')
public_key = args.public_key.read_text().strip()
if not public_key.startswith('ssh-ed25519 ') or '\n' in public_key:
    raise SystemExit('Expected a single dedicated Ed25519 public key')
source = Path(__file__).resolve().parent
base, config = Path('/opt/wow-character-status'), Path('/etc/wow-character-status')
if base.exists() or config.exists():
    raise SystemExit('Project paths already exist; inspect them rather than overwriting')
for account in ('wow-character-build', 'wow-character-deploy', 'wow-character-ronkalot', 'wow-character-navsquad'):
    try:
        pwd.getpwnam(account)
    except KeyError:
        shell = '/bin/sh' if account == 'wow-character-deploy' else '/usr/sbin/nologin'
        subprocess.run(['useradd', '--system', '--user-group', '--create-home', '--home-dir',
                        '/var/lib/' + account, '--shell', shell, account], check=True)
    else:
        raise SystemExit('Project account already exists; inspect it first')
base.mkdir(mode=0o755)
(base / 'releases').mkdir(mode=0o755)
config.mkdir(mode=0o700)
for name, source_name in [('wow-character-status-deploy', 'install_release.py'),
                           ('wow-character-status-receive', 'receive-release')]:
    target = Path('/usr/local/sbin') / name
    if target.exists():
        raise SystemExit('Project receiver path already exists')
    shutil.copyfile(source / source_name, target)
    target.chmod(0o755)
unit = Path('/etc/systemd/system/wow-character-status@.service')
if unit.exists():
    raise SystemExit('Project unit already exists')
shutil.copyfile(source / 'wow-character-status@.service', unit)
unit.chmod(0o644)
home = Path(pwd.getpwnam('wow-character-deploy').pw_dir)
os.chown(home, 0, 0)
home.chmod(0o755)
ssh = home / '.ssh'
ssh.mkdir(mode=0o755)
(ssh / 'authorized_keys').write_text('restrict,command="/usr/local/sbin/wow-character-status-receive" ' + public_key + '\n')
(ssh / 'authorized_keys').chmod(0o644)
sudoers = Path('/etc/sudoers.d/wow-character-status-deploy')
sudoers.write_text('wow-character-deploy ALL=(root) NOPASSWD: /usr/local/sbin/wow-character-status-deploy ""\n')
sudoers.chmod(0o440)
subprocess.run(['visudo', '-cf', str(sudoers)], check=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
print('Project accounts, receiver and service template created; no application started.')
