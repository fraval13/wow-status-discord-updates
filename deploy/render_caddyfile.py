"""Render the production Caddyfile from the private group configuration.

Group names are shared secrets and their route keys are derived from them, so the
routes are not tracked in Git. On the server, as root:

    cd /opt/wow-character-status/current
    .venv/bin/python deploy/render_caddyfile.py | diff -u /etc/caddy/Caddyfile -

shows what would change (a dry run). See deploy/SERVER.md for installing the result.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent
TEMPLATE = DEPLOY / 'Caddyfile.production.template'
GROUPS = Path('/etc/wow-character-status/groups.json')
MARKER = '    # GROUP ROUTES\n'
ROUTE = '''    handle_path /groups/{key}/* {{
        reverse_proxy 127.0.0.1:{port} {{
            header_up X-WoW-Client-IP {{http.request.remote.host}}
        }}
    }}
'''


def _receiver():
    """The deployment receiver owns the group-config rules; reuse them, don't copy them."""
    spec = importlib.util.spec_from_file_location('wow_status_receiver', DEPLOY / 'install_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_groups(raw):
    return _receiver().validate_groups(raw)


def render(raw_groups, template=None):
    """Caddyfile text with one route per group, in port order, from the raw groups.json data."""
    source = str(DEPLOY.parent / 'src')
    if source not in sys.path:
        sys.path.insert(0, source)  # the release's own key derivation, also without the venv
    from wow_status.group_routing import group_key
    groups = validate_groups(raw_groups)
    template = TEMPLATE.read_text(encoding='utf-8') if template is None else template
    if template.count(MARKER) != 1:
        raise ValueError('The Caddyfile template needs exactly one group routes marker')
    routes = ''.join(ROUTE.format(key=group_key(group['name']), port=group['port'])
                     for group in sorted(groups.values(), key=lambda group: group['port']))
    return template.replace(MARKER, routes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--groups-config', type=Path, default=GROUPS,
                        help='Private groups.json (default: %(default)s)')
    parser.add_argument('--output', type=Path, help='Write here (mode 0644) instead of standard output')
    args = parser.parse_args(argv)
    text = render(json.loads(args.groups_config.read_text(encoding='utf-8')))
    if args.output:
        args.output.write_text(text, encoding='utf-8', newline='\n')
        args.output.chmod(0o644)
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
