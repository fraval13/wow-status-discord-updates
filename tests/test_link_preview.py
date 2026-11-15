"""A pasted homepage link shows a large image card in Discord (issue #190)."""
import importlib.util
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PREVIEW = ROOT / 'website/assets/link-preview.png'


def load_builder():
    spec = importlib.util.spec_from_file_location('homepage_build_preview', ROOT / 'scripts/build_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def page():
    return (ROOT / 'website/index.html').read_text(encoding='utf-8')


def tags(html):
    parser = builder.MetaTags()
    parser.feed(html)
    return parser.tags


def test_homepage_has_complete_open_graph_and_twitter_tags():
    found = tags(page())
    assert found['og:type'] == 'website'
    assert found['og:site_name'] == 'WoW Status'
    assert found['og:url'] == 'https://wow.frankvalde.com/'
    assert found['og:image'] == found['twitter:image'] == 'https://wow.frankvalde.com/assets/link-preview.png'
    assert (found['og:image:width'], found['og:image:height']) == ('1200', '630')
    assert found['twitter:card'] == 'summary_large_image'
    assert found['twitter:title'] == found['og:title']
    assert found['twitter:description'] == found['og:description']
    assert found['og:image:alt'] and found['twitter:image:alt']
    assert builder.link_preview_path(page()) == '/assets/link-preview.png'


def test_committed_preview_is_a_1200_by_630_png():
    data = PREVIEW.read_bytes()
    assert builder.png_size(data) == (1200, 630)
    builder.check_link_preview(page(), data)


@pytest.mark.parametrize('change', [
    lambda html: html.replace('summary_large_image', 'summary'),
    lambda html: html.replace('<meta property="og:image:width" content="1200">', ''),
    lambda html: html.replace('link-preview.png', 'adventure.webp'),
    lambda html: html.replace('name="twitter:image" content="https://wow.frankvalde.com/assets/link-preview.png"',
                              'name="twitter:image" content="https://wow.frankvalde.com/assets/other.png"'),
    lambda html: html.replace('https://wow.frankvalde.com/assets/link-preview.png',
                              'http://wow.frankvalde.com/assets/link-preview.png'),
])
def test_incomplete_preview_tags_are_refused(change):
    html = change(page())
    assert html != page()
    with pytest.raises(ValueError, match='link preview tags'):
        builder.check_link_preview(html, PREVIEW.read_bytes())


@pytest.mark.parametrize('data', [
    b'',
    (ROOT / 'website/assets/adventure.webp').read_bytes(),
    builder.PNG_SIGNATURE + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 1200, 600),
])
def test_wrong_preview_image_is_refused(data):
    with pytest.raises(ValueError, match='1200×630 PNG'):
        builder.check_link_preview(page(), data)


def test_committed_preview_matches_the_artwork():
    # The PNG is drawn from adventure.webp, journal.webp and Cinzel; a changed
    # illustration must come with a regenerated preview.
    pytest.importorskip('PIL')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/make_link_preview.py'), '--check'],
                            capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
