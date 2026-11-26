"""Wago release API contracts and workflow gates; no real uploads or tokens."""
import importlib.util
import io
import json
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('upload_wago', ROOT / 'scripts/upload_wago.py')
wago = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wago)
PROJECT = 'mNww12No'
TOKEN = 'test-private-token'
INTERFACES = {'retail': 120105, 'vanilla': 11509, 'tbc': 20506, 'forever': 16001}
CATALOGUE = {'patches': {'retail': ['12.1.5'], 'classic': ['1.15.9'], 'bc': ['2.5.6'], 'forever': ['1.60.1']}}
NOTES = '## 0.18.0\n\n- A player-facing change\n\n## 0.17.0\n\n- An older change\n'


def build(folder, *, different=None, project=PROJECT):
    for edition, interface in INTERFACES.items():
        version = '0.17.0' if edition == different else '0.18.0'
        with zipfile.ZipFile(folder / f'WoWStatus-{edition}.zip', 'w') as package:
            package.writestr('WoWStatus/WoWStatus.toc',
                             f'## Interface: {interface}\n## Version: {version}\n## X-Wago-ID: {project}\nSafe.lua\n')
            package.writestr('WoWStatus/Safe.lua', '-- A harmless fixture\n')
    return folder


class Server:
    def __init__(self, *, catalogue=None, fail=None, response=b''):
        self.catalogue = CATALOGUE if catalogue is None else catalogue
        self.fail, self.response, self.uploads, self.requests = fail, response, [], []

    def __call__(self, request, timeout):
        assert timeout == 180
        self.requests.append(request)
        if request.get_method() == 'GET':
            assert request.full_url == f'{wago.API}/data/game'
            assert not request.has_header('Authorization')
            assert request.headers['User-agent'] == 'wow-status-release'
            return io.BytesIO(json.dumps(self.catalogue).encode('utf-8'))
        assert request.full_url == f'{wago.API}/projects/{PROJECT}/version'
        assert request.headers['Authorization'] == f'Bearer {TOKEN}'
        assert request.headers['Accept'] == 'application/json'
        body = request.data
        meta = json.loads(body.split(b'Content-Type: application/json\r\n\r\n')[1].split(b'\r\n--')[0])
        filename = body.split(b'filename="')[1].split(b'"')[0].decode('utf-8')
        if self.fail == filename:
            raise HTTPError(request.full_url, 422, 'No', {}, io.BytesIO(TOKEN.encode('utf-8')))
        assert b'WoWStatus/Safe.lua' in body  # Actual ZIP bytes, not a path or source tree.
        self.uploads.append((filename, meta))
        return io.BytesIO(self.response)


def test_four_separate_uploads_have_correct_flavours_and_release_notes(tmp_path, capsys):
    server = Server()
    assert wago.upload(build(tmp_path), PROJECT, TOKEN, NOTES, opener=server) == 0
    assert len(server.uploads) == 4
    for filename, meta in server.uploads:
        edition = filename.removeprefix('WoWStatus-').removesuffix('.zip')
        flavour, label = wago.EDITIONS[edition]
        assert meta == {
            'label': f'0.18.0 ({label})', 'stability': 'stable',
            'changelog': '- A player-facing change',
            f'supported_{flavour}_patches': [wago.interface_version(INTERFACES[edition])],
        }
    assert TOKEN not in capsys.readouterr().out


def test_a_single_edition_retry_does_not_repeat_successful_files(tmp_path):
    server = Server(response=b'{"id":123}')
    assert wago.upload(build(tmp_path), PROJECT, TOKEN, NOTES, editions=['forever'], opener=server) == 0
    assert [name for name, _ in server.uploads] == ['WoWStatus-forever.zip']


def test_dry_run_needs_no_token_and_never_posts(tmp_path, capsys):
    server = Server()
    assert wago.upload(build(tmp_path), PROJECT, '', NOTES, dry_run=True, opener=server) == 0
    assert len(server.requests) == 1 and not server.uploads
    assert capsys.readouterr().out.count('DRY RUN') == 4


@pytest.mark.parametrize('catalogue', [[], {}, {'patches': []}, {'patches': {'retail': ['12.1.0']}}])
def test_missing_or_wrong_edition_patches_fail_before_any_upload(tmp_path, catalogue):
    server = Server(catalogue=catalogue)
    assert wago.upload(build(tmp_path), PROJECT, TOKEN, NOTES, opener=server) == 1
    assert len(server.requests) == 1


def test_mixed_addon_versions_cannot_partially_publish(tmp_path):
    server = Server()
    assert wago.upload(build(tmp_path, different='forever'), PROJECT, TOKEN, NOTES, opener=server) == 1
    assert not server.uploads


