"""Bounded Discord content. Every send also disables mention parsing."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo


def safe(value):
    text = str(value)
    text = re.sub(r'\|c[0-9a-fA-F]{8}|\|r', '', text)
    text = re.sub(r'\|H[^|]+\|h(.*?)\|h', r'\1', text)
    text = text.replace('@', '@\u200b')
    # Keep raw evidence in JSON, but user text cannot create clickable URLs/invites.
    text = re.sub(r'(?i)\b([a-z][a-z0-9+.-]{1,31}):(?=//)', r'\1:​', text)
    text = re.sub(r'(?i)\b(www|discord|discordapp)\.', r'\1​.', text)
    return re.sub(r'([\\`*_~|>\[\]])', r'\\\1', text)[:500]


def norwegian(value):
    return datetime.fromtimestamp(value, ZoneInfo('Europe/Oslo')).strftime(
        '%Y-%m-%d %H:%M:%S %z') + ' Europe/Oslo'


def profile(char):
    ident, snap = char['identity'], char['snapshot']
    owner = char.get('friend', {}).get('display_name', 'Linked friend')
    lines = [f"**{safe(owner)}’s {safe(ident['name'])}** · {char.get('role', 'alt')} · "
             f"{safe(ident['realm'])} · {safe(ident['client'])}"]
    for key, value in snap.items():
        if key == 'professions':
            value = ', '.join(p['name'] + ' (player-entered)' for p in value)
        if key == 'gear':
            value = ', '.join(f'{slot}: {item}' for slot, item in value.items())
        lines.append(f'{key.title()}: {safe(value)}')
    lines.append(f"Last export: {norwegian(char['exported'])}\n"
                 f"Last upload: {norwegian(char['uploaded'])}")
    return '\n'.join(lines)[:1900]


def announcement(item):
    character_name = safe(item['identity']['name'])
    owner = item.get('friend', {}).get('display_name')
    name = f'{safe(owner)}’s {character_name}' if owner else character_name
    data, kind = item['data'], item['kind']
    if kind == 'introduction':
        snap = item['snapshot']
        details = ' '.join(safe(snap[k]) for k in ('level', 'race', 'class') if k in snap)
        return (f"A new adventurer joins the tracker: **{name}**"
                f"{' — ' + details if details else ''} on {safe(item['identity']['realm'])}!")
    if kind in {'dungeon', 'mount', 'reputation', 'unlock', 'pvp', 'discovery'}:
        text = safe(data.get('text', 'shared a milestone'))
        if kind == 'discovery':
            text = 'shared a discovery: ||' + text + '||'
        return f"**{name}** · {text}\nRecorded {norwegian(item['at'])} · uploaded character data"
    messages = {
        'level': f"**{name}** reached level {safe(data.get('level', '?'))}!",
        'loot': f"**{name}** looted {safe(data.get('item', '?'))}!",
        'equipment': f"**{name}** equipped {safe(data.get('item', '?'))}.",
        'death': f"**{name}** has fallen.",
        'zone': f"**{name}** was last seen in {safe(data.get('zone', '?'))}.",
        'quest': f"**{name}** completed a quest.",
        'profession': f"**{name}** improved {safe(data.get('name', 'a profession'))}.",
        'status': f"**{name}** shared updated character progress.",
        'session': f"**{name}** shared a session update: {safe(data.get('state', '?'))}.",
        'lfg': f"**{name}** is looking for a group: {safe(data.get('text', '?'))}",
    }
    prefix = '[TEST] ' if data.get('synthetic') else ''
    return prefix + messages[kind][:1780] + f"\nRecorded {norwegian(item['at'])} · uploaded character data"


def roster_pages(store, characters):
    from .people import decorate
    chars = [decorate(store, c) for c in characters if c['settings']['enabled']]
    chars.sort(key=lambda c: (c['friend']['display_name'].casefold(), c['owner'],
                              c['role'] != 'main', c['identity']['name'].casefold()))
    pages, lines, previous = [], [], None
    for char in chars:
        owner = char['friend']['display_name']
        identity, snapshot = char['identity'], char['snapshot']
        header = f"**{safe(owner)[:100]}**" if previous != char['owner'] else ''
        details = ' · '.join(str(snapshot[k]) for k in ('level', 'class') if k in snapshot)
        line = (f"• {safe(identity['name'])[:100]} · {char['role']} · {safe(details)[:100]} · "
                f"{safe(identity['realm'])[:100]} · {safe(identity['client'])[:50]}\n"
                f"  Last upload: {norwegian(char['uploaded'])}")
        professions = snapshot.get('professions', [])
        if professions:
            line += '\n  Professions: ' + ', '.join(safe(p['name'])[:40] for p in professions[:6])
        addition = ('\n' + header if header else '') + '\n' + line
        if lines and len('\n'.join(lines)) + len(addition) > 1750:
            pages.append('\n'.join(lines))
            lines = [f"**{safe(owner)[:100]}**", line]
        else:
            if header:
                lines.append(header)
            lines.append(line)
        previous = char['owner']
    if lines:
        pages.append('\n'.join(lines))
    return pages or ['No characters are sharing yet.']
