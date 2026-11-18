"""Public addon ZIPs ship only what the game loads, and only at the project version."""
import html
import importlib.util
import io
import json
import os
import re
import subprocess
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).parents[1]


def load_builder():
    spec = importlib.util.spec_from_file_location('homepage_build', ROOT / 'scripts/build_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def git(root, *args, data=None, env=None):
    # core.autocrlf=false: commit exactly the bytes a test writes, on Windows too.
    # core.hooksPath: a developer's global hooks must not run in the test repositories.
    return subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                           '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false',
                           '-c', 'core.hooksPath=no-hooks', *args],
                          input=data, check=True, capture_output=True,
                          env=None if env is None else {**os.environ, **env}).stdout


def zip_names(output, edition):
    with zipfile.ZipFile(output / f'downloads/WoWStatus-{edition}.zip') as package:
        return package.namelist()


def make_addon_repo(repo):
    """A small Git repository holding HEAD's website, addons and pyproject.toml.

    It is built from the committed tree, so uncommitted local edits never change the result.
    """
    archive = git(ROOT, 'archive', '--format=tar', 'HEAD', 'website', 'addon', 'pyproject.toml', 'CHANGELOG.md')
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if member.isfile():
                path = repo / member.name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tar.extractfile(member).read())
    git(repo, 'init', '-q')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'release')
    git(repo, 'repack', '-adq')  # clones link one pack instead of hundreds of loose objects


@pytest.fixture
def addon_repo(shared_once, tmp_path, clone_repository, reuse_homepage_packages):
    """A clean checkout of that repository. Builds read the addons from Git, so they
    stay out of the working tree."""
    reuse_homepage_packages(builder)
    return clone_repository(shared_once('addon-repo', make_addon_repo), tmp_path / 'repo', ['website'])


def commit(repo, files):
    # Write blobs straight into the index: the working tree may be case-insensitive (Windows,
    # macOS) and a developer's global .gitignore could hide files such as .DS_Store.
    for name, data in files.items():
        blob = git(repo, 'hash-object', '-w', '--stdin', data=data).decode().strip()
        git(repo, 'update-index', '--add', '--cacheinfo', f'100644,{blob},{name}')
    git(repo, 'commit', '-q', '-m', 'change')


def test_current_release_ships_every_committed_addon_file(tmp_path, reuse_homepage_packages):
    # Guard for the allowlist: a needed file committed to an addon folder must never be dropped.
    reuse_homepage_packages(builder)
    builder.build(ROOT, tmp_path, 'HEAD')
    for edition in builder.EDITIONS:
        folder = f'addon/{edition}/WoWStatus/'
        tracked = git(ROOT, 'ls-tree', '-r', '-z', '--name-only', 'HEAD', '--', folder).decode().split('\0')
        assert zip_names(tmp_path, edition) == sorted('WoWStatus/' + name.removeprefix(folder)
                                                      for name in tracked if name)


SOFTWARE_BLOCK = re.compile(r'  <script id="wow-status-software" type="application/ld\+json">\n(.*?)\n  </script>\n', re.S)


def software_graph(page):
    blocks = SOFTWARE_BLOCK.findall(page)
    assert len(blocks) == 1
    data = json.loads(blocks[0])
    assert data['@context'] == 'https://schema.org'
    return data['@graph']


