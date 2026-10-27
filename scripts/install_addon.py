"""Run at home: install either the Vanilla Classic or Forever addon folder."""
import argparse
import re
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--client', choices=['vanilla', 'forever'], required=True)
parser.add_argument('--addons-dir', type=Path, required=True,
                    help='Existing Interface/AddOns directory for the chosen game client')
parser.add_argument('--interface', required=True,
                    help='Fourth return value from /dump GetBuildInfo() in that game client')
args = parser.parse_args()
if not re.fullmatch(r'\d{5,6}', args.interface):
    parser.error('Interface must be a 5- or 6-digit number')
interface = int(args.interface)
low, high = (11000, 12000) if args.client == 'vanilla' else (16000, 17000)
if not low <= interface < high:
    parser.error('Interface is outside this edition’s documented range; confirm client/build first')
if not args.addons_dir.is_dir():
    parser.error('AddOns directory must already exist; select the correct game client')
source = Path(__file__).resolve().parents[1] / 'addon' / args.client / 'WoWStatus'
target = args.addons_dir / 'WoWStatus'
if source.resolve() == target.resolve():
    parser.error('Choose the game AddOns directory, not this repository')
if target.exists():
    parser.error('WoWStatus already exists. Back up addon files and SavedVariables before removing it')
shutil.copytree(source, target)
toc = target / 'WoWStatus.toc'
toc.write_text(re.sub(r'(?m)^## Interface: \d+$', '## Interface: ' + args.interface,
                      toc.read_text(encoding='utf-8')), encoding='utf-8')
print(f'Installed {args.client} WoWStatus at {target}. Restart that game client; sharing begins disabled.')
