"""Code must not depend on the platform's default text encoding (issue #6).

Windows decodes text with the legacy ANSI code page (cp1252) unless an encoding
is given, so a bare ``read_text()`` silently mangles UTF-8 captions.

Two layers enforce this. CI runs pytest with ``PYTHONWARNDEFAULTENCODING=1`` and
pytest turns ``EncodingWarning`` into an error, which catches every text API on
the paths the tests exercise. This static guard backs that up for code the tests
never run (installers, deploy scripts), using a deliberately small, precise list
of calls. Ruff's PLW1514 is preview-only and misses ``Path.read_text`` on
computed paths, so it cannot do this job.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCANNED = ('src', 'scripts', 'deploy', 'tests')

# Callee -> (mode position, encoding position or None if keyword-only, default mode).
OPENERS = {
    'open': (1, 3, 'r'), 'io.open': (1, 3, 'r'), 'os.fdopen': (1, 3, 'r'),
    'codecs.open': (1, 2, 'r'), 'gzip.open': (1, 3, 'rb'), 'bz2.open': (1, 3, 'rb'),
    'lzma.open': (1, None, 'rb'),
}
SUBPROCESS_DECODING = {'run', 'check_output', 'Popen'}
SUBPROCESS_ALWAYS_TEXT = {'getoutput', 'getstatusoutput'}


def _callee(func):
    """``open``, ``io.open`` (module or variable name) or ``.read_text`` (any other receiver)."""
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
    """True unless absent or a literal ``None``/``False``."""
    return node is not None and not (isinstance(node, ast.Constant) and node.value in (None, False))


def _explicit_encoding(node):
    """An encoding that does not defer to the locale (``None``/``'locale'`` do)."""
    return _given(node) and not (isinstance(node, ast.Constant) and node.value == 'locale')


def _problem(call):
    callee = _callee(call.func)
    if callee is None:
        return None
    method = callee.rpartition('.')[2]
    if method in {'read_text', 'write_text'} and callee != method:
        position = 0 if method == 'read_text' else 1
        return None if _explicit_encoding(_argument(call, 'encoding', position)) else method
    if callee in OPENERS:
        mode_position, encoding_position, default = OPENERS[callee]
        mode = _argument(call, 'mode', mode_position)
        mode = default if mode is None else mode.value if isinstance(mode, ast.Constant) else None
        binary = isinstance(mode, str) and 'b' in mode
        if not binary and not _explicit_encoding(_argument(call, 'encoding', encoding_position)):
            return callee
        return None
    decodes = method in SUBPROCESS_ALWAYS_TEXT or method in SUBPROCESS_DECODING and any(
        _given(_argument(call, name, None)) for name in ('text', 'universal_newlines', 'errors'))
    if callee in {method, f'subprocess.{method}'} and decodes and not _explicit_encoding(
            _argument(call, 'encoding', None)):
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
    "p.read_text(encoding='locale')",
    "gzip.open('f', 'rt')",
    "open('f', mode)",
    "open('f', 0)",
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
    "gzip.open('f')",
    "gzip.open('f', 'rt', encoding='utf-8')",
    "zipfile.ZipFile(p).open('WoWStatus/WoWStatus.toc')",
    "opener.open(url)",
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
