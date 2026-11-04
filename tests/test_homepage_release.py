"""Public downloads must match the release before their symlink can be activated."""
import functools
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).parents[1]


@functools.cache
def verifier_module():
    spec = importlib.util.spec_from_file_location('homepage_verify', ROOT/'scripts/verify_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public_verifier():
    return verifier_module().verify


def receiver():
    if sys.platform == 'win32':
        pytest.skip('The root deployment receiver is Linux-only')
    spec = importlib.util.spec_from_file_location('homepage_receiver', ROOT / 'deploy/install_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def built_site(tmp_path_factory):
    target=tmp_path_factory.mktemp('homepage')
    subprocess.run([sys.executable,str(ROOT/'scripts/build_homepage.py'),'--output',str(target)],check=True,cwd=ROOT)
    return target


@pytest.fixture
def staged(built_site,tmp_path):
    public=tmp_path/'.deploy/HOMEPAGE'
    shutil.copytree(built_site,public)
    for edition in ('vanilla','forever','tbc','retail'):
        with zipfile.ZipFile(public/f'downloads/WoWStatus-{edition}.zip') as archive:
            toc=tmp_path/f'addon/{edition}/WoWStatus/WoWStatus.toc'
            toc.parent.mkdir(parents=True)
            toc.write_bytes(archive.read('WoWStatus/WoWStatus.toc'))
    return tmp_path,json.loads((public/'downloads/release.json').read_text(encoding='utf-8'))['addon_revision']


def test_release_rejects_wrong_revision_or_corrupt_download_before_activation(staged):
    stage,revision=staged
    module=receiver()
    with pytest.raises(ValueError,match='revision'):
        module.prepare_homepage(stage,'0'*40)
    package=stage/'.deploy/HOMEPAGE/downloads/WoWStatus-vanilla.zip'
    package.write_bytes(package.read_bytes()+b'corrupt')
    with pytest.raises(ValueError,match='checksum'):
        module.prepare_homepage(stage,revision)
    assert not (stage/'public-homepage').exists()


def test_public_release_version_must_match_addon_before_switch(staged):
    stage,revision=staged
    module=receiver()
    toc=stage/'addon/forever/WoWStatus/WoWStatus.toc'
    toc.write_bytes(toc.read_bytes()+b'\n## Unexpected: mismatch\n')
    with pytest.raises(ValueError,match='ZIP'):
        module.prepare_homepage(stage,revision)
    assert not (stage/'public-homepage').exists()


def test_valid_release_switches_all_public_downloads_together(staged,monkeypatch,tmp_path):
    stage,revision=staged
    module=receiver()
    site=tmp_path/'site'
    site.mkdir()
    old=tmp_path/'old'
    old.mkdir()
    (site/'current').symlink_to(old,target_is_directory=True)
    monkeypatch.setattr(module,'HOMEPAGE',site)
    public=module.prepare_homepage(stage,revision)
    assert (site/'current').resolve()==old
    module.switch_homepage(public)
    assert (site/'current').resolve()==public
    manifest=json.loads((site/'current/downloads/release.json').read_text(encoding='utf-8'))
    for edition in ('vanilla','forever','tbc','retail'):
        assert (site/f'current/downloads/WoWStatus-{edition}.zip').is_file()
        assert f'VERSION {manifest["editions"][edition]["version"]}' in (site/'current/index.html').read_text(encoding='utf-8')
    # Receiver rollback returns the complete previous site, including downloads.
    module.switch_homepage(old)
    assert (site/'current').resolve()==old


def site_fetch(site, change=lambda path, data: data):
    """A fetcher serving the built site, with change(path, data) applied to each response."""
    def fetch(url):
        path=urlparse(url).path.lstrip('/') or 'index.html'
        return change(path, (site/path).read_bytes())
    return fetch


def test_published_site_verification_checks_every_download(built_site):
    manifest=local_manifest(built_site)
    fetch=site_fetch(built_site)
    assert public_verifier()('https://example.com',manifest['addon_revision'],fetch,
                             expected=manifest)==manifest


@pytest.mark.parametrize('fault', ['stale_revision','missing_tbc_link','corrupt_tbc_zip','stale_version'])
def test_published_site_verification_rejects_incomplete_updates(built_site,fault):
    manifest=local_manifest(built_site)
    def change(path,data):
        if path=='downloads/release.json' and fault=='stale_revision':
            return json.dumps(dict(manifest,addon_revision='0'*40)).encode()
        if path=='index.html' and fault=='missing_tbc_link':
            return data.replace(b'/downloads/WoWStatus-tbc.zip',b'/missing.zip')
        if path=='downloads/WoWStatus-tbc.zip' and fault=='corrupt_tbc_zip':
            return data+b'corrupt'
        if path=='index.html' and fault=='stale_version':
            return data.replace(('VERSION '+manifest['editions']['tbc']['version']).encode(),b'VERSION 0.0.0')
        return data
    with pytest.raises(ValueError):
        public_verifier()('https://example.com',manifest['addon_revision'],site_fetch(built_site,change),
                          expected=manifest)


def local_manifest(site):
    return json.loads((site/'downloads/release.json').read_text(encoding='utf-8'))


def rewrite_zip(data, drop=(), replace=None, add=None):
    """Return a copy of a ZIP without the drop entries, with replace/add entries written."""
    replace, add = replace or {}, add or {}
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, \
            zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            if item.filename not in drop:
                target.writestr(item, replace.get(item.filename, source.read(item)))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')  # zipfile warns about the duplicate-entry case
            for name, content in add.items():
                target.writestr(name, content)
    return output.getvalue()


def tampered_site(built_site, zip_data):
    """A site serving zip_data as the vanilla ZIP, with its served manifest regenerated to match."""
    served = local_manifest(built_site)
    vanilla = dict(served['editions']['vanilla'], bytes=len(zip_data),
                   sha256=hashlib.sha256(zip_data).hexdigest())
    served = dict(served, editions=dict(served['editions'], vanilla=vanilla))
    replaced = {'downloads/release.json': json.dumps(served).encode(),
                'downloads/WoWStatus-vanilla.zip': zip_data}
    return served, site_fetch(built_site, lambda path, data: replaced.get(path, data))


ISSUE_TAMPERING = dict(drop={'WoWStatus/Groups.lua'},
                       replace={'WoWStatus/WoWStatus.lua': b'print("not the real addon")'},
                       add={'../../outside.lua': b'-- escapes the AddOns folder',
                            'WoWStatus/WTF/SavedVariables.lua': b'WoWStatusDB = {}'})


def test_tampered_zip_with_regenerated_manifest_fails(built_site):
    # Issue #16: this passed when the verifier trusted the served manifest.
    original = (built_site/'downloads/WoWStatus-vanilla.zip').read_bytes()
    served, fetch = tampered_site(built_site, rewrite_zip(original, **ISSUE_TAMPERING))
    expected = local_manifest(built_site)
    with pytest.raises(ValueError, match='differs from the locally built'):
        public_verifier()('https://example.com', expected['addon_revision'], fetch,
                          expected=expected)
    # Even a local manifest that somehow matched it can't make that ZIP pass.
    with pytest.raises(ValueError, match='vanilla ZIP'):
        public_verifier()('https://example.com', expected['addon_revision'], fetch,
                          expected=served)


def test_zip_that_differs_from_the_local_build_fails(built_site):
    # The served manifest is honest here, but the ZIP is not the one this build produced.
    expected = local_manifest(built_site)
    def change(path, data):
        if path=='downloads/WoWStatus-retail.zip':
            return rewrite_zip(data, replace={'WoWStatus/WoWStatus.lua': b'-- swapped'})
        return data
    fetch = site_fetch(built_site, change)
    with pytest.raises(ValueError, match='retail ZIP does not match the locally built'):
        public_verifier()('https://example.com', expected['addon_revision'], fetch,
                          expected=expected)


def test_local_manifest_must_be_this_revisions_complete_build(built_site):
    expected = local_manifest(built_site)
    revision = expected['addon_revision']
    fetch = site_fetch(built_site)
    without_hash = {k: v for k, v in expected['editions']['tbc'].items() if k != 'sha256'}
    for local in (dict(expected, addon_revision='0'*40),
                  dict(expected, editions={k: v for k, v in expected['editions'].items()
                                           if k != 'tbc'}),
                  dict(expected, editions=dict(expected['editions'], tbc=without_hash)),
                  dict(expected, editions=None),
                  ['not', 'a', 'manifest']):
        with pytest.raises(ValueError, match='local release.json'):
            public_verifier()('https://example.com', revision, fetch, expected=local)


@pytest.mark.parametrize('tamper', [
    dict(drop={'WoWStatus/Groups.lua'}),
    dict(add={'../../outside.lua': b''}),
    dict(add={'WoWStatus/../outside.lua': b''}),
    dict(add={'/WoWStatus/absolute.lua': b''}),
    dict(add={'WoWStatus/WTF/SavedVariables.lua': b''}),
    dict(add={'WoWStatus/Notes.txt': b''}),
    dict(add={'WoWStatus/Textures/': b''}),
    dict(add={'WoWStatus/WoWStatus.lua': b'duplicate'}),
    dict(drop={'WoWStatus/WoWStatus.toc'}),
], ids=['missing_listed_file', 'traversal', 'nested_traversal', 'absolute',
        'saved_variables', 'unlisted_file', 'directory_entry', 'duplicate', 'no_toc'])
def test_zip_entries_must_be_exactly_the_toc_files(built_site, tamper):
    module = verifier_module()
    original = (built_site/'downloads/WoWStatus-vanilla.zip').read_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as package:
        module.check_entries('vanilla', package)
    data = rewrite_zip(original, **tamper)
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        with pytest.raises(ValueError, match='vanilla ZIP'):
            module.check_entries('vanilla', package)


def test_zip_entry_with_a_stored_backslash_fails_on_every_platform(built_site):
    # On Windows zipfile reads a stored backslash as '/', so write the name with '|' and
    # patch the bytes: the check must see the stored name, whatever platform it runs on.
    original = (built_site/'downloads/WoWStatus-vanilla.zip').read_bytes()
    data = rewrite_zip(original, add={'WoWStatus|Extra.lua': b''})
    data = data.replace(b'WoWStatus|Extra.lua', b'WoWStatus\\Extra.lua')
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        assert any('\\' in item.orig_filename for item in package.infolist())
        with pytest.raises(ValueError, match='unexpected entry:'):
            verifier_module().check_entries('vanilla', package)


def test_every_built_zip_passes_the_entry_check(built_site):
    module = verifier_module()
    for edition in module.EDITIONS:
        with zipfile.ZipFile(built_site/f'downloads/WoWStatus-{edition}.zip') as package:
            module.check_entries(edition, package)


def test_deploy_passes_the_local_manifest_to_the_verifier():
    workflow = (ROOT/'.github/workflows/checks.yml').read_text(encoding='utf-8')
    # The deploy job is the last job; its own steps must build dist/homepage, then verify with it.
    deploy = workflow[workflow.index('\n  deploy:\n'):]
    build = deploy.index('run: python scripts/build_homepage.py --addon-ref HEAD\n')
    verify = deploy.index('scripts/verify_homepage.py')
    assert build < verify
    assert '--manifest dist/homepage/downloads/release.json' in deploy[verify:].split('\n      - ')[0]


def test_command_line_requires_a_manifest_of_the_same_revision(built_site, tmp_path):
    script = [sys.executable, str(ROOT/'scripts/verify_homepage.py'), '--url', 'https://example.com',
              '--revision', '1'*40]
    missing = subprocess.run(script, capture_output=True, text=True, encoding='utf-8')
    assert missing.returncode == 2 and '--manifest' in missing.stderr
    other = subprocess.run([*script, '--manifest', str(built_site/'downloads/release.json')],
                           capture_output=True, text=True, encoding='utf-8')
    assert other.returncode == 2 and 'not a complete build of revision' in other.stderr
    short = subprocess.run([*script[:-1], 'abc123', '--manifest', str(built_site/'downloads/release.json')],
                           capture_output=True, text=True, encoding='utf-8')
    assert short.returncode == 2 and 'complete Git commit revision' in short.stderr
