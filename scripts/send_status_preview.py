"""Render a fictional status card. --send explicitly posts it to a configured group."""
import argparse
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

from wow_status.output import upload_summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', action='store_true', help='Post one clearly labelled example to Discord')
    parser.add_argument('--group', default='navsquad')
    parser.add_argument('--config', default='/etc/wow-character-status/config.json')
    args = parser.parse_args()
    item = json.loads((Path(__file__).resolve().parents[1] / 'tests/fixtures/status_preview.json').read_text())
    custom = {}
    config = json.loads(Path(args.config).read_text())[args.group] if args.send else None
    api = 'https://discord.com/api/v10'
    headers = {'User-Agent': 'DiscordBot (https://github.com/fraval13/wow-status-discord-updates, 0.10.0)'}
    if config:
        headers['Authorization'] = 'Bot ' + config['bot_token']
        request = urllib.request.Request(api + '/guilds/' + str(config['guild_id']) + '/emojis', headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            for entry in json.load(response):
                if entry.get('available', True) and not entry.get('roles'):
                    custom[entry['name']] = '<' + ('a' if entry.get('animated') else '') + ':' + entry['name'] + ':' + entry['id'] + '>'
    rendered = upload_summary([item], custom, preview=True)
    payload = {'content': rendered['content'], 'embeds': [card.to_dict() for card in rendered['embeds']],
               'allowed_mentions': {'parse': []}}
    if not args.send:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    payload.update(nonce=hashlib.sha256(('0.10.0:' + args.group).encode()).hexdigest()[:24], enforce_nonce=True)
    headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(api + '/channels/' + str(config['channel_id']) + '/messages',
        data=json.dumps(payload).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(request, timeout=30) as response:
        message = json.load(response)
    print('Sent labelled example: https://discord.com/channels/' + str(config['guild_id']) + '/' + str(config['channel_id']) + '/' + message['id'])


if __name__ == '__main__':
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'Discord preview failed (HTTP {error.code}); credentials were not printed.') from None
