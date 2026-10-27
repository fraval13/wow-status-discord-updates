"""Run at home: copy this addon's files and set the installed client's TOC version."""
import argparse
import re
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--addons-dir', type=Path, required=True,
                    help='Existing Classic Era Interface/AddOns directory')
parser.add_argument('--interface', required=True,
                    help='Fourth value from /dump GetBuildInfo() in your client')
args = parser.parse_args()
if not re.fullmatch(r'\d{5,6}', args.interface):
    parser.error('Interface must be a 5- or 6-digit build interface number')
if not args.addons_dir.is_dir():
    parser.error('AddOns directory must already exist; confirm the correct WoW client')
source = Path(__file__).resolve().parents[1] / 'addon/WoWStatus'
target = args.addons_dir / 'WoWStatus'
if source.resolve() == target.resolve():
    parser.error('Choose the game AddOns directory, not this repository')
if target.exists():
    parser.error('WoWStatus already exists. Back it up and remove it before installing an update')
shutil.copytree(source, target)
toc = target / 'WoWStatus.toc'
toc.write_text(re.sub(r'(?m)^## Interface: \d+$', '## Interface: ' + args.interface,
                      toc.read_text(encoding='utf-8')), encoding='utf-8')
print(f'Installed WoWStatus at {target}. Restart WoW; sharing begins disabled.')
