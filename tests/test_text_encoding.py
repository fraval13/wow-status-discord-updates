"""Tests and tools must not depend on the platform's default text encoding (issue #6).

Windows CI decodes text with the legacy ANSI code page (cp1252) unless an
encoding is given, so a bare ``read_text()`` silently mangles UTF-8 captions.
Ruff's PLW1514 is preview-only and cannot see ``Path.read_text`` on computed
paths, so this guard walks the sources that run in CI or on players' machines.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
# Python sources that run in CI or on players' Windows machines.
SCANNED = ('src', 'scripts', 'tests')

# Callee -> (mode position, encoding position, default mode). Builtin ``open``,
# ``io.open`` and ``os.fdopen`` share a signature; ``.open`` on anything else is
# taken to be ``Path.open``.
OPENERS = {
    'open': (1, 3, 'r'), 'io.open': (1, 3, 'r'), 'os.fdopen': (1, 3, 'r'),
    'codecs.open': (1, 2, 'r'), '.open': (0, 2, 'r'),
    'tempfile.NamedTemporaryFile': (0, 2, 'w+b'), 'tempfile.TemporaryFile': (0, 2, 'w+b'),
    'tempfile.SpooledTemporaryFile': (1, 3, 'w+b'),
}
# Modules whose ``open`` is not a text-file opener (os.open takes flags).
NOT_TEXT_OPEN = {'os', 'tarfile', 'zipfile', 'gzip', 'bz2', 'lzma', 'webbrowser', 'dbm', 'shelve'}
SUBPROCESS_DECODING = {'run', 'check_output', 'Popen'}
SUBPROCESS_ALWAYS_TEXT = {'getoutput', 'getstatusoutput'}


def _callee(func):
    """``open``, ``io.open``, ``.open`` (method on a value) or ``.read_text``."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return f'{func.value.id}.{func.attr}'
        return f'.{func.attr}'
    return None


def _argument(call, name, position):
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return call.args[position] if position is not None and len(call.args) > position else None


def _given(node):
    """True when an argument is present and not a literal ``None``/``False``."""
    return node is not None and not (isinstance(node, ast.Constant) and node.value in (None, False))


def _problem(call):
    callee = _callee(call.func)
    if callee is None:
        return None
    module, _, method = callee.rpartition('.')
    if method in {'read_text', 'write_text'} and '.' in callee:
        position = 0 if method == 'read_text' else 1
        return None if _given(_argument(call, 'encoding', position)) else method
    opener = OPENERS.get(callee) or (
        OPENERS['.open'] if method == 'open' and '.' in callee and module not in NOT_TEXT_OPEN
        and callee not in OPENERS else None)
    if opener:
        mode_position, encoding_position, default = opener
        mode = _argument(call, 'mode', mode_position)
        mode = mode.value if isinstance(mode, ast.Constant) else default if mode is None else ''
        if 'b' not in mode and not _given(_argument(call, 'encoding', encoding_position)):
            return callee.lstrip('.')
        return None
    if callee in {method, f'subprocess.{method}'} and (
            method in SUBPROCESS_ALWAYS_TEXT or method in SUBPROCESS_DECODING and any(
                _given(_argument(call, name, None)) for name in ('text', 'universal_newlines', 'errors'))):
        if not _given(_argument(call, 'encoding', None)):
            return f'subprocess.{method}'
    return None


def unspecified_encodings(source, filename='<source>'):
    """Return sorted ``(line, call)`` for every text I/O call that relies on the locale."""
    return sorted(
        (node.lineno, problem) for node in ast.walk(ast.parse(source, filename))
        if isinstance(node, ast.Call) and (problem := _problem(node)))


BAD = [
    "p.read_text()",
    "p.write_text('x')",
    "p.read_text(encoding=None)",
    "open('f')",
    "open('f', 'w')",
    "io.open('f', 'w')",
    "codecs.open('f')",
    "os.fdopen(fd, 'w')",
    "path.open()",
    "tmp_path.joinpath('x').open('w')",
    "tempfile.NamedTemporaryFile('w')",
    "subprocess.run(cmd, text=True)",
    "subprocess.run(cmd, text=True, encoding=None)",
    "subprocess.run(cmd, errors='replace', capture_output=True)",
    "subprocess.check_output(cmd, universal_newlines=True)",
    "subprocess.getoutput(cmd)",
]
GOOD = [
    "p.read_text(encoding='utf-8')",
    "p.read_text('utf-8')",
    "p.write_text('x', encoding='utf-8')",
    "p.write_text('x', 'utf-8')",
    "open('f', 'rb')",
    "open('f', mode='wb')",
    "open('f', encoding='utf-8')",
    "open('f', 'r', -1, 'utf-8')",
    "io.open('f', 'w', encoding='utf-8')",
    "os.fdopen(fd, 'w', encoding='utf-8')",
    "os.open(path, os.O_WRONLY)",
    "tarfile.open(archive)",
    "path.open('a+b')",
    "path.open('w', -1, 'utf-8')",
    "tempfile.NamedTemporaryFile()",
    "subprocess.run(cmd, text=True, encoding='utf-8')",
    "subprocess.run(cmd, capture_output=True)",
    "subprocess.run(cmd, text=False)",
    "runner.run(cmd, text=True)",
]


def test_guard_flags_each_locale_dependent_call_and_nothing_else():
    assert [line for line, _ in unspecified_encodings('\n'.join(BAD))] == list(range(1, len(BAD) + 1))
    assert unspecified_encodings('\n'.join(GOOD)) == []


def test_no_source_reads_or_writes_text_with_the_locale_encoding():
    problems = [
        f'{path.relative_to(ROOT)}:{line}: {call} without encoding='
        for folder in SCANNED
        for path in sorted((ROOT / folder).rglob('*.py'))
        for line, call in unspecified_encodings(path.read_text(encoding='utf-8'), str(path))
    ]
    assert not problems, 'Pass encoding="utf-8" explicitly:\n' + '\n'.join(problems)