def test_software_metadata_matches_the_actual_manifest_and_release_commit(addon_repo, tmp_path, monkeypatch):
    # A rebuild today must still describe the built release, not today's date.
    monkeypatch.setenv('GIT_COMMITTER_DATE', '2001-02-03T04:05:06+00:00')
    git(addon_repo, 'commit', '--amend', '--no-edit', '--date=1999-01-01T00:00:00+00:00')
    output = tmp_path / 'metadata'
    builder.build(addon_repo, output, 'HEAD')
    manifest = json.loads((output / 'downloads/release.json').read_text(encoding='utf-8'))
    page = (output / 'index.html').read_text(encoding='utf-8')
    graph = software_graph(page)
    assert len(graph) == len(manifest['editions']) == 4
    at = int(git(addon_repo, 'show', '-s', '--format=%ct', manifest['addon_revision']))
    expected = datetime.fromtimestamp(at, timezone.utc).isoformat().replace('+00:00', 'Z')
    assert expected == '2001-02-03T04:05:06Z'
    for application, (edition, release) in zip(graph, manifest['editions'].items()):
        assert application['@type'] == 'SoftwareApplication'
        assert application['softwareVersion'] == release['version']
        assert application['downloadUrl'] == 'https://wow.frankvalde.com/downloads/' + release['file']
        assert application['fileSize'] == f"{release['bytes']} B"
        assert (output / 'downloads' / release['file']).stat().st_size == release['bytes']
        assert application['datePublished'] == expected
        assert application['name'] == 'WoW Status — ' + builder.EDITION_NAMES[edition]
        assert application['applicationCategory'] == 'GameApplication'
        assert application['isAccessibleForFree'] is True and application['offers']['price'] == 0
        assert application['offers']['url'] == application['downloadUrl']
        assert application['publisher']['name'] == 'fraval13'
        assert 'review' not in application and 'aggregateRating' not in application
    assert 'FAQPage' not in page
    # Removing the generated, non-rendered data leaves the original built page byte for byte.
    monkeypatch.setattr(builder, 'write_software_metadata', lambda *args: None)
    baseline = tmp_path / 'baseline'
    builder.build(addon_repo, baseline, 'HEAD')
    assert SOFTWARE_BLOCK.sub('', page) == (baseline / 'index.html').read_text(encoding='utf-8')


def test_software_metadata_uses_changed_release_values_and_the_pages_own_url():
    page = '''<head><meta property="og:url" content="https://example.com/">
        <meta property="og:site_name" content="Example addon">
        <meta property="og:description" content="What the page says">
        <meta property="og:image" content="https://example.com/art.jpg"></head>'''
    release = {'version': '7.8.9', 'file': 'Changed.zip', 'bytes': 123456}
    graph = json.loads(builder.software_metadata(page, {'editions': {'retail': release}}, '2000-01-02'))['@graph']
    assert graph[0]['softwareVersion'] == '7.8.9'
    assert graph[0]['fileSize'] == '123456 B'
    assert graph[0]['downloadUrl'] == 'https://example.com/downloads/Changed.zip'
    assert graph[0]['description'] == 'What the page says'
    assert graph[0]['image'] == 'https://example.com/art.jpg'


def test_page_metadata_cannot_close_the_json_script(tmp_path):
    path = tmp_path / 'index.html'
    path.write_text('''<head><meta property="og:url" content="https://example.com/">
        <meta property="og:site_name" content="&lt;/script&gt;&lt;b&gt;Test&lt;/b&gt;">
        <meta property="og:description" content="Quote: &quot; and ampersand &amp;">
        <meta property="og:image" content="https://example.com/art.jpg"></head><body>Unchanged</body>''', encoding='utf-8')
    manifest = {'editions': {'vanilla': {'version': '1.0.0', 'file': 'Addon.zip', 'bytes': 1}}}
    builder.write_software_metadata(path, manifest, '2000-01-02')
    page = path.read_text(encoding='utf-8')
    assert page.count('</script>') == 1
    assert software_graph(page)[0]['name'].startswith('</script><b>Test</b>')
    assert page.endswith('<body>Unchanged</body>')


@pytest.mark.parametrize('page', ['<head></head></head>', '<head></head><script id="wow-status-software"></script>'])
def test_missing_or_duplicate_metadata_insertion_points_are_rejected(tmp_path, page):
    path = tmp_path / 'index.html'
    path.write_text(page, encoding='utf-8')
    with pytest.raises(ValueError, match='one </head> and no hand-written'):
        builder.write_software_metadata(path, {}, '')


def test_unlisted_committed_files_stay_out_of_every_zip(addon_repo, tmp_path):
    builder.build(addon_repo, tmp_path / 'clean', 'HEAD')
    stray = {}
    for edition in builder.EDITIONS:
        folder = f'addon/{edition}/WoWStatus/'
        stray |= {folder + '.DS_Store': b'\0\0\0\1Bud1', folder + 'WTF/WoWStatus.lua': b'WoWStatusDB = {}\n',
                  folder + 'Textures/.DS_Store': b'\0', folder + 'Textures/Logo.psd': b'8BPS',
                  folder + 'Textures/._Logo.tga': b'\0\5\26\7',
                  folder + 'Textures/Old/Logo.tga': b'\0', folder + 'Notes.lua': b'-- not in the TOC\n'}
    commit(addon_repo, stray)
    builder.build(addon_repo, tmp_path / 'stray', 'HEAD')
    for edition in builder.EDITIONS:
        names = zip_names(tmp_path / 'stray', edition)
        assert names == zip_names(tmp_path / 'clean', edition)
        assert 'WoWStatus/Textures/Logo.tga' in names
        assert 'WoWStatus/Textures/LevelUp.tga' in names


