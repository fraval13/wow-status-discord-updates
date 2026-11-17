"""The homepage's own scripts: they parse, and they agree with each other (#121).

`scripts/build_homepage.py` copies `website/` as it stands and
`scripts/verify_homepage.py` compares hashes, links and versions, so nothing
else notices a script that no longer parses. `website/flavour.js` is read as
JSON by `test_flavour.py`; `website/app.js` had no check at all.
"""
import functools
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEBSITE = Path(__file__).parents[1] / 'website'
SCRIPTS = sorted(WEBSITE.glob('*.js'))
# The banks app.js asks window.WoWStatusFlavour for, one per preview button.
REQUIRED_BANKS = {'level', 'loot', 'profession-learned', 'introduction'}


@functools.cache
def page():
    return (WEBSITE / 'index.html').read_text(encoding='utf-8')


def banks():
    text = (WEBSITE / 'flavour.js').read_text(encoding='utf-8')
    return json.loads(text.split(' = ', 1)[1].rstrip().removesuffix(';'))


def test_there_are_scripts_to_check():
    assert [path.name for path in SCRIPTS] == ['app.js', 'flavour.js']


@pytest.mark.parametrize('path', SCRIPTS, ids=lambda path: path.name)
def test_every_website_script_parses(path):
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed; the workflow checks this too')
    result = subprocess.run([node, '--check', str(path)], capture_output=True,
                            encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_app_js_only_asks_for_banks_that_flavour_js_has():
    """Renaming a bank threw on page load instead of degrading."""
    available = banks()
    assert REQUIRED_BANKS <= set(available), sorted(REQUIRED_BANKS - set(available))
    source = (WEBSITE / 'app.js').read_text(encoding='utf-8')
    wanted = set(re.findall(r"kind: '([a-z-]+)'", source))
    assert wanted == REQUIRED_BANKS, wanted
    assert wanted <= set(available), sorted(wanted - set(available))
    for kind in sorted(wanted):
        assert len(available[kind]) > 1, f'{kind} needs more than one line to vary'


def test_every_icon_the_preview_asks_for_exists():
    source = (WEBSITE / 'app.js').read_text(encoding='utf-8')
    icons = set(re.findall(r"icon: '([a-z0-9_-]+)'", source))
    assert icons, 'no preview icons found in app.js'
    missing = [name for name in sorted(icons) if not (WEBSITE / f'assets/icons/{name}.jpg').is_file()]
    assert missing == []


# The listing the homepage offers next to the ZIPs (#189). Every link to a CurseForge
# project in the page, README.md and docs/CURSEFORGE.md must point at this one.
CURSEFORGE_URL = 'https://www.curseforge.com/wow/addons/wow-status'
CURSEFORGE_PROJECT = re.compile(r'curseforge\.com/wow/addons/([a-z0-9-]+)', re.I)


class Anchors(HTMLParser):
    """The attributes of every <a> tag, in document order (any quoting or case)."""

    def __init__(self, html):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.append(dict(attrs))


def test_download_panel_offers_the_curseforge_app_next_to_the_zips():
    """#189: both install routes in the download panel, with the update difference stated."""
    panel = re.search(r'<section[^>]*id="downloads".*?</section>', page(), re.S)
    assert panel, 'no download panel'
    hrefs = [link.get('href') for link in Anchors(panel.group()).links]
    assert CURSEFORGE_URL in hrefs, hrefs
    assert {f'/downloads/WoWStatus-{edition}.zip'
            for edition in ('vanilla', 'tbc', 'retail', 'forever')} <= set(hrefs)
    assert 'by hand' in panel.group(), 'the panel no longer says a ZIP is updated by hand'


def test_every_curseforge_link_is_the_listing_and_opens_safely():
    links = [link for link in Anchors(page()).links if 'curseforge.com' in (link.get('href') or '').lower()]
    assert len(links) >= 3, links  # download panel, install step 1, footer
    for link in links:
        assert link['href'] == CURSEFORGE_URL, link
        assert link.get('target') == '_blank', link
        assert {'noopener', 'noreferrer'} <= set((link.get('rel') or '').split()), link
    for name in ('website/index.html', 'README.md', 'docs/CURSEFORGE.md'):
        text = (WEBSITE.parent / name).read_text(encoding='utf-8')
        projects = {slug.lower() for slug in CURSEFORGE_PROJECT.findall(text)}
        assert projects == {'wow-status'}, (name, projects)


# The main-window demo (#195): invented characters in the page itself, a still
# picture of the Activity page without JavaScript and three working tabs with it.
class Demo(HTMLParser):
    """Tags inside the demo section, with their attributes and own text."""

    def __init__(self, html):
        super().__init__()
        self.tags, self.stack = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        item = {'tag': tag, 'attrs': dict(attrs), 'text': ''}
        self.tags.append(item)
        if tag not in ('img', 'input', 'meta', 'link', 'br'):
            self.stack.append(item)

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()['tag'] == tag:
                break

    def handle_data(self, data):
        for item in self.stack:
            item['text'] += data

    def find(self, cls=None, **attrs):
        return [item for item in self.tags
                if (cls is None or cls in (item['attrs'].get('class') or '').split())
                and all(item['attrs'].get(key.replace('_', '-')) == value for key, value in attrs.items())]


def demo_section():
    found = re.search(r'<section[^>]*id="window".*?</section>', page(), re.S)
    assert found, 'no main-window demo'
    return found.group()


def test_demo_is_labelled_as_a_demonstration_with_invented_characters():
    section = demo_section()
    assert 'DEMONSTRATION · INVENTED CHARACTERS' in section
    assert 'A demonstration with invented characters' in section
    assert '<a href="#window">' in page(), 'the side menu does not lead to the demo'


def test_page_has_no_inline_styles_the_content_security_policy_would_block():
    """Caddy serves the site with style-src 'self', so style="" never applies."""
    assert re.search(r'\sstyle\s*=', page()) is None
    assert '<style' not in page()


def test_demo_tabs_each_control_one_panel_and_only_activity_shows_without_js():
    demo = Demo(demo_section())
    tablist = demo.find(role='tablist')
    assert len(tablist) == 1 and 'hidden' in tablist[0]['attrs'], 'the tab row must wait for app.js'
    tabs = demo.find(role='tab')
    assert [tab['text'] for tab in tabs] == ['Activity', 'Leaderboard', 'Characters']  # the addon's order
    panels = demo.find('wow-page')
    assert [tab['attrs']['aria-controls'] for tab in tabs] == [panel['attrs']['id'] for panel in panels]
    # app.js makes them tab panels; without it there is no tab to belong to.
    assert demo.find(role='tabpanel') == []
    assert [('hidden' in panel['attrs']) for panel in panels] == [False, True, True]
    assert [tab['attrs']['aria-selected'] for tab in tabs] == ['true', 'false', 'false']
    assert [tab['attrs'].get('tabindex') for tab in tabs] == [None, '-1', '-1']


def test_demo_controls_are_disabled_until_the_script_runs():
    """Without JavaScript nothing on the still picture pretends to work."""
    demo = Demo(demo_section())
    controls = [item for item in demo.tags if item['tag'] in ('button', 'input') and item['attrs'].get('role') != 'tab']
    assert controls
    assert all('disabled' in item['attrs'] for item in controls), [item['text'] for item in controls]
    source = (WEBSITE / 'app.js').read_text(encoding='utf-8')
    for hook in ('.wow-tabs', '#demo-activity [data-filter]', '#demo-sort', '.demo-section', '#demo-online-only'):
        assert hook in source, hook
    # Every id and class the script looks up is still in the page.
    ids = set(re.findall(r'id="([^"]+)"', page()))
    classes = {name for value in re.findall(r'class="([^"]+)"', page()) for name in value.split()}
    selectors = ' '.join(re.findall(r"querySelector(?:All)?\('([^']+)'\)", source))
    assert {name for name in re.findall(r'#([a-z][\w-]*)', selectors)} <= ids
    assert {name for name in re.findall(r'\.([a-z][\w-]*)', selectors)} <= classes


def test_demo_captions_come_from_the_notification_banks():
    available = banks()
    lines = Demo(demo_section()).find('demo-flavour')
    assert len(lines) >= 5
    for line in lines:
        bank = line['attrs']['data-bank']
        assert bank in available, bank
        # Class roasts need a visible unit in the game, so the demo uses [ANY] only.
        allowed = set()
        for text in available[bank]:
            tagged = re.match(r'^\[([A-Z]+)\] (.+)$', text)
            if not tagged:
                allowed.add(text)
            elif tagged.group(1) == 'ANY':
                allowed.add(tagged.group(2))
        assert line['text'] in allowed, (bank, line['text'])


def duration(seconds):
    days, hours, minutes = seconds // 86400, seconds // 3600 % 24, seconds // 60 % 60
    if days:
        return f'{days}d {hours}h'
    return f'{hours}h {minutes}m' if hours else f'{minutes}m'


def test_demo_leaderboard_starts_sorted_by_level_and_matches_its_data():
    rows = re.findall(r'<tr([^>]*data-name[^>]*)>(.*?)</tr>', demo_section(), re.S)
    assert len(rows) >= 3
    keys = []
    for rank, (attributes, body) in enumerate(rows, 1):
        data = dict(re.findall(r'data-([a-z]+)="([^"]*)"', attributes))
        cells = [re.sub(r'<span class="visually-hidden">.*?</span>|<[^>]+>|●', '', cell).strip()
                 for cell in re.findall(r'<td>(.*?)</td>', body, re.S)]
        assert cells[:2] == [f'{rank}.', data['name']], cells
        assert cells[2] == f"Level {data['level']} ({int(data['xp']) // 10} %)"
        assert cells[3:5] == [data['deaths'], data['quests']]
        assert cells[5] == duration(int(data['played'])), cells  # UI.duration in Theme.lua
        keys.append((int(data['level']), int(data['xp'])))
    assert keys == sorted(keys, reverse=True)


def test_every_image_the_page_shows_exists():
    sources = set(re.findall(r'<img[^>]*\ssrc="/([^"]+)"', page()))
    assert sources
    assert [name for name in sorted(sources) if not (WEBSITE / name).is_file()] == []
