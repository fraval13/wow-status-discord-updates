"""CurseForge uploader with a fake HTTP opener; never contacts CurseForge."""
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('upload_curseforge', ROOT / 'scripts/upload_curseforge.py')
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)

INTERFACES = {'retail': 120105, 'vanilla': 11509, 'tbc': 20506, 'forever': 16001}
CHANGELOG = '# What\'s New\n\n## 0.18.0\n\n- New thing\n- Other thing\n\n## 0.17.0\n\n- Old thing\n'


def build(folder: Path) -> Path:
    for edition, interface in INTERFACES.items():
        with zipfile.ZipFile(folder / f'WoWStatus-{edition}.zip', 'w') as package:
            package.writestr('WoWStatus/WoWStatus.toc', f'## Interface: {interface}\n## Version: 0.18.0\nSafe.lua\n')
    return folder


class FakeServer:
    def __init__(self, versions, fail=()):
        self.versions, self.fail, self.uploads = versions, set(fail), []

    def __call__(self, request, timeout):
        assert request.headers['X-api-token'] == 'secret-token'
        if request.full_url.endswith('/api/game/versions'):
            return io.BytesIO(json.dumps(self.versions).encode('utf-8'))
        assert request.full_url == f'{cf.API}/api/projects/1234/upload-file'
        body = request.data
        metadata = json.loads(body.split(b'Content-Type: application/json\r\n\r\n', 1)[1].split(b'\r\n--', 1)[0])
        filename = body.split(b'filename="', 1)[1].split(b'"', 1)[0].decode('utf-8')
        if filename in self.fail:
            raise OSError('HTTP Error 400')
        self.uploads.append((filename, metadata))
        return io.BytesIO(json.dumps({'id': len(self.uploads)}).encode('utf-8'))


VERSIONS = [
    {'id': 1, 'name': '12.1.5', 'gameVersionTypeID': 517},
    {'id': 2, 'name': '1.15.8', 'gameVersionTypeID': 67408},
    {'id': 3, 'name': '1.15.7', 'gameVersionTypeID': 67408},
    {'id': 4, 'name': '2.5.6', 'gameVersionTypeID': 73246},
]


def test_interface_numbers_map_to_game_version_names():
    assert cf.interface_version(120105) == '12.1.5'
    assert cf.interface_version(11509) == '1.15.9'
    assert cf.interface_version(20506) == '2.5.6'
    assert cf.interface_version(16001) == '1.60.1'


def test_notes_are_the_release_section_only():
    assert cf.release_notes(CHANGELOG, '0.18.0') == '- New thing\n- Other thing'
    assert cf.release_notes(CHANGELOG, '9.9.9') == 'WoW Status 9.9.9.'


def test_uploads_each_listed_edition_and_skips_unlisted_ones(tmp_path, capsys):
    server = FakeServer(VERSIONS)
    assert cf.upload(build(tmp_path), '1234', 'secret-token', CHANGELOG, server) == 0
    uploaded = {name: meta for name, meta in server.uploads}
    assert set(uploaded) == {'WoWStatus-retail.zip', 'WoWStatus-vanilla.zip', 'WoWStatus-tbc.zip'}
    assert uploaded['WoWStatus-retail.zip']['gameVersions'] == [1]
    # 1.15.9 is not listed yet: the newest 1.15 patch is used, with a warning.
    assert uploaded['WoWStatus-vanilla.zip']['gameVersions'] == [2]
    meta = uploaded['WoWStatus-tbc.zip']
    assert meta['displayName'] == 'WoW Status 0.18.0 (TBC Anniversary)'
    assert meta['releaseType'] == 'release' and meta['changelogType'] == 'markdown'
    assert meta['changelog'] == '- New thing\n- Other thing'
    out = capsys.readouterr().out
    assert 'tagged 1.15.8' in out and 'no game version 1.60.1' in out
    assert 'secret-token' not in out


def test_a_failed_upload_fails_the_run_after_trying_the_rest(tmp_path):
    server = FakeServer(VERSIONS, fail={'WoWStatus-retail.zip'})
    assert cf.upload(build(tmp_path), '1234', 'secret-token', CHANGELOG, server) == 1
    assert len(server.uploads) == 2


def test_nothing_uploadable_fails(tmp_path):
    assert cf.upload(build(tmp_path), '1234', 'secret-token', CHANGELOG, FakeServer([])) == 1


def test_without_configuration_it_does_nothing(monkeypatch, capsys):
    monkeypatch.delenv('CURSEFORGE_API_TOKEN', raising=False)
    monkeypatch.delenv('CURSEFORGE_PROJECT_ID', raising=False)
    assert cf.main([]) == 0
    assert 'skipped' in capsys.readouterr().out


@pytest.mark.parametrize('project', ['abc', '12a'])
def test_project_id_must_be_numeric(monkeypatch, project):
    monkeypatch.setenv('CURSEFORGE_API_TOKEN', 'secret-token')
    monkeypatch.setenv('CURSEFORGE_PROJECT_ID', project)
    assert cf.main([]) == 1
