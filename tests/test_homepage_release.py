"""Public downloads must match the release before their symlink can be activated."""
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).parents[1]


def public_verifier():
    spec = importlib.util.spec_from_file_location('homepage_verify', ROOT/'scripts/verify_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify


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


def test_published_site_verification_checks_every_download(built_site):
    manifest=json.loads((built_site/'downloads/release.json').read_text(encoding='utf-8'))
    def fetch(url):
        path=urlparse(url).path.lstrip('/') or 'index.html'
        return (built_site/path).read_bytes()
    assert public_verifier()('https://example.com',manifest['addon_revision'],fetch)==manifest


@pytest.mark.parametrize('fault', ['stale_revision','missing_tbc_link','corrupt_tbc_zip','stale_version'])
def test_published_site_verification_rejects_incomplete_updates(built_site,fault):
    manifest=json.loads((built_site/'downloads/release.json').read_text(encoding='utf-8'))
    def fetch(url):
        path=urlparse(url).path.lstrip('/') or 'index.html'
        data=(built_site/path).read_bytes()
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
        public_verifier()('https://example.com',manifest['addon_revision'],fetch)
