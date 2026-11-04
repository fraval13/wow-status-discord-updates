"""Render the production Caddyfile from the private group configuration.

Group names are shared secrets and their route keys are derived from them, so the
routes are not tracked in Git. On the server, as root:

    cd /opt/wow-character-status/current
    .venv/bin/python -B deploy/render_caddyfile.py | diff -u /etc/caddy/Caddyfile -

shows what would change (a dry run). See deploy/SERVER.md for installing the result.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import install_release  # the receiver owns the group-config rules

DEPLOY = Path(__file__).resolve().parent
if str(DEPLOY.parent / 'src') not in sys.path:
    sys.path.insert(0, str(DEPLOY.parent / 'src'))  # this revision's key derivation, also without the venv
from wow_status.group_routing import group_key  # noqa: E402

TEMPLATE = DEPLOY / 'Caddyfile.production.template'
GROUPS = install_release.GROUPS_FILE
MARKER = '    # GROUP ROUTES\n'
# (route key, loopback port) of each group route in a rendered or live Caddyfile.
ROUTES = re.compile(r'handle_path /groups/([0-9a-f]{22})/\* \{\s*reverse_proxy 127\.0\.0\.1:([0-9]+)')
ROUTE = '''    handle_path /groups/{key}/* {{
        reverse_proxy 127.0.0.1:{port} {{
            header_up X-WoW-Client-IP {{http.request.remote.host}}
        }}
    }}
'''


def render(raw_groups, template=None):
    """Caddyfile text with one route per group, in port order, from the raw groups.json data."""
    groups = install_release.validate_groups(raw_groups)
    template = TEMPLATE.read_text(encoding='utf-8') if template is None else template
    if template.count(MARKER) != 1:
        raise ValueError('The Caddyfile template needs exactly one group routes marker')
    ordered = sorted(groups.values(), key=lambda group: group['port'])
    keys = [group_key(group['name']) for group in ordered]
    if len(set(keys)) != len(keys):  # what Caddy routes on, beyond validate_groups' case-folding
        raise ValueError('Two groups share a route key; choose different names')
    routes = ''.join(ROUTE.format(key=key, port=group['port']) for key, group in zip(keys, ordered))
    return template.replace(MARKER, routes)


def routes(caddyfile):
    return set(ROUTES.findall(caddyfile))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--groups-config', type=Path, default=GROUPS,
                        help='Private groups.json (default: %(default)s)')
    parser.add_argument('--output', type=Path,
                        help='Replace this file atomically (mode 0644) instead of printing')
    args = parser.parse_args(argv)
    text = render(json.loads(args.groups_config.read_text(encoding='utf-8')))
    if args.output:
        temporary = args.output.with_name(args.output.name + '.partial')
        temporary.unlink(missing_ok=True)
        temporary.write_text(text, encoding='utf-8', newline='\n')
        temporary.chmod(0o644)
        os.replace(temporary, args.output)  # replaces a symlink itself, never its target
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
