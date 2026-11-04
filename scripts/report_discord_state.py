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
MAX_BYTES = 64 * 1024


def group_routes(caddyfile):
    """(path prefix, local port) for every group route in the Caddy config."""
    return re.findall(r'handle_path (/groups/[0-9a-f]+)/\*\s*\{\s*'
                      r'reverse_proxy 127\.0\.0\.1:(\d+)', caddyfile)


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


def problem(body, revision):
    """None when the group's bot is settled, otherwise what to warn about."""
    if body['revision'] != revision:
        return 'serving another revision'
    if body['discord'] in SETTLED:
        return None
    return ' '.join(str(body[key]) for key in ('discord', 'discord_error') if body.get(key))


def report(base, routes, revision, names=None, fetch=read, attempts=12, pause=5,
           sleep=time.sleep):
    """Return one warning per group whose bot did not settle; a fresh bot needs a few
    seconds after the service restarts to log in and reach Discord's gateway."""
    states = {}
    for attempt in range(attempts):
        for prefix, port in routes:
            try:
                states[port] = problem(fetch(base.rstrip('/') + prefix + '/health'), revision)
            except Exception as exc:  # A warning step: report it, never fail the run.
                states[port] = f'health check failed ({type(exc).__name__})'
        if not any(states.values()) or attempt == attempts - 1:
            break
        sleep(pause)
    names = names or {}
    return [f'{names.get(port, "port " + port)}: {state}'
            for port, state in sorted(states.items()) if state]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    routes = group_routes((DEPLOY / 'Caddyfile.production').read_text(encoding='utf-8'))
    names = group_names((DEPLOY / 'install_release.py').read_text(encoding='utf-8'))
    warnings = report(args.url, routes, args.revision, names) if routes else [
        'no group routes found in deploy/Caddyfile.production, so no bot was checked']
    for warning in warnings:
        print(f'::warning title=Discord bot not connected::{warning}. Ingestion is running; '
              'see "Discord bot not connected" in deploy/SERVER.md.')
    if not warnings:
        print(f'Discord bots settled for {len(routes)} group(s).')


if __name__ == '__main__':
    main()
