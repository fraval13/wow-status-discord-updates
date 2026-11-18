"""Run shipped Lua files in TOC order, sharing compiled chunks across clients."""
from pathlib import Path

ADDON_ROOT = Path(__file__).parents[1] / 'addon'
_COMPILED = {}


def edition_files(edition):
    folder = ADDON_ROOT / edition / 'WoWStatus'
    return tuple(folder / line.replace('\\', '/')
                 for raw in (folder / 'WoWStatus.toc').read_text(encoding='utf-8').splitlines()
                 if (line := raw.strip()) and not line.startswith('#'))


def run_addon_file(runtime, path):
    """Compile each source once per Lua runtime type; reread for tests that edit files."""
    source = path.read_text(encoding='utf-8')
    key = (type(runtime), source)
    if key not in _COMPILED:
        compiler = type(runtime)(encoding=None)
        _COMPILED[key] = compiler.eval(
            'function(source) return string.dump(assert((loadstring or load)(source, "<python>"))) end'
        )(source.encode('utf-8'))
    return runtime.eval('loadstring or load')(_COMPILED[key])()


def load_edition(runtime, edition, *, only=None, after_file=None):
    """Load all TOC entries, or a named subset, in their shipped order.

    after_file runs after each file for tests that override a flag before its
    consumers load. Login and edition-specific API stubs stay with the caller.
    """
    files = edition_files(edition)
    folder = ADDON_ROOT / edition / 'WoWStatus'
    if only is not None:
        selected = set(only)
        missing = selected - {path.relative_to(folder).as_posix() for path in files}
        if missing:
            raise ValueError(f'{edition} TOC does not list: {", ".join(sorted(missing))}')
        files = tuple(path for path in files if path.relative_to(folder).as_posix() in selected)
    for path in files:
        if path.suffix.lower() != '.lua':
            raise ValueError(f'Lua test loader cannot execute TOC entry: {path.name}')
        run_addon_file(runtime, path)
        if after_file is not None:
            after_file(path.relative_to(folder).as_posix())
