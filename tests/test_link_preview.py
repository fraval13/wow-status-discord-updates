"""A pasted homepage link shows a large image card in Discord (issue #190)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WEBSITE = ROOT / 'website'
PREVIEW = WEBSITE / 'assets/link-preview.jpg'


def load_builder():
    spec = importlib.util.spec_from_file_location('homepage_build_preview', ROOT / 'scripts/build_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def page():
    return (WEBSITE / 'index.html').read_text(encoding='utf-8')


def test_homepage_has_complete_open_graph_and_twitter_tags():
    parser = builder.MetaTags()
    parser.feed(page())
    found = dict(parser.tags)
    assert len(found) == len(parser.tags), 'a meta tag is repeated'
    assert found['og:type'] == 'website'
    assert found['og:site_name'] == 'WoW Status'
    assert found['og:url'] == 'https://wow.frankvalde.com/'
    assert found['og:image'] == found['twitter:image'] == 'https://wow.frankvalde.com/assets/link-preview.jpg'
    assert (found['og:image:type'], found['og:image:width'], found['og:image:height']) == ('image/jpeg', '1200', '630')
    assert found['twitter:card'] == 'summary_large_image'
    assert found['twitter:title'] == found['og:title']
    assert found['twitter:description'] == found['og:description']
    assert found['og:image:alt'] and found['twitter:image:alt'] == found['og:image:alt']
    builder.check_link_preview(page(), builder.site_file(WEBSITE))


def test_committed_preview_is_a_complete_1200_by_630_jpeg():
    data = PREVIEW.read_bytes()
    assert builder.jpeg_size(data) == (1200, 630)
    # Small enough for chat clients that skip large previews.
    assert len(data) < 400 * 1024


def served(data):
    return lambda path: data if path == builder.LINK_PREVIEW else b''


@pytest.mark.parametrize('change', [
    lambda html: html.replace('summary_large_image', 'summary'),
    lambda html: html.replace('<meta property="og:image:width" content="1200">', ''),
    lambda html: html.replace('<meta name="twitter:image:alt"', '<meta name="twitter:image:alt" content=""><x'),
    lambda html: html.replace('link-preview.jpg', 'adventure.webp'),
    lambda html: html.replace('name="twitter:image" content="https://wow.frankvalde.com/assets/link-preview.jpg"',
                              'name="twitter:image" content="https://wow.frankvalde.com/assets/other.jpg"'),
    lambda html: html.replace('https://wow.frankvalde.com/assets/link-preview.jpg',
                              'http://wow.frankvalde.com/assets/link-preview.jpg'),
    # The image must come from the page's own site, where the build put it.
    lambda html: html.replace('https://wow.frankvalde.com/assets/link-preview.jpg',
                              'https://example.org/assets/link-preview.jpg'),
    # A second, conflicting tag: scrapers disagree on which one wins.
    lambda html: html.replace('</head>', '<meta name="twitter:card" content="summary"></head>'),
    lambda html: html.replace('</head>', '<meta property="og:image" content="https://wow.frankvalde.com/a.webp">'
                                         '</head>'),
])
def test_incomplete_preview_tags_are_refused(change):
    html = change(page())
    assert html != page()
    with pytest.raises(ValueError, match='link preview tags'):
        builder.check_link_preview(html, served(PREVIEW.read_bytes()))


@pytest.mark.parametrize('data', [
    b'',
    (WEBSITE / 'assets/adventure.webp').read_bytes(),
    (WEBSITE / 'assets/favicon.png').read_bytes(),
    PREVIEW.read_bytes()[:4096],  # cut short: no end-of-image marker
    PREVIEW.read_bytes()[:-2],
])
def test_wrong_preview_image_is_refused(data):
    with pytest.raises(ValueError, match='1200×630 JPEG'):
        builder.check_link_preview(page(), served(data))


def test_build_fails_fast_without_the_preview(tmp_path):
    root = tmp_path / 'root'
    (root / 'website').mkdir(parents=True)
    (root / 'website/index.html').write_text(page(), encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    # Same isolation as the other homepage tests: no developer hooks or line-ending rewrites.
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=T', '-c', 'user.email=t@example.com',
                    '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false', '-c', 'core.hooksPath=no-hooks',
                    'commit', '-q', '--allow-empty', '-m', 'x'], check=True)
    with pytest.raises(ValueError, match='1200×630 JPEG'):
        builder.build(root, tmp_path / 'site', 'HEAD')
    assert not (tmp_path / 'site').exists()


def test_committed_preview_matches_the_artwork():
    # The JPEG is drawn from adventure.webp, journal.webp and Cinzel; a changed
    # illustration or preview text must come with a regenerated image.
    pytest.importorskip('PIL')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/make_link_preview.py'), '--check'],
                            capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
