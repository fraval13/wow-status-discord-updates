"""Generate addon/shared/Flavour<Name>.lua from docs/caption-personalities/<id>/*.json.

Each personality folder holds one JSON file per caption category: a list of
{"en": ..., "nn": ...} pairs, 300 per category (death lines also carry a "tag":
170 ANY and 30 for each class token, 560 in all). Line i of the Nynorsk bank translates line i of the English bank.

    python scripts/build_personalities.py          # write the Lua files
    python scripts/build_personalities.py --check  # fail if they are stale or invalid
    python scripts/build_personalities.py --check --only dwarf  # one personality

After writing, run ``python scripts/sync_addons.py`` to copy them to the editions.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/caption-personalities'
OUTPUT = ROOT / 'addon/shared'

LINES_PER_CATEGORY = 300
# Death: general lines for any class, plus class-specific lines for each class.
DEATH_GENERAL = 170
DEATH_PER_CLASS = 30
MAX_LENGTH = 90
CATEGORIES = ('level', 'introduction', 'loot', 'death', 'zone', 'quest', 'profession_learned',
              'profession', 'dungeon', 'mount', 'reputation', 'unlock', 'pvp')
CLASSES = ('DEATHKNIGHT', 'DEMONHUNTER', 'DRUID', 'EVOKER', 'HUNTER', 'MAGE', 'MONK', 'PALADIN',
           'PRIEST', 'ROGUE', 'SHAMAN', 'WARLOCK', 'WARRIOR')
FORBIDDEN = re.compile(r'[\\"\n\r\t|]')
# Reaction whispers (docs/caption-personalities/<id>/reactions/<type>.json): the
# text a reaction button whispers to a friend, in the chosen personality's voice.
# Keys follow Popups.lua: gz = GZ!, level = Congrats on level N!, f = F,
# gitgood = Git Good, welcome = Welcome!, enjoy = Enjoy <zone>!, congrats =
# Congrats!, congrats_<kind> = P.CONGRATS[kind].
REACTIONS = ('gz', 'level', 'f', 'gitgood', 'welcome', 'enjoy', 'congrats', 'congrats_loot', 'congrats_quest',
             'congrats_profession', 'congrats_dungeon', 'congrats_raid', 'congrats_mount', 'congrats_epicmount',
             'congrats_reputation', 'congrats_unlock', 'congrats_pvp', 'congrats_first')
LINES_PER_REACTION = 300
# Personalities whose reaction voices ship. The others keep captions only until
# their reactions are written and proofread; their reactions/ folders are ignored.
REACTION_VOICES = ('wholesome', 'bard', 'veteran', 'christian', 'dwarf', 'drama')
# The value filled in when whispering; each line of these types holds it exactly once.
PLACEHOLDERS = {'level': '{level}', 'enjoy': '{zone}'}
# Variety: at most this many lines of a reaction file may open with the same two
# words (letters only, any case; a placeholder counts as a word), per language.
MAX_SAME_OPENING = 30


def _opening(text: str) -> str:
    words = re.findall(r"\{\w+\}|[^\W\d_]+(?:['\u2019][^\W\d_]+)*", text.casefold())
    return ' '.join(words[:2])


@dataclass(frozen=True)
class Personality:
    id: str
    name: str
    nn_name: str
    file: str


# Menu order after Classic. Names are shown in the settings and accepted by
# /wstatus personality <name>.
PERSONALITIES = (
    Personality('wholesome', 'Wholesome', 'Hjartevarm', 'FlavourWholesome.lua'),
    Personality('bard', 'Epic bard', 'Episk skald', 'FlavourBard.lua'),
    Personality('veteran', 'Grumpy veteran', 'Grinete veteran', 'FlavourVeteran.lua'),
    Personality('goblin', 'Goblin merchant', 'Goblinkremmar', 'FlavourGoblin.lua'),
    Personality('christian', 'Christian', 'Kristen', 'FlavourChristian.lua'),
    Personality('smug', 'Condescending Christian', 'Nedlatande kristen', 'FlavourSmug.lua'),
    Personality('dwarf', 'Dwarf', 'Dverg', 'FlavourDwarf.lua'),
    Personality('jealous', 'Jealous friend', 'Sjalu venn', 'FlavourJealous.lua'),
    Personality('drama', 'Drama queen', 'Dramadronning', 'FlavourDrama.lua'),
)


class PersonalityError(ValueError):
    """A caption source file breaks the format; nothing has been written."""


def _validate_reactions(personality: Personality, reaction: str, rows: object) -> list[tuple[str, str]]:
    where = f'{personality.id}/reactions/{reaction}.json'
    if not isinstance(rows, list) or len(rows) != LINES_PER_REACTION:
        count = len(rows) if isinstance(rows, list) else 'no'
        raise PersonalityError(f'{where}: {count} lines, need {LINES_PER_REACTION}')
    placeholder = PLACEHOLDERS.get(reaction)
    seen: dict[str, set[str]] = {'en': set(), 'nn': set()}
    result = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != {'en', 'nn'}:
            raise PersonalityError(f'{where}#{number}: need exactly en and nn')
        for lang in ('en', 'nn'):
            text = row[lang]
            if not isinstance(text, str) or not text.strip() or text != text.strip():
                raise PersonalityError(f'{where}#{number}: empty or padded {lang} line')
            if len(text) > MAX_LENGTH or FORBIDDEN.search(text):
                raise PersonalityError(f'{where}#{number}: {lang} line is too long or has a forbidden character')
            braces = text.replace(placeholder, '') if placeholder else text
            if placeholder and text.count(placeholder) != 1:
                raise PersonalityError(f'{where}#{number}: {lang} line needs {placeholder} exactly once')
            if '{' in braces or '}' in braces:
                raise PersonalityError(f'{where}#{number}: {lang} line has a stray brace')
            if text.casefold() in seen[lang]:
                raise PersonalityError(f'{where}#{number}: duplicate {lang} line {text!r}')
            seen[lang].add(text.casefold())
        result.append((row['en'], row['nn']))
    for lang, index in (('en', 0), ('nn', 1)):
        openings: dict[str, int] = {}
        for row in result:
            key = _opening(row[index])
            openings[key] = openings.get(key, 0) + 1
        common, count = max(openings.items(), key=lambda item: item[1])
        if count > MAX_SAME_OPENING:
            raise PersonalityError(f'{where}: {count} {lang} lines open with {common!r}; '
                                   f'at most {MAX_SAME_OPENING}, vary the openings')
    return result


def _validate(personality: Personality, category: str, rows: object) -> list[tuple[str, str, str]]:
    where = f'{personality.id}/{category}.json'
    need = DEATH_GENERAL + DEATH_PER_CLASS * len(CLASSES) if category == 'death' else LINES_PER_CATEGORY
    if not isinstance(rows, list) or len(rows) != need:
        count = len(rows) if isinstance(rows, list) else 'no'
        raise PersonalityError(f'{where}: {count} lines, need {need}')
    seen: dict[str, set[str]] = {'en': set(), 'nn': set()}
    tags: dict[str, int] = {}
    result = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise PersonalityError(f'{where}#{number}: not an object')
        for lang in ('en', 'nn'):
            text = row.get(lang)
            if not isinstance(text, str) or not text.strip() or text != text.strip():
                raise PersonalityError(f'{where}#{number}: empty or padded {lang} line')
            if len(text) > MAX_LENGTH or FORBIDDEN.search(text) or text.startswith('['):
                raise PersonalityError(f'{where}#{number}: {lang} line is too long or has a forbidden character')
            if text.casefold() in seen[lang]:
                raise PersonalityError(f'{where}#{number}: duplicate {lang} line {text!r}')
            seen[lang].add(text.casefold())
        tag = row.get('tag', '')
        if category == 'death':
            if tag != 'ANY' and tag not in CLASSES:
                raise PersonalityError(f'{where}#{number}: unknown death tag {tag!r}')
            tags[tag] = tags.get(tag, 0) + 1
        elif tag:
            raise PersonalityError(f'{where}#{number}: only death lines carry a tag')
        result.append((tag, row['en'], row['nn']))
    if category == 'death':
        wanted = {'ANY': DEATH_GENERAL, **{token: DEATH_PER_CLASS for token in CLASSES}}
        wrong = [f'{tag} {tags.get(tag, 0)}/{count}' for tag, count in wanted.items() if tags.get(tag, 0) != count]
        if wrong:
            raise PersonalityError(f'{where}: death tag counts are off: ' + ', '.join(wrong))
    return result


def _lua(text: str) -> str:
    return '"' + text + '"'


def render(personality: Personality, source: Path = SOURCE) -> str:
    banks = {}
    for category in CATEGORIES:
        path = source / personality.id / f'{category}.json'
        if not path.is_file():
            raise PersonalityError(f'{personality.id}: missing {category}.json')
        try:
            rows = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise PersonalityError(f'{personality.id}/{category}.json: {error}') from error
        banks[category] = _validate(personality, category, rows)
    reactions = {}
    for reaction in REACTIONS if personality.id in REACTION_VOICES else ():
        path = source / personality.id / 'reactions' / f'{reaction}.json'
        if not path.is_file():
            raise PersonalityError(f'{personality.id}: missing reactions/{reaction}.json')
        try:
            rows = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            raise PersonalityError(f'{personality.id}/reactions/{reaction}.json: {error}') from error
        reactions[reaction] = _validate_reactions(personality, reaction, rows)
    out = [
        f'-- Generated from docs/caption-personalities/{personality.id}/ by',
        '-- scripts/build_personalities.py. Do not edit; edit the JSON and rebuild.',
        '-- Captions are presentation only; reactions are whispered to a friend when a',
        '-- reaction button is clicked. Nynorsk line i translates English line i.',
        'if not WoWStatusPersonalities then return end',
        f'WoWStatusPersonalities.register("{personality.id}", {{',
        f'    name = {_lua(personality.name)}, nn_name = {_lua(personality.nn_name)},',
    ]
    for lang, index in (('en', 1), ('nn', 2)):
        out.append(f'    {lang} = {{')
        for category in CATEGORIES:
            out.append(f'        {category} = {{')
            for row in banks[category]:
                prefix = f'[{row[0]}] ' if row[0] else ''
                out.append(f'            {_lua(prefix + row[index])},')
            out.append('        },')
        out.append('    },')
    if reactions:
        out.extend(_render_reactions(reactions))
    out.append('})')
    return '\n'.join(out) + '\n'


def _render_reactions(reactions: dict[str, list[tuple[str, str]]]) -> list[str]:
    out = ['    reactions = {']
    for lang, index in (('en', 0), ('nn', 1)):
        out.append(f'        {lang} = {{')
        for reaction in REACTIONS:
            out.append(f'            {reaction} = {{')
            for row in reactions[reaction]:
                out.append(f'                {_lua(row[index])},')
            out.append('            },')
        out.append('        },')
    out.append('    },')
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='report stale or invalid files; write nothing')
    parser.add_argument('--only', metavar='ID', help='build or check one personality, e.g. while writing it')
    args = parser.parse_args(argv)
    chosen = [p for p in PERSONALITIES if args.only in (None, p.id)]
    if not chosen:
        print(f'build_personalities: unknown personality {args.only!r}; add it to PERSONALITIES', file=sys.stderr)
        return 1
    try:
        rendered = {p.file: render(p) for p in chosen}
    except PersonalityError as error:
        print(f'build_personalities: {error}', file=sys.stderr)
        return 1
    stale = []
    for name, text in rendered.items():
        target = OUTPUT / name
        current = target.read_text(encoding='utf-8') if target.is_file() else None
        if current != text:
            stale.append(name)
            if not args.check:
                target.write_bytes(text.encode('utf-8'))
    if args.check and stale:
        print('build_personalities: stale ' + ', '.join(stale) + '; run scripts/build_personalities.py',
              file=sys.stderr)
        return 1
    print(('checked ' if args.check else 'wrote ') + str(len(rendered) if args.check else len(stale)) + ' file(s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