def test_missing_release_notes_cannot_publish(tmp_path):
    server = Server()
    assert wago.upload(build(tmp_path), PROJECT, TOKEN, '## Unreleased\n- Not released\n', opener=server) == 1
    assert not server.uploads


def test_another_project_id_in_a_toc_cannot_publish(tmp_path):
    server = Server()
    assert wago.upload(build(tmp_path, project='other123'), PROJECT, TOKEN, NOTES, opener=server) == 1
    assert not server.uploads


def test_missing_last_zip_does_not_publish_the_first_three(tmp_path):
    server = Server()
    build(tmp_path)
    (tmp_path / 'WoWStatus-forever.zip').unlink()
    assert wago.upload(tmp_path, PROJECT, TOKEN, NOTES, opener=server) == 1
    assert not server.uploads


def test_api_failure_is_reported_without_retrying_or_exposing_its_body(tmp_path, capsys):
    server = Server(fail='WoWStatus-vanilla.zip')
    assert wago.upload(build(tmp_path), PROJECT, TOKEN, NOTES, opener=server) == 1
    assert len(server.requests) == 5  # One catalogue request and exactly four POST attempts.
    assert len(server.uploads) == 3
    out = capsys.readouterr().out
    assert 'Classic Era upload failed' in out and 'HTTP 422' in out and TOKEN not in out


@pytest.mark.parametrize('code', [302, 401, 403, 404, 413, 422, 500])
def test_http_errors_do_not_log_the_token_or_reflected_server_body(code):
    def opener(request, timeout):
        raise HTTPError(request.full_url, code, 'No', {}, io.BytesIO(TOKEN.encode('utf-8')))
    with pytest.raises(wago.UploadError) as error:
        wago.call(wago.Request(f'{wago.API}/projects/{PROJECT}/version', data=b'zip'), opener, TOKEN)
    assert TOKEN not in str(error.value) and f'HTTP {code}' in str(error.value)


@pytest.mark.parametrize('error', [URLError(TOKEN), TimeoutError(TOKEN), ValueError(TOKEN)])
def test_transport_and_decode_errors_do_not_expose_secrets(error):
    def opener(request, timeout):
        raise error
    with pytest.raises(wago.UploadError) as caught:
        wago.call(wago.Request(f'{wago.API}/data/game'), opener, TOKEN)
    assert TOKEN not in str(caught.value)


def test_configuration_is_required_before_a_real_upload(monkeypatch, capsys):
    monkeypatch.setenv('WAGO_PROJECT_ID', PROJECT)
    monkeypatch.delenv('WAGO_API_TOKEN', raising=False)
    assert wago.main([]) == 1
    assert 'WAGO_API_TOKEN' in capsys.readouterr().out


@pytest.mark.parametrize('project', ['', '../path', '1234567', 'mNww12No/other'])
def test_project_id_cannot_inject_an_api_path(monkeypatch, project):
    monkeypatch.setenv('WAGO_PROJECT_ID', project)
    assert wago.main(['--dry-run']) == 1


def test_all_four_distributions_identify_the_wago_project():
    for edition in INTERFACES:
        path = ROOT / f'addon/{edition}/WoWStatus/WoWStatus.toc'
        assert path.read_text(encoding='utf-8').count(f'## X-Wago-ID: {PROJECT}\n') == 1


def test_workflow_uploads_only_the_verified_revision_and_keeps_tokens_out_of_checkout():
    text = (ROOT / '.github/workflows/checks.yml').read_text(encoding='utf-8')
    job = text.split('\n  wago:\n')[1]
    assert 'needs: [deploy-gate, deploy]' in job
    assert "if: needs.deploy.result == 'success' && vars.WAGO_PROJECT_ID != ''" in job
    assert 'ref: ${{ needs.deploy-gate.outputs.revision }}' in job
    assert 'persist-credentials: false' in job
    assert 'cancel-in-progress: false' in job
    assert 'character-status-wago' in job
    assert job.count("if: steps.wago-config.outputs.ready == 'true'") == 3
    assert 'WAGO_API_TOKEN: ${{ secrets.WAGO_API_TOKEN }}' in job
    assert 'WAGO_PROJECT_ID: ${{ vars.WAGO_PROJECT_ID }}' in job
    assert 'scripts/voices.py bundle' in job
    curseforge = text.split('\n  curseforge:\n')[1].split('\n  wago:\n')[0]
    assert '!inputs.wago_only' in curseforge
    assert 'WAGO_EDITION: ${{ inputs.wago_edition || \'all\' }}' in job
