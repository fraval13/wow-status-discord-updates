"""The homepage's own scripts: they parse, and they agree with each other (#121).

`scripts/build_homepage.py` copies `website/` as it stands and
`scripts/verify_homepage.py` compares hashes, links and versions, so nothing
else notices a script that no longer parses. `website/flavour.js` is read as
JSON by `test_flavour.py`; `website/app.js` had no check at all.
"""
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
    page = (WEBSITE / 'index.html').read_text(encoding='utf-8')
    panel = re.search(r'<section[^>]*id="downloads".*?</section>', page, re.S)
    assert panel, 'no download panel'
    hrefs = [link.get('href') for link in Anchors(panel.group()).links]
    assert CURSEFORGE_URL in hrefs, hrefs
    assert {f'/downloads/WoWStatus-{edition}.zip'
            for edition in ('vanilla', 'tbc', 'retail', 'forever')} <= set(hrefs)
    assert 'by hand' in panel.group(), 'the panel no longer says a ZIP is updated by hand'


def test_every_curseforge_link_is_the_listing_and_opens_safely():
    page = (WEBSITE / 'index.html').read_text(encoding='utf-8')
    links = [link for link in Anchors(page).links if 'curseforge.com' in (link.get('href') or '').lower()]
    assert len(links) >= 3, links  # download panel, install step 1, footer
    for link in links:
        assert link['href'] == CURSEFORGE_URL, link
        assert link.get('target') == '_blank', link
        assert {'noopener', 'noreferrer'} <= set((link.get('rel') or '').split()), link
    for name in ('website/index.html', 'README.md', 'docs/CURSEFORGE.md'):
        text = (WEBSITE.parent / name).read_text(encoding='utf-8')
        projects = {slug.lower() for slug in CURSEFORGE_PROJECT.findall(text)}
        assert projects == {'wow-status'}, (name, projects)
