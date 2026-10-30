"""Public downloads must match the release before their symlink can be activated."""
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


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
    for edition in ('vanilla','forever','tbc'):
        with zipfile.ZipFile(public/f'downloads/WoWStatus-{edition}.zip') as archive:
            toc=tmp_path/f'addon/{edition}/WoWStatus/WoWStatus.toc'
            toc.parent.mkdir(parents=True)
            toc.write_bytes(archive.read('WoWStatus/WoWStatus.toc'))
    return tmp_path,json.loads((public/'downloads/release.json').read_text())['addon_revision']


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
    manifest=json.loads((site/'current/downloads/release.json').read_text())
    for edition in ('vanilla','forever','tbc'):
        assert (site/f'current/downloads/WoWStatus-{edition}.zip').is_file()
        assert f'VERSION {manifest["editions"][edition]["version"]}' in (site/'current/index.html').read_text()
    # Receiver rollback returns the complete previous site, including downloads.
    module.switch_homepage(old)
    assert (site/'current').resolve()==old