def test_pyproject_version_must_match_the_addon_tocs(addon_repo, tmp_path):
    pyproject = (addon_repo / 'pyproject.toml').read_text(encoding='utf-8')
    version = builder.project_version(addon_repo, 'HEAD')
    commit(addon_repo, {'pyproject.toml': pyproject.replace(f'version = "{version}"',
                                                            'version = "9.9.9"').encode()})
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match=r'\(vanilla .*, retail .*\) must all equal pyproject.toml version 9.9.9'):
        builder.build(addon_repo, output, 'HEAD')
    # Nothing is written, so an existing site is never left half-updated.
    assert not output.exists()


def test_a_toc_listed_file_must_be_committed(addon_repo, tmp_path):
    git(addon_repo, 'rm', '-q', '--sparse', 'addon/tbc/WoWStatus/Popups.lua')
    git(addon_repo, 'commit', '-q', '-m', 'drop')
    with pytest.raises(ValueError, match='tbc: Missing addon file: Popups.lua'):
        builder.build(addon_repo, tmp_path / 'site', 'HEAD')


@pytest.mark.parametrize('variant', ['bom', 'crlf'])
def test_a_toc_with_a_bom_or_crlf_fails_clearly(addon_repo, tmp_path, variant):
    toc = 'addon/retail/WoWStatus/WoWStatus.toc'
    data = git(addon_repo, 'show', f'HEAD:{toc}')
    data = b'\xef\xbb\xbf' + data if variant == 'bom' else data.replace(b'\n', b'\r\n')
    commit(addon_repo, {toc: data})
    with pytest.raises(ValueError, match='retail TOC must be saved without a BOM and with LF'):
        builder.build(addon_repo, tmp_path / 'site', 'HEAD')


def test_a_missing_toc_fails_clearly(addon_repo, tmp_path):
    git(addon_repo, 'rm', '-q', '--sparse', 'addon/forever/WoWStatus/WoWStatus.toc')
    git(addon_repo, 'commit', '-q', '-m', 'drop')
    with pytest.raises(ValueError, match='No forever TOC'):
        builder.build(addon_repo, tmp_path / 'site', 'HEAD')


def test_textures_that_differ_only_by_case_fail(addon_repo, tmp_path):
    commit(addon_repo, {'addon/tbc/WoWStatus/Textures/logo.TGA': b'\0'})
    with pytest.raises(ValueError, match='tbc: Addon files differ only by case: Textures/Logo.tga, Textures/logo.TGA'):
        builder.build(addon_repo, tmp_path / 'site', 'HEAD')


def test_a_revision_without_pyproject_fails_clearly(addon_repo, tmp_path):
    git(addon_repo, 'rm', '-q', '--sparse', 'pyproject.toml')
    git(addon_repo, 'commit', '-q', '-m', 'drop')
    with pytest.raises(ValueError, match='No pyproject.toml project version'):
        builder.build(addon_repo, tmp_path / 'site', 'HEAD')


def test_non_ascii_texture_names_ship(addon_repo, tmp_path):
    commit(addon_repo, {'addon/vanilla/WoWStatus/Textures/Æsir.tga': b'\0'})
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    assert 'WoWStatus/Textures/Æsir.tga' in zip_names(tmp_path / 'site', 'vanilla')


def test_package_files_reads_toc_paths_and_allowlisted_textures():
    toc = '## Version: 1.0\n# comment\r\nLibs\\Lib.lua\r\n\nCore.lua\n'
    tracked = {'WoWStatus.toc', 'Libs/Lib.lua', 'Core.lua', 'Extra.lua', 'Textures/Logo.tga',
               'Textures/Glow.TGA', 'Textures/Logo.tga.bak', 'Textures/Deep/Logo.tga', 'Textures/._Logo.tga',
               'WTF/WoWStatus.lua', '.DS_Store'}
    assert builder.package_files(toc, tracked) == ['Core.lua', 'Libs/Lib.lua', 'Textures/Glow.TGA',
                                                   'Textures/Logo.tga', 'WoWStatus.toc']


