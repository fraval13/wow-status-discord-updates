"""Bounded Discord content. Every send also disables mention parsing."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo


def safe(value):
    text = str(value)
    text = re.sub(r'\|c[0-9a-fA-F]{8}|\|r', '', text)
    text = re.sub(r'\|H[^|]+\|h(.*?)\|h', r'\1', text)
    text = text.replace('@', '@\u200b')
    return re.sub(r'([\\`*_~|>\[\]])', r'\\\1', text)[:500]


def norwegian(value):
    return datetime.fromtimestamp(value, ZoneInfo('Europe/Oslo')).strftime(
        '%Y-%m-%d %H:%M:%S %z') + ' Europe/Oslo'


def profile(char):
    ident, snap = char['identity'], char['snapshot']
    lines = [f"**{safe(ident['name'])}** · {safe(ident['realm'])} · {safe(ident['client'])}"]
    for key, value in snap.items():
        if key == 'gear':
            value = ', '.join(f'{slot}: {item}' for slot, item in value.items())
        lines.append(f'{key.title()}: {safe(value)}')
    lines.append(f"Last export: {norwegian(char['exported'])}\n"
                 f"Last upload: {norwegian(char['uploaded'])}")
    return '\n'.join(lines)[:1900]


def announcement(item):
    name = safe(item['identity']['name'])
    data, kind = item['data'], item['kind']
    if kind == 'introduction':
        snap = item['snapshot']
        details = ' '.join(safe(snap[k]) for k in ('level', 'race', 'class') if k in snap)
        return (f"A new adventurer joins the tracker: **{name}**"
                f"{' — ' + details if details else ''} on {safe(item['identity']['realm'])}!")
    messages = {
        'level': f"**{name}** reached level {safe(data.get('level', '?'))}!",
        'loot': f"**{name}** looted {safe(data.get('item', '?'))}!",
        'equipment': f"**{name}** equipped {safe(data.get('item', '?'))}.",
        'death': f"**{name}** has fallen.",
        'zone': f"**{name}** was last seen in {safe(data.get('zone', '?'))}.",
        'session': f"**{name}** shared a session update: {safe(data.get('state', '?'))}.",
        'lfg': f"**{name}** is looking for a group: {safe(data.get('text', '?'))}",
    }
    return messages[kind][:1800] + f"\nRecorded {norwegian(item['at'])} · uploaded character data"
