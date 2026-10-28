"""Discord presentation derived only from consented, recorded character observations."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import discord

from .archive import item_reference
from .daily import window
from .formatting import announcement, safe
from .progression import timeline

EMOJIS = {
    'introduction': ('wow_new', '👋'), 'level': ('wow_levelup', '⬆️'),
    'loot': ('wow_loot', '💰'), 'equipment': ('wow_gear', '🛡️'),
    'death': ('wow_death', '💀'), 'recap': ('wow_recap', '📜'),
}
RARITIES = {0: ('Poor', 0x9D9D9D), 1: ('Common', 0xFFFFFF), 2: ('Uncommon', 0x1EFF00),
            3: ('Rare', 0x0070DD), 4: ('Epic', 0xA335EE), 5: ('Legendary', 0xFF8000)}


def emoji(kind, custom=None):
    name, fallback = EMOJIS.get(kind, ('', '•'))
    return (custom or {}).get(name, fallback)


def duration(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return ' '.join(part for part in (f'{days}d' if days else '', f'{hours}h' if hours else '',
        f'{minutes}m' if minutes else '', f'{seconds}s' if seconds or not (days or hours or minutes) else '') if part)


def level_context(store, item):
    """Match the event's tracking segment; do not bridge missing levels or paused history."""
    if item['kind'] != 'level' or item['data'].get('synthetic'):
        return []
    lines = []
    at, level, cid = item['at'], item['data']['level'], item['id']
    played = item['data'].get('played_level_seconds')
    if played is not None:
        lines.append(f'⏱️ {duration(played)} played from level {level - 1} to {level}')
    row = store.db.execute('SELECT data FROM level_tracking WHERE character=?', (cid,)).fetchone()
    tracking = json.loads(row['data']) if row else {}
    # An exact event identity prevents ambiguous equal-timestamp observations being matched.
    points = tracking.get('points', [])
    matched = next((p for p in points if p.get('event_id') == item.get('event_id')
                    and p['kind'] == 'level' and p['level'] == level and p['at'] == at), None)
    if matched and item.get('event_id') is not None:
        for interval in timeline(tracking)['durations']:
            if interval['finished_at']['unix'] == at and interval['next_level'] == level:
                seconds = interval['elapsed_lower_bound_seconds'] if interval['partial'] else interval['elapsed_seconds']
                label = 'since tracking began (partial level)' if interval['partial'] else f'elapsed since level {level - 1} (includes offline)'
                lines.append(f'🕒 {duration(seconds)} {label}')
                break
    day = datetime.fromtimestamp(at, ZoneInfo('Europe/Oslo')).date()
    start, _ = window(day)
    rows = store.db.execute("SELECT data FROM events WHERE character=? AND kind='level' "
        'AND suppressed=0 AND at>=? AND at<=?', (cid, start, at)).fetchall()
    count = sum(not json.loads(row['data']).get('synthetic') for row in rows)
    if count:
        lines.append(f'📈 {count} recorded level-up{"s" if count != 1 else ""} today · Europe/Oslo')
    return lines


def message(store, item, custom=None):
    """Return send kwargs; no arbitrary game URLs, thumbnail fetches or mention parsing."""
    kind, data = item['kind'], item['data']
    text = emoji(kind, custom) + ' ' + announcement(item)
    details = []
    if data.get('zone'):
        details.append('📍 ' + safe(data['zone']))
    details.extend(level_context(store, item))
    if details:
        head, separator, footer = text.partition('\nRecorded ')
        text = head + '\n' + '\n'.join(details)
        if separator:
            text += separator + footer
    result = {'content': text[:1950]}
    if kind in ('loot', 'equipment'):
        reference = item_reference(data['item'])
        title = reference.get('display_name') or data['item']
        quality = data.get('quality')
        rarity, color = RARITIES.get(quality, ('Quality not recorded', 0x5865F2))
        embed = discord.Embed(title=safe(title)[:256], colour=color)
        embed.description = rarity
        # Classic Era item IDs can be linked to Classic data. Forever-specific items have
        # no verified external database here; retain their names/IDs without inventing links.
        item_id = reference.get('item_id')
        if item_id and item['identity']['client'] == 'classic-era':
            embed.url = f'https://www.wowhead.com/classic/item={item_id}'
        if item_id:
            embed.set_footer(text=f'Item ID: {item_id} · {item["identity"]["client"]}')
        result['embed'] = embed
    elif kind == 'level' and (data.get('maximum') or data['level'] % 10 == 0):
        maximum = data.get('maximum') is True
        embed = discord.Embed(title='🏆 Level cap reached!' if maximum else f'🎉 Level {data["level"]} milestone!',
            description=f'**{safe(item["identity"]["name"])}** reached level {data["level"]}.',
            colour=0xFFD700 if maximum else 0x1EFF00)
        result['embed'] = embed
    return result



def upload_summary(items):
    """One bounded message per exported account batch; summarize volume, never dump events."""
    from collections import Counter
    characters = {}
    for item in items:
        characters.setdefault(item['id'], []).append(item)
    lines = ['📜 **Progress since the last upload**']
    for index, records in enumerate(characters.values()):
        if index >= 12:
            lines.append(f'…and {len(characters) - index} more characters. Full history is retained.')
            break
        real = [item for item in records if not item['data'].get('synthetic')]
        counts = Counter(item['kind'] for item in real)
        levels = sorted({r['data']['level'] for r in real if r['kind'] == 'level'})
        parts = []
        if len(real) != len(records):
            parts.append(f'{len(records) - len(real)} test event(s), not real progress')
        if counts['introduction']:
            parts.append('joined the tracker')
        if levels:
            parts.append(f"level {levels[0]}" if len(levels) == 1 else f"{len(levels)} level-ups (latest level {levels[-1]})")
        labels = {'loot': 'loot finds', 'equipment': 'gear changes', 'death': 'deaths',
                  'zone': 'zone changes', 'session': 'session updates', 'lfg': 'LFG updates'}
        parts.extend(f'{counts[kind]} {label}' for kind, label in labels.items() if counts[kind])
        name = safe(records[0]['identity']['name'])
        line = f"**{name}**: " + ', '.join(parts)
        if sum(len(x) + 1 for x in lines) + len(line) > 1800:
            lines.append('Additional activity is retained in the character history.')
            break
        lines.append(line)
    return {'content': '\n'.join(lines)}
