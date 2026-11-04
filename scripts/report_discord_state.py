"""After a deploy, warn (never fail) when a group's Discord bot is not connected.

Ingestion stays healthy while Discord is down, so the deploy itself passes; this
step keeps a revoked token or a removed bot visible on the workflow run instead.
Group routes are read from the Caddy config that serves them.
"""
import argparse
import ast
import json
import re
import time
import urllib.request
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / 'deploy'
SETTLED = ('ready', 'disabled')
# States that can still change within this step's polling window.
TRANSIENT = ('starting', 'reconnecting', 'health check failed')
MOVED = 'serving another revision'
MAX_BYTES = 64 * 1024


def group_routes(caddyfile):
    """(path prefix, local port) for every group route in the Caddy config; the port
    is None when a group's block has no local upstream."""
    routes = []
    for block in re.split(r'(?=handle_path )', caddyfile):
        prefix = re.match(r'handle_path (/groups/[0-9a-f]+)/\*', block)
        if prefix:
            port = re.search(r'reverse_proxy 127\.0\.0\.1:(\d+)', block)
            routes.append((prefix.group(1), port.group(1) if port else None))
    return routes


def group_names(receiver):
    """Port -> group name, from the receiver's GROUPS table."""
    for node in ast.parse(receiver).body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'GROUPS'
                                                for t in node.targets):
            return {str(port): name for name, port in ast.literal_eval(node.value).items()}
    return {}


def read(url):
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=10) as response:
        data = response.read(MAX_BYTES + 1)
        if response.status != 200 or len(data) > MAX_BYTES:
            raise ValueError('Invalid or oversized health response')
        return json.loads(data)


def clean(value):
    """The public site is untrusted: keep its words, never its markup or line breaks."""
    return re.sub(r'[^A-Za-z0-9 ._-]', '?', str(value))[:80]


def problem(body, revision):
    """None when the group's bot is settled, otherwise what to warn about."""
    if body['revision'] != revision:
        return MOVED
    if body['discord'] in SETTLED:
        return None
    return ' '.join(clean(body[key]) for key in ('discord', 'discord_error') if body.get(key))


def report(base, routes, revision, names=None, fetch=None, attempts=12, pause=5,
           sleep=time.sleep, notices=None):
    """Return one warning per group whose bot did not settle; a fresh bot needs a few
    seconds after the service restarts to log in and reach Discord's gateway. A group
    a newer deploy already replaced goes to ``notices`` instead."""
    fetch = fetch or read
    states = {}
    for attempt in range(attempts):
        for prefix, port in routes:
            try:
                states[port] = problem(fetch(base.rstrip('/') + prefix + '/health'), revision)
            except Exception as exc:  # A warning step: report it, never fail the run.
                states[port] = f'health check failed ({type(exc).__name__})'
        if (attempt == attempts - 1 or not any(
                state and state.startswith(TRANSIENT) for state in states.values())):
            break
        sleep(pause)
    names, warnings = names or {}, []
    for port, state in sorted(states.items()):
        name = names.get(port, 'port ' + port)
        if state == MOVED:
            if notices is not None:
                notices.append(f'{name} already serves another revision, so its bot was not '
                               'checked for this one')
        elif state:
            warnings.append(f'{name}: {state}')
    return warnings


def command_text(text):
    """Escape a workflow command's message so it stays one annotation."""
    return text.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    routes = group_routes((DEPLOY / 'Caddyfile.production').read_text(encoding='utf-8'))
    names = group_names((DEPLOY / 'install_release.py').read_text(encoding='utf-8'))
    unreadable = [prefix for prefix, port in routes if port is None]
    routes = [(prefix, port) for prefix, port in routes if port is not None]
    warnings = [f'{prefix}: no local upstream found in deploy/Caddyfile.production, not checked'
                for prefix in unreadable]
    notices = []
    if routes:
        warnings += report(args.url, routes, args.revision, names, notices=notices)
    elif not unreadable:
        warnings.append('no group routes found in deploy/Caddyfile.production, '
                        'so no bot was checked')
    for warning in warnings:
        print('::warning title=Discord bot not connected::' + command_text(
            f'{warning}. Ingestion is running; see "Discord bot not connected" in '
            'deploy/SERVER.md.'))
    for notice in notices:
        print('::notice title=Discord bot not checked::' + command_text(notice) + '.')
    if not warnings:
        print(f'Discord bots settled for {len(routes)} group(s).')


if __name__ == '__main__':
    main()
