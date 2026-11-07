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