def test_key_bindings_ship_without_a_toc_line():
    # The game loads Bindings.xml by its name; other XML still needs a TOC line.
    tracked = {'WoWStatus.toc', 'Core.lua', 'Bindings.xml', 'Other.xml', 'Libs/Bindings.xml'}
    assert builder.package_files('Core.lua\n', tracked) == ['Bindings.xml', 'Core.lua', 'WoWStatus.toc']


def test_changelog_page_lists_every_release_in_order_with_stable_anchors(addon_repo, tmp_path):
    # #194: every ## <version> section, newest first, generated so it cannot drift.
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    sections = builder.parse_changelog(git(addon_repo, 'show', 'HEAD:CHANGELOG.md').decode('utf-8'))
    page = (tmp_path / 'site/changelog/index.html').read_text(encoding='utf-8')
    assert re.findall(r'<section class="release-entry" id="v([\d.]+)"', page) == [v for v, _ in sections]
    for version, notes in sections:
        entry = page.split(f'id="v{version}"', 1)[1].split('</section>', 1)[0]
        assert f'<a href="#v{version}">' in entry
        assert re.findall('<li>(.*?)</li>', entry) == [html.escape(note) for note in notes]
    assert f'{len(sections)} releases so far' in page
    assert f'href="#v{sections[0][0]}"' in page.split('<main', 1)[0]  # the utility bar's latest link
    assert page.count('<small>LATEST</small>') == 1
    assert f'id="v{sections[0][0]}"' in page.split('<small>LATEST</small>', 1)[0].rsplit('<section', 1)[1]
    homepage = (tmp_path / 'site/index.html').read_text(encoding='utf-8')
    assert 'href="/changelog/"' in homepage
    assert f'href="/changelog/#v{sections[0][0]}"' in homepage
    assert not re.search(r'__[A-Z_]+__', page + homepage)


def test_a_changelog_that_does_not_parse_fails_the_build(addon_repo, tmp_path):
    changelog = git(addon_repo, 'show', 'HEAD:CHANGELOG.md')
    commit(addon_repo, {'CHANGELOG.md': changelog + b'\n## Someday\n\n- A note\n'})
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match='heading must be a version'):
        builder.build(addon_repo, output, 'HEAD')
    assert not output.exists()


def test_a_missing_changelog_template_fails_the_build(addon_repo, tmp_path):
    (addon_repo / 'website/changelog/index.html').unlink()
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match='changelog/index.html is missing'):
        builder.build(addon_repo, output, 'HEAD')
    assert not output.exists()


def test_changelog_entries_escape_notes_and_mark_the_built_version():
    entries = builder.render_changelog([('2.0.0', ['Fish & <chips>']), ('1.0.0', ['First'])])
    assert '<li>Fish &amp; &lt;chips&gt;</li>' in entries
    assert entries.index('id="v2.0.0"') < entries.index('id="v1.0.0"')
    assert entries.count('LATEST') == 1 and entries.index('LATEST') < entries.index('id="v1.0.0"')


def test_notes_newer_than_the_built_version_stay_off_the_site(addon_repo, tmp_path):
    # Notes committed before the version bump (or an older --addon-ref) are not released yet.
    changelog = git(addon_repo, 'show', 'HEAD:CHANGELOG.md').decode('utf-8')
    version = builder.project_version(addon_repo, 'HEAD')
    commit(addon_repo, {'CHANGELOG.md': changelog.replace(
        f'## {version}\n', f'## 99.0.0\n\n- Not released yet\n\n## {version}\n', 1).encode()})
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    page = (tmp_path / 'site/changelog/index.html').read_text(encoding='utf-8')
    assert 'v99.0.0' not in page and 'Not released yet' not in page
    assert re.findall(r'id="v([\d.]+)"', page)[0] == version
    assert 'Not released yet' not in (tmp_path / 'site/index.html').read_text(encoding='utf-8')


def test_fill_replaces_placeholders_in_one_pass(tmp_path):
    page = tmp_path / 'page.html'
    page.write_text('__A__ __B__', encoding='utf-8')
    builder.fill(page, {'A': 'x', 'B': 'y', 'UNUSED': 'z'})
    assert page.read_text(encoding='utf-8') == 'x y'
    page.write_text('__A__ __MISSING__', encoding='utf-8')
    with pytest.raises(ValueError, match='Unresolved placeholder in page.html: MISSING'):
        builder.fill(page, {'A': 'x'})
    # An inserted value is never filled again, and one that looks like a placeholder fails clearly.
    page.write_text('__A__ __B__', encoding='utf-8')
    with pytest.raises(ValueError, match='may not contain placeholder text like __B__'):
        builder.fill(page, {'A': '__B__', 'B': 'y'})


