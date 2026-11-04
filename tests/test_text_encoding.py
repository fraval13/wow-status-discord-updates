"""Tests must not depend on the platform's default text encoding (issue #6).

Windows CI decodes text with the legacy ANSI code page (cp1252) unless an
encoding is given, so a bare ``read_text()`` silently mangles UTF-8 captions.
Ruff's PLW1514 cannot see ``Path.read_text`` on computed paths, so this guard
walks the test sources instead.
"""
import ast
from pathlib import Path

TESTS = Path(__file__).parent


def _keywords(call):
    return {keyword.arg for keyword in call.keywords}


def _is_binary_mode(mode):
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and 'b' in mode.value


def unspecified_encodings(source, filename='<test>'):
    """Return ``(line, call)`` for every text I/O call that relies on the locale."""
    problems = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.Call):
            continue
        func, keywords = node.func, _keywords(node)
        if 'encoding' in keywords:
            continue
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, 'id', None)
        if name == 'read_text' and isinstance(func, ast.Attribute) and not node.args:
            problems.append((node.lineno, 'read_text'))
        elif name == 'write_text' and isinstance(func, ast.Attribute) and len(node.args) < 2:
            problems.append((node.lineno, 'write_text'))
        elif name == 'open' and isinstance(func, ast.Name):
            mode = node.args[1] if len(node.args) > 1 else next(
                (keyword.value for keyword in node.keywords if keyword.arg == 'mode'), None)
            if not _is_binary_mode(mode):
                problems.append((node.lineno, 'open'))
        elif name in {'run', 'check_output', 'Popen'} and keywords & {'text', 'universal_newlines'}:
            problems.append((node.lineno, f'subprocess.{name}'))
    return problems


def test_guard_flags_locale_dependent_calls():
    source = '\n'.join([
        "p.read_text()",
        "p.write_text('x')",
        "open('f')",
        "open('f', 'w')",
        "subprocess.run(cmd, text=True)",
        "p.read_text(encoding='utf-8')",
        "p.write_text('x', encoding='utf-8')",
        "p.write_text('x', 'utf-8')",
        "open('f', 'rb')",
        "open('f', mode='wb')",
        "open('f', encoding='utf-8')",
        "subprocess.run(cmd, text=True, encoding='utf-8')",
        "subprocess.run(cmd, capture_output=True)",
    ])
    assert unspecified_encodings(source) == [
        (1, 'read_text'), (2, 'write_text'), (3, 'open'), (4, 'open'), (5, 'subprocess.run')]


def test_no_test_reads_or_writes_text_with_the_locale_encoding():
    problems = [
        f'{path.name}:{line}: {call} without encoding='
        for path in sorted(TESTS.glob('*.py'))
        for line, call in unspecified_encodings(path.read_text(encoding='utf-8'), str(path))
    ]
    assert not problems, 'Pass encoding="utf-8" explicitly:\n' + '\n'.join(problems)
