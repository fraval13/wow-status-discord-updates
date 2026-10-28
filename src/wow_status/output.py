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



CLASS_COLOURS = {'WARRIOR':0xC79C6E,'PALADIN':0xF58CBA,'HUNTER':0xABD473,
                 'ROGUE':0xFFF569,'PRIEST':0xFFFFFF,'SHAMAN':0x0070DE,
                 'MAGE':0x69CCF0,'WARLOCK':0x9482C9,'DRUID':0xFF7D0A}
CLASS_SYMBOLS = {'WARRIOR':'⚔️','PALADIN':'🛡️','HUNTER':'🏹','ROGUE':'🗡️',
                 'PRIEST':'✨','SHAMAN':'⚡','MAGE':'🔮','WARLOCK':'😈','DRUID':'🐾'}


def status_card(item, custom=None, preview=False):
    """Current, selected character observations; cumulative values, never session deltas."""
    custom = custom or {}
    snap, identity = item['snapshot'], item['identity']
    token = snap.get('class_id', str(snap.get('class', '')).upper())

    def icon(name, fallback):
        return custom.get('wow_' + name, fallback)

    class_icon = icon(token.lower(), CLASS_SYMBOLS.get(token, '👤'))
    card = discord.Embed(title=f"{class_icon} {safe(identity['name'])}",
                         colour=CLASS_COLOURS.get(token, 0x5865F2))
    card.description = ('**EXAMPLE — not a real character update**\n' if preview else '')
    if snap.get('class'):
        card.description += safe(snap['class']) + ' · '
    card.description += safe(identity['realm'])
    if token in CLASS_COLOURS:
        card.set_thumbnail(url=f'https://wow.zamimg.com/images/wow/icons/large/classicon_{token.lower()}.jpg')
    friend = item.get('friend', {})
    if friend.get('name_source') in ('addon', 'nickname'):
        card.add_field(name=icon('player','👤') + ' Player', value=safe(friend['display_name']), inline=True)
    if 'level' in snap:
        card.add_field(name=icon('level','⬆️') + ' Level', value=str(snap['level']), inline=True)
    if 'faction' in snap:
        faction = snap['faction']
        symbol = icon(faction.lower(), '🔵' if faction == 'Alliance' else '🔴')
        card.add_field(name=symbol + ' Faction', value=safe(faction), inline=True)
    if 'xp_percent' in snap:
        percent = snap['xp_percent']
        filled = min(10, max(0, int(percent/10 + .5)))
        progress = '▰' * filled + '▱' * (10 - filled)
        card.add_field(name=icon('xp','📈') + ' XP progress',
                       value=f"`{progress}` **{percent:g}%** · {snap['xp_current']:,} / {snap['xp_max']:,}", inline=False)
    elif item.get('settings', {}).get('fields', {}).get('level'):
        value = 'Maximum level' if snap.get('level') == 60 else 'Not observed yet'
        card.add_field(name=icon('xp','📈') + ' XP progress', value=value, inline=False)
    if 'deaths' in snap:
        card.add_field(name=icon('deaths','💀') + ' Total deaths', value=str(snap['deaths']), inline=True)
    if 'quests_completed' in snap:
        card.add_field(name=icon('quests','📜') + ' Completed quests', value=str(snap['quests_completed']), inline=True)
    if 'zone' in snap:
        card.add_field(name=icon('location','📍') + ' Location', value=safe(snap['zone']), inline=False)
    if 'professions' in snap:
        professions = []
        for profession in snap['professions']:
            name = safe(profession['name'])
            symbol = icon(profession.get('key', ''), '⚒️')
            rank = f" **{profession['skill']} / {profession['max_skill']}**" if 'skill' in profession else ' · rank unavailable'
            professions.append(symbol + ' ' + name + rank)
        card.add_field(name='Professions', value='\n'.join(professions) or 'None learned', inline=False)
    elif item.get('settings', {}).get('fields', {}).get('professions'):
        card.add_field(name='Professions', value='Ranks not observed yet', inline=False)
    notes = [identity['client']]
    if snap.get('deaths_since'):
        date = datetime.fromtimestamp(snap['deaths_since'], ZoneInfo('Europe/Oslo')).strftime('%d %b %Y')
        notes.append('Deaths tracked since ' + date)
    if snap.get('quests_source') == 'tracked_since':
        notes.append('Quests tracked since installation')
    elif snap.get('quests_source') == 'game_api':
        notes.append('Quests: game-reported completions')
    card.set_footer(text=' · '.join(notes))
    return card


def upload_summary(items, custom=None, preview=False):
    """One message with tidy character cards, bounded by Discord's combined embed limit."""
    characters = {}
    for item in items:
        characters.setdefault(item['id'], item)
    cards, length = [], 0
    for item in characters.values():
        card = status_card(item, custom, preview)
        if len(cards) == 10 or length + len(card) > 5500:
            break
        cards.append(card)
        length += len(card)
    content = '🧪 **TEST STATUS — example data only**' if preview else '📜 **WoW Progress**'
    if len(cards) < len(characters):
        content += f" · {len(characters) - len(cards)} more changed characters retained in history"
    if any(item['data'].get('synthetic') for item in items):
        content += ' · TEST event, not real progress'
    return {'content': content, 'embeds': cards}