def test_a_single_release_reads_in_the_singular(addon_repo, tmp_path):
    version = builder.project_version(addon_repo, 'HEAD')
    commit(addon_repo, {'CHANGELOG.md': f'# What\'s New\n\n## {version}\n\n- Only release\n'.encode()})
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    assert '1 release so far' in (tmp_path / 'site/changelog/index.html').read_text(encoding='utf-8')


def test_website_notes_in_page_folders_never_ship(addon_repo, tmp_path):
    (addon_repo / 'website/changelog/README.md').write_text('Template notes\n', encoding='utf-8')
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    assert (tmp_path / 'site/changelog/index.html').is_file()
    assert not (tmp_path / 'site/changelog/README.md').exists()


SITEMAP = '{http://www.sitemaps.org/schemas/sitemap/0.9}'


def test_robots_and_sitemap_list_the_pages_with_the_release_date(addon_repo, tmp_path):
    # Issue #192: both files are generated by every build, with lastmod from the built release.
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    when = git(addon_repo, 'show', '-s', '--format=%ct', 'HEAD').decode().strip()
    lastmod = datetime.fromtimestamp(int(when), timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    root = ElementTree.fromstring((tmp_path / 'site/sitemap.xml').read_bytes())
    assert root.tag == f'{SITEMAP}urlset'
    entries = [(url.findtext(f'{SITEMAP}loc'), url.findtext(f'{SITEMAP}lastmod')) for url in root]
    assert entries == [('https://wow.frankvalde.com/', lastmod),
                       ('https://wow.frankvalde.com/changelog/', lastmod),
                       ('https://wow.frankvalde.com/nn/', lastmod)]
    robots = (tmp_path / 'site/robots.txt').read_bytes()
    assert b'\r' not in robots
    lines = robots.decode('ascii').splitlines()
    assert lines[1:] == ['User-agent: *', 'Disallow: /groups/', 'Allow: /', '',
                         'Sitemap: https://wow.frankvalde.com/sitemap.xml']
    # Downloads stay crawlable: only the current ZIPs are served, there is no archive path.
    assert not any(line.startswith('Disallow: /downloads') for line in lines)


def test_lastmod_is_the_built_commits_time_in_utc(addon_repo, tmp_path):
    # A later release commit, made in another time zone: lastmod is its committer time in UTC.
    git(addon_repo, 'commit', '-q', '--allow-empty', '-m', 'release',
        env={'GIT_COMMITTER_DATE': '2030-01-02T05:04:05+02:00'})
    builder.build(addon_repo, tmp_path / 'later', 'HEAD')
    builder.build(addon_repo, tmp_path / 'earlier', 'HEAD~1')
    later = (tmp_path / 'later/sitemap.xml').read_text(encoding='utf-8')
    assert later.count('<lastmod>2030-01-02T03:04:05+00:00</lastmod>') == 3
    assert '2030-' not in (tmp_path / 'earlier/sitemap.xml').read_text(encoding='utf-8')


def test_render_sitemap_escapes_urls_and_robots_names_the_sitemap():
    sitemap = builder.render_sitemap(['https://example.com/?a=1&b=<2>'], '2026-01-02T03:04:05+00:00')
    assert '<loc>https://example.com/?a=1&amp;b=&lt;2&gt;</loc>' in sitemap
    assert ElementTree.fromstring(sitemap.encode('utf-8')) is not None
    assert builder.render_robots('https://example.com/sitemap.xml').endswith(
        '\nSitemap: https://example.com/sitemap.xml\n')


@pytest.mark.parametrize('file, other', [('index.html', '/changelog/'), ('changelog/index.html', '/')])
@pytest.mark.parametrize('canonical', [
    '',  # none
    '<link rel="canonical" href="https://example.com{own}">',  # another site
    '<link rel="canonical" href="https://wow.frankvalde.com/changes/">',  # not this page
    '<link rel="canonical" href="https://wow.frankvalde.com{other}">',  # another page of this site
    '<link rel="canonical" href="https://wow.frankvalde.com{own}?">',  # not exactly the URL
    '<link rel="canonical" href="https://wow.frankvalde.com{own}">'
    '<link rel="canonical" href="https://wow.frankvalde.com{own}">',  # repeated
])
def test_sitemap_pages_need_their_own_canonical_link(addon_repo, tmp_path, file, other, canonical):
    own = builder.site_path(file)
    page = addon_repo / 'website' / file
    text = page.read_text(encoding='utf-8')
    text = text.replace(re.search(r'<link rel="canonical"[^>]*>', text).group(0),
                        canonical.format(own=own, other=other), 1)
    page.write_text(text, encoding='utf-8')
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match=re.escape(
            f'{file}: a sitemap page needs exactly one <link rel="canonical" href="https://wow.frankvalde.com{own}">')):
        builder.build(addon_repo, output, 'HEAD')
    assert not output.exists()


