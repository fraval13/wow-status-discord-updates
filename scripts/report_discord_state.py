"""After a deploy, warn (never fail) when a group's Discord bot is not connected.

Ingestion stays healthy while Discord is down, so the deploy itself passes; this
step keeps a revoked token or a removed bot visible on the workflow run instead.
Group route keys are private (issue #1), so they come from the optional "route" of
each instance in the WOW_STATUS_DISCORD_CONFIG secret; warnings name the instance.
"""
import argparse
import json
import os
import re
import time
import urllib.request

ROUTE = re.compile(r'[0-9a-f]{22}')
SETTLED = ('ready', 'disabled')
# States that can still change within this step's polling window.
TRANSIENT = ('starting', 'reconnecting', 'health check failed')
MOVED = 'serving another revision'
MAX_BYTES = 64 * 1024


def configured_routes(raw):
    """(path prefix, instance) for each instance with a route in the Discord secret, and
    how many instances have none. Never echoes the secret: it is malformed or not."""
    try:
        config = json.loads(raw) if raw and raw.strip() else {}
    except ValueError:
        config = None
    if not isinstance(config, dict) or not all(isinstance(v, dict) for v in config.values()):
        raise ValueError('WOW_STATUS_DISCORD_CONFIG is not a JSON object of instances')
    routes, missing = [], 0
    for instance, values in sorted(config.items()):
        route = values.get('route')
        if isinstance(route, str) and ROUTE.fullmatch(route):
            print('::add-mask::' + route)  # a route key alone admits someone to the group
            routes.append(('/groups/' + route, clean(instance)))
        else:
            missing += 1
    return routes, missing


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
    warnings, notices = [], []
    try:
        routes, missing = configured_routes(os.environ.get('WOW_STATUS_DISCORD_CONFIG', ''))
    except ValueError as exc:
        routes, missing = [], 0
        warnings.append(str(exc) + ', so no bot was checked')
    if missing:
        notices.append(f'{missing} instance(s) in WOW_STATUS_DISCORD_CONFIG have no "route", '
                       'so their bots were not checked (deploy/SERVER.md)')
    if routes:
        names = {instance: instance for _, instance in routes}
        warnings += report(args.url, routes, args.revision, names, notices=notices)
    elif not warnings and not missing:
        notices.append('no group routes in WOW_STATUS_DISCORD_CONFIG, so no bot was checked '
                       '(deploy/SERVER.md)')
    for warning in warnings:
        print('::warning title=Discord bot not connected::' + command_text(
            f'{warning}. Ingestion is running; see "Discord bot not connected" in '
            'deploy/SERVER.md.'))
    for notice in notices:
        print('::notice title=Discord bot not checked::' + command_text(notice) + '.')
    if routes and not warnings:
        print(f'Discord bots settled for {len(routes)} group(s).')


if __name__ == '__main__':
    main()
