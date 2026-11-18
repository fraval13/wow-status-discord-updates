"""Report display-locale key coverage; partial banks remain useful.

Requires the development dependency lupa. No game or saved player data is read.
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source_keys(root):
    """Literal English UI sources, including text passed through page helpers.

    Dynamic sentences and captions need human review; this is a coverage report,
    not a claim to discover every possible string constructed at runtime.
    """
    keys = set()
    for path in sorted((root / 'addon/shared').glob('*.lua')):
        if path.name.startswith(('Locale', 'Flavour')):
            continue
        source = path.read_text(encoding='utf-8')
        keys.update(re.findall(r'\b(?:T|TF|F)\("((?:[^"\\]|\\.)*)"', source))
        keys.update(re.findall(r'\b(?:label|button|text|check|checkbox|section|say|notify|report|refuse)\(\s*'
                               r'(?:[\w.]+\s*,\s*)?(?:"[a-z_]+"\s*,\s*)?"((?:[^"\\]|\\.)*)"\s*[,)]', source))
        keys.update(re.findall(r'\bregister\("[a-z_]+",\s*"([^"]*)"', source))
        keys.update(re.findall(r'\{title="([^"]*)"', source))
        keys.update(re.findall(r'\{"[a-z_]+", ?"([A-Z][^"]*)"\}', source))
    return sorted(key.replace('\\n', '\n') for key in keys if key and not key.endswith(' ')
                  and not key.startswith(('GameFont', 'Interface', 'Minimap')))


def load_banks(root, edition):
    import lupa.lua51 as lua
    runtime = lua.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('WoWStatusDB = {}')
    folder = root / 'addon' / edition / 'WoWStatus'
    files = (folder / 'WoWStatus.toc').read_text(encoding='utf-8').splitlines()
    for name in files:
        name = name.strip()
        if name == 'Safe.lua' or (name.startswith('Locale') and name.endswith('.lua')):
            runtime.execute((folder / name).read_text(encoding='utf-8'))
    return runtime


def coverage(runtime, keys):
    locale = runtime.globals().WoWStatusLocale
    result = {}
    for code in sorted(locale.banks.keys()):
        if code == 'en':
            continue
        locale.set(code)
        bank = locale.banks[code]
        # Explicit identity translations are covered too (proper names often stay).
        result[code] = [key for key in keys
                        if not bank.exact[key] and locale.T(key) == key]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--edition', choices=('vanilla', 'forever', 'tbc', 'retail'), default='vanilla')
    parser.add_argument('--strict', action='store_true', help='fail if any literal source key is uncovered')
    args = parser.parse_args(argv)
    keys = source_keys(ROOT)
    missing = coverage(load_banks(ROOT, args.edition), keys)
    for code, lines in missing.items():
        print(f'{code}: {len(keys) - len(lines)}/{len(keys)} literal keys covered; {len(lines)} use English fallback')
        for line in lines:
            print(f'  {line!r}')
    return int(args.strict and any(missing.values()))


if __name__ == '__main__':
    raise SystemExit(main())