def test_a_new_page_joins_the_sitemap(addon_repo, tmp_path):
    # Every shipped HTML page is listed, so a page added later cannot be left out.
    page = addon_repo / 'website/faq/index.html'
    page.parent.mkdir()
    page.write_text('<!doctype html><link rel="canonical" href="https://wow.frankvalde.com/faq/">',
                    encoding='utf-8')
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    root = ElementTree.fromstring((tmp_path / 'site/sitemap.xml').read_bytes())
    assert [url.findtext(f'{SITEMAP}loc') for url in root] == [
        'https://wow.frankvalde.com/', 'https://wow.frankvalde.com/changelog/', 'https://wow.frankvalde.com/faq/',
        'https://wow.frankvalde.com/nn/']
    page.write_text('<!doctype html>', encoding='utf-8')
    with pytest.raises(ValueError, match='faq/index.html: a sitemap page needs exactly one'):
        builder.build(addon_repo, tmp_path / 'other', 'HEAD')


def test_html_files_that_are_not_pages_stay_out_of_the_sitemap(addon_repo, tmp_path):
    # A search engine's verification file or an error page has no canonical link and is no page.
    (addon_repo / 'website/google1234abcd.html').write_text('google-site-verification: x\n', encoding='utf-8')
    (addon_repo / 'website/404.html').write_text('<!doctype html><p>Not found</p>', encoding='utf-8')
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    assert (tmp_path / 'site/404.html').is_file()
    root = ElementTree.fromstring((tmp_path / 'site/sitemap.xml').read_bytes())
    assert [url.findtext(f'{SITEMAP}loc') for url in root] == [
        'https://wow.frankvalde.com/', 'https://wow.frankvalde.com/changelog/',
        'https://wow.frankvalde.com/nn/']


def test_site_paths_of_built_files():
    for file, path in [('index.html', '/'), ('changelog/index.html', '/changelog/'), ('robots.txt', '/robots.txt'),
                       ('reindex.html', '/reindex.html'), ('faq/reindex.html', '/faq/reindex.html')]:
        assert builder.site_path(file) == path


@pytest.mark.parametrize('name', ['robots.txt', 'sitemap.xml'])
def test_a_hand_written_crawler_file_fails_the_build(addon_repo, tmp_path, name):
    (addon_repo / 'website' / name).write_text('stale\n', encoding='utf-8')
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match=f'website/{re.escape(name)} must not exist'):
        builder.build(addon_repo, output, 'HEAD')
    assert not output.exists()


def nynorsk_build(repo, output):
    builder.build(repo, output, 'HEAD')
    return ((output / 'index.html').read_text(encoding='utf-8'),
            (output / 'nn/index.html').read_text(encoding='utf-8'))


def test_the_nynorsk_page_is_the_same_page_in_the_other_language(addon_repo, tmp_path):
    # #193: one template, one copy deck, so the two pages cannot drift apart.
    english, nynorsk = nynorsk_build(addon_repo, tmp_path / 'site')
    assert '<html lang="nn">' in nynorsk and '<html lang="en">' in english
    assert '<link rel="canonical" href="https://wow.frankvalde.com/nn/">' in nynorsk
    assert '<meta property="og:url" content="https://wow.frankvalde.com/nn/">' in nynorsk
    assert '<meta property="og:locale" content="nn_NO">' in nynorsk
    # The same hreflang set on both pages, pointing at each other.
    for page in (english, nynorsk):
        assert '<link rel="alternate" hreflang="en" href="https://wow.frankvalde.com/">' in page
        assert '<link rel="alternate" hreflang="nn" href="https://wow.frankvalde.com/nn/">' in page
        assert '<link rel="alternate" hreflang="x-default" href="https://wow.frankvalde.com/">' in page
    # Each page offers the other one, in the other one's language.
    assert 'href="/nn/" hreflang="nn" lang="nn">Les denne sida på nynorsk' in english
    assert 'href="/" hreflang="en" lang="en">Read this page in English' in nynorsk
    # Translated, not copied: the English copy is gone from the Nynorsk page.
    for sentence in ('Keep your friends in the story.', 'Your adventure awaits',
                     'A few things worth knowing.', 'Three steps to set out together.'):
        assert sentence in english
        assert sentence not in nynorsk
    assert 'Hald vener med i soga.' in nynorsk
    assert 'Eventyret ventar' in nynorsk
    assert not re.search(r'__[A-Z_]+__', nynorsk)
    # The structure is the same page, not a second one written by hand.
    assert nynorsk.count('<section') == english.count('<section')
    assert nynorsk.count('class="feature"') == english.count('class="feature"')


