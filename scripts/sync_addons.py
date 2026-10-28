"""Maintainer tool: copy canonical shared Lua into both standalone addon folders.

This only copies source files; it does not start a game, service or test suite.
"""
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'addon'
for client in ('vanilla', 'forever'):
    destination = root / client / 'WoWStatus'
    for source in sorted((root / 'shared').glob('*.lua')):
        shutil.copyfile(source, destination / source.name)
    for source in sorted((root / 'shared' / 'Textures').glob('*')):
        (destination / 'Textures').mkdir(exist_ok=True)
        shutil.copyfile(source, destination / 'Textures' / source.name)
