"""Parse a deliberately small data-only subset of WoW SavedVariables Lua.

No Lua runtime, evaluation, function calls, expressions, or metatables are accepted.
"""
import re

MAX_BYTES = 2 * 1024 * 1024
TOKEN = re.compile(
    r'\s+|--[^\n]*|(?P<string>"(?:[^"\\\r\n]|\\(?:[abfnrtv\\"\']|\d{1,3}|\r?\n))*"|'
    r"'(?:[^'\\\r\n]|\\(?:[abfnrtv\\\"']|\d{1,3}|\r?\n))*')|"
    r'(?P<number>-?\d+(?:\.\d+)?)|(?P<word>[A-Za-z_][A-Za-z_0-9]*)|(?P<punct>[{}\[\]=,;])'
)


class ParseError(ValueError):
    pass


def _string(raw):
    value = raw[1:-1]
    escapes = dict(zip('abfnrtv', '\a\b\f\n\r\t\v'))

    # Build bytes so Lua's decimal UTF-8 escapes round-trip non-ASCII names.
    chunks = bytearray()
    position = 0

    def unescape(match):
        char = match.group(1)
        if char.isdigit():
            number = int(char)
            if number > 255:
                raise ParseError('Invalid decimal escape')
            return bytes([number])
        return escapes.get(char, '\n' if char in ('\n', '\r\n') else char).encode('utf-8')

    # Lua decimal escapes represent UTF-8 bytes, including escaped high bytes.
    for match in re.finditer(r'\\(\d{1,3}|\r?\n|.)', value):
        chunks.extend(value[position:match.start()].encode('utf-8'))
        chunks.extend(unescape(match))
        position = match.end()
    chunks.extend(value[position:].encode('utf-8'))
    try:
        return chunks.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ParseError('Invalid UTF-8 in Lua string') from exc


def parse(text):
    if len(text.encode('utf-8')) > MAX_BYTES:
        raise ParseError('SavedVariables file exceeds 2 MiB')
    tokens = []
    pos = 0
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            raise ParseError(f'Unsupported Lua syntax at offset {pos}')
        pos = match.end()
        if match.lastgroup:
            tokens.append((match.lastgroup, match.group()))
        if len(tokens) > 200_000:
            raise ParseError('Too many tokens')
    index = 0

    def take(expected=None):
        nonlocal index
        if index >= len(tokens):
            raise ParseError('Unexpected end of file')
        token = tokens[index]
        if expected is not None and token[1] != expected:
            raise ParseError(f'Expected {expected}')
        index += 1
        return token

    def value(depth=0):
        if depth > 24:
            raise ParseError('Table nesting is too deep')
        kind, raw = take()
        if kind == 'string':
            return _string(raw)
        if kind == 'number':
            return float(raw) if '.' in raw else int(raw)
        if raw in ('true', 'false', 'nil'):
            return {'true': True, 'false': False, 'nil': None}[raw]
        if raw != '{':
            raise ParseError('Only literal values are allowed')
        result = {}
        implicit = 1
        while index < len(tokens) and tokens[index][1] != '}':
            if tokens[index][1] == '[':
                take('[')
                key = value(depth + 1)
                if type(key) not in (str, int):
                    raise ParseError('Invalid table key')
                take(']')
                take('=')
                item = value(depth + 1)
            elif (index + 1 < len(tokens) and tokens[index][0] == 'word'
                  and tokens[index + 1][1] == '='):
                key = take()[1]
                take('=')
                item = value(depth + 1)
            else:
                key, item = implicit, value(depth + 1)
                implicit += 1
            if key in result:
                raise ParseError('Duplicate table key')
            result[key] = item
            if index < len(tokens) and tokens[index][1] in (',', ';'):
                take()
            elif index < len(tokens) and tokens[index][1] != '}':
                raise ParseError('Expected table separator')
        take('}')
        return result

    take('WoWStatusDB')
    take('=')
    result = value()
    if index != len(tokens) or not isinstance(result, dict):
        raise ParseError('Expected one WoWStatusDB table assignment')
    return result