def test_both_pages_show_the_same_generated_version_and_sizes(addon_repo, tmp_path):
    english, nynorsk = nynorsk_build(addon_repo, tmp_path / 'site')
    version = builder.project_version(addon_repo, 'HEAD')
    assert f'VERSION {version}' in english
    assert f'VERSJON {version}' in nynorsk
    sizes = re.findall(r'ZIP · (\d+ KB)', english)
    assert len(sizes) == 4
    assert re.findall(r'ZIP · (\d+ KB)', nynorsk) == sizes
    # The release notes are the same notes, generated once.
    notes = re.findall(r'<li>(.*?)</li>', english.split('release-panel', 1)[1])
    assert notes and re.findall(r'<li>(.*?)</li>', nynorsk.split('release-panel', 1)[1]) == notes


def test_the_nynorsk_page_gets_nynorsk_captions_and_samples(addon_repo, tmp_path):
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    page = (tmp_path / 'site/nn/index.html').read_text(encoding='utf-8')
    assert 'src="/nn/flavour.js"' in page and 'src="/nn/app.js"' in page
    flavour = (tmp_path / 'site/nn/flavour.js').read_text(encoding='utf-8')
    english = (tmp_path / 'site/flavour.js').read_text(encoding='utf-8')
    # Line for line the same bank, so it is the same joke in either language.
    assert 'Same spelar. Større tal.' in flavour
    assert 'Same player. Larger numbers.' in english
    assert flavour.count('": [') == english.count('": [')
    samples = (tmp_path / 'site/nn/app.js').read_text(encoding='utf-8')
    assert "heading: 'NYTT NIVÅ!'" in samples
    assert "heading: 'LEVEL UP!'" not in samples


def test_the_copy_deck_itself_never_ships(addon_repo, tmp_path):
    builder.build(addon_repo, tmp_path / 'site', 'HEAD')
    assert not (tmp_path / 'site/nn.json').exists()
    assert not (tmp_path / 'site/nn/nn.json').exists()


def test_a_string_without_a_translation_fails_the_build(addon_repo, tmp_path):
    page = addon_repo / 'website/index.html'
    page.write_text(page.read_text(encoding='utf-8').replace(
        '<h3>A shared chronicle.</h3>', '<h3>A brand new heading.</h3>'), encoding='utf-8')
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match='no Nynorsk for'):
        builder.build(addon_repo, output, 'HEAD')
    assert not output.exists()


def test_a_translation_the_page_no_longer_has_fails_the_build(addon_repo, tmp_path):
    deck = addon_repo / 'website/nn.json'
    deck.write_text(deck.read_text(encoding='utf-8').replace(
        '  "Footer": "Botntekst"', '  "Footer": "Botntekst",\n  "Gone from the page": "Borte"', 1),
        encoding='utf-8')
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match='no longer has'):
        builder.build(addon_repo, output, 'HEAD')
    assert not output.exists()


def test_preview_captions_that_drifted_from_the_addon_fail_the_build(addon_repo, tmp_path):
    # Pairing by position would otherwise put the wrong Nynorsk line under the picture.
    flavour = addon_repo / 'website/flavour.js'
    flavour.write_text(flavour.read_text(encoding='utf-8').replace(
        '"Same player. Larger numbers.",', '"Something nobody wrote in the addon.",', 1),
        encoding='utf-8')
    output = tmp_path / 'site'
    with pytest.raises(ValueError, match='cannot be paired'):
        builder.build(addon_repo, output, 'HEAD')
    assert not output.exists()
