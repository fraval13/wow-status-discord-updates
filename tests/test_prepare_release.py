"""Exercise release commits against local bare remotes, including retries and races."""
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_release as release  # noqa: E402


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True, encoding='utf-8').stdout.strip()


def commit(root, subject):
    git(root, 'add', '.')
    git(root, 'commit', '-m', subject)
    return git(root, 'rev-parse', 'HEAD')


@pytest.fixture
def repository(tmp_path, request):
    root, remote = tmp_path / 'repo', tmp_path / 'remote.git'
    root.mkdir()
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.name', 'Release tests')
    git(root, 'config', 'user.email', 'release-tests@example.invalid')
    git(root, 'config', 'commit.gpgsign', 'false')
    git(root, 'config', 'core.autocrlf', getattr(request, 'param', 'false'))
    for path in release.files(root):
        path.parent.mkdir(parents=True, exist_ok=True)
    (root / 'pyproject.toml').write_text('[project]\nname = "release-fixture"\nversion = "0.14.14"\n',
                                       encoding='utf-8', newline='\n')
    changelog = "# What's New\n\n## Unreleased\n\n- Raid milestones and recap sharing\n\n## 0.14.14\n\n- Previous release\n"
    (root / 'CHANGELOG.md').write_text(changelog, encoding='utf-8', newline='\n')
    notes = release.whats_new.render(release.whats_new.parse(changelog))
    for path in release.note_paths(root):
        path.write_text(notes, encoding='utf-8', newline='\n')
    # Minimal editions still use the real committed-source builder in the test below.
    for path in release.sync_version.toc_paths(root):
        path.write_text('## Interface: 11507\n## Version: 0.14.14\nWhatsNewData.lua\n', encoding='utf-8', newline='\n')
    (root / 'website').mkdir()
    (root / 'website/index.html').write_text(
        '<h1>__VERSION__</h1><ul>__WHATS_NEW__</ul>', encoding='utf-8', newline='\n')
    initial = commit(root, 'New raid milestones and recap sharing')
    git(root, 'init', '--bare', str(remote))
    git(root, 'remote', 'add', 'origin', str(remote))
    git(root, 'push', 'origin', 'HEAD:refs/heads/main')
    return root, remote, initial


@pytest.mark.parametrize("repository", ["false", "true"], indirect=True)
def test_release_increments_minor_once_and_reuses_the_exact_commit_on_retries(
        repository, monkeypatch, tmp_path):
    root, remote, source = repository
    output = tmp_path / 'output'
    monkeypatch.setattr(release, 'ROOT', root)
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    assert release.main(['--revision', source]) == 0
    prepared = git(root, 'rev-parse', 'HEAD')
    assert output.read_text(encoding='utf-8') == f'revision={prepared}\n'
    assert release.validate_release(root) == '0.15.0'
    assert git(remote, 'rev-parse', 'refs/heads/main') == prepared
    assert release.generated_source(root, prepared) == source
    assert set(git(root, 'diff-tree', '--no-commit-id', '--name-only', '-r', prepared).splitlines()) == {
        path.relative_to(root).as_posix() for path in release.files(root)}
    assert '\n## Unreleased\n' not in release.read(root / 'CHANGELOG.md')
    # A manual dispatch of the prepared commit must not increment again.
    assert release.prepare(root, prepared) == prepared
    # Nor should re-running the original triggering commit after a partial failure.
    git(root, 'checkout', '--detach', source)
    assert release.prepare(root, source) == prepared
    assert release.validate_release(root) == '0.15.0'


def test_next_main_change_gets_the_next_minor_and_fallback_notes(repository):
    root, _, source = repository
    release.prepare(root, source)
    (root / 'new-feature.txt').write_text('A new feature\n', encoding='utf-8', newline='\n')
    source = commit(root, 'Make activity clearer')
    git(root, 'push', 'origin', 'HEAD:refs/heads/main')
    release.prepare(root, source)
    assert release.validate_release(root) == '0.16.0'
    assert '- Make activity clearer\n' in release.read(root / 'CHANGELOG.md')


def test_explicit_release_version_is_not_incremented_twice(repository):
    root, _, _ = repository
    release.bump(root, '0.15.0', 'Intentional release')
    source = commit(root, 'Release 0.15.0')
    git(root, 'push', 'origin', 'HEAD:refs/heads/main')
    assert release.prepare(root, source) == source
    assert release.validate_release(root) == '0.15.0'


def test_stale_run_never_versions_or_overwrites_newer_main(repository):
    root, remote, source = repository
    (root / 'feature.txt').write_text('newer\n', encoding='utf-8', newline='\n')
    newer = commit(root, 'Newer main change')
    git(root, 'push', 'origin', 'HEAD:refs/heads/main')
    git(root, 'checkout', '--detach', source)
    assert release.prepare(root, source) == source
    assert git(remote, 'rev-parse', 'refs/heads/main') == newer
    assert release.validate_release(root) == '0.14.14'


def test_main_push_racing_release_preparation_is_never_overwritten(repository, monkeypatch, tmp_path):
    root, remote, source = repository
    competitor = tmp_path / 'competitor'
    git(root, 'clone', '--branch', 'main', str(remote), str(competitor))
    git(competitor, 'config', 'user.name', 'Other maintainer')
    git(competitor, 'config', 'user.email', 'other@example.invalid')
    (competitor / 'newer.txt').write_text('newer\n', encoding='utf-8', newline='\n')
    newer = commit(competitor, 'New main change during release preparation')
    original = release.git

    def racing_git(root, *args, **kwargs):
        if args and args[0] == 'push':
            git(competitor, 'push', 'origin', 'HEAD:refs/heads/main')
        return original(root, *args, **kwargs)

    monkeypatch.setattr(release, 'git', racing_git)
    with pytest.raises(subprocess.CalledProcessError):
        release.prepare(root, source)
    assert git(remote, 'rev-parse', 'refs/heads/main') == newer


def test_dirty_tracked_files_fail_and_untracked_branding_is_excluded(repository):
    root, remote, source = repository
    branding = root / 'assets/branding.txt'
    branding.parent.mkdir()
    branding.write_text('Keep this private working file\n', encoding='utf-8', newline='\n')
    project = root / 'pyproject.toml'
    before = project.read_bytes()
    project.write_bytes(before + b'\n# unfinished\n')
    with pytest.raises(ValueError, match='clean tracked checkout'):
        release.prepare(root, source)
    assert git(remote, 'rev-parse', 'refs/heads/main') == source
    project.write_bytes(before)
    prepared = release.prepare(root, source)
    assert branding.read_text(encoding='utf-8') == 'Keep this private working file\n'
    assert 'assets/' not in git(root, 'ls-tree', '-r', '--name-only', prepared)


def test_invalid_pending_notes_fail_before_any_release_file_is_written(repository):
    root, remote, _ = repository
    notes = root / 'CHANGELOG.md'
    notes.write_text(release.read(notes).replace('## Unreleased\n', '## Unreleased\n\n- bad|text\n'),
                     encoding='utf-8', newline='\n')
    source = commit(root, 'Invalid pending notes')
    git(root, 'push', 'origin', 'HEAD:refs/heads/main')
    before = {path: path.read_bytes() for path in release.files(root)}
    with pytest.raises(ValueError, match='printable characters'):
        release.prepare(root, source)
    assert {path: path.read_bytes() for path in release.files(root)} == before
    assert git(remote, 'rev-parse', 'refs/heads/main') == source


def test_release_builder_packages_the_prepared_revision_and_version_in_every_zip(repository, tmp_path):
    root, _, source = repository
    prepared = release.prepare(root, source)
    spec = importlib.util.spec_from_file_location('prepared_homepage', ROOT / 'scripts/build_homepage.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    output = tmp_path / 'site'
    builder.build(root, output, prepared)
    manifest = json.loads((output / 'downloads/release.json').read_text(encoding='utf-8'))
    assert manifest['addon_revision'] == prepared
    assert '0.15.0' in (output / 'index.html').read_text(encoding='utf-8')
    for edition, package in manifest['editions'].items():
        assert package['version'] == '0.15.0'
        with zipfile.ZipFile(output / 'downloads' / package['file']) as archive:
            assert b'## Version: 0.15.0\n' in archive.read('WoWStatus/WoWStatus.toc')
            assert b'version="0.15.0"' in archive.read('WoWStatus/WhatsNewData.lua')


def test_workflow_passes_prepared_commit_to_every_consumer_and_never_gives_prs_write_access():
    text = (ROOT / '.github/workflows/checks.yml').read_text(encoding='utf-8')
    release_job = text.split('\n  release:\n')[1].split('\n  validate:\n')[0]
    validate = text.split('\n  validate:\n')[1].split('\n  deploy-gate:\n')[0]
    gate = text.split('\n  deploy-gate:\n')[1].split('\n  deploy:\n')[0]
    deploy = text.split('\n  deploy:\n')[1]
    assert "github.ref == 'refs/heads/main'" in release_job
    assert "github.event_name == 'push' || github.event_name == 'workflow_dispatch'" in release_job
    assert 'contents: write' in release_job and 'contents: write' not in validate
    assert 'GH_TOKEN:' in release_job and 'GH_TOKEN:' not in validate
    assert 'needs: release' in validate and "needs.release.result == 'skipped'" in validate
    assert 'ref: ${{ needs.release.outputs.revision || github.sha }}' in validate
    assert 'needs: [release, validate]' in gate
    assert 'revision: ${{ needs.release.outputs.revision }}' in gate
    assert 'ref: ${{ needs.release.outputs.revision }}' in gate
    assert 'RELEASE_REVISION: ${{ needs.release.outputs.revision }}' in gate
    assert 'ref: ${{ needs.deploy-gate.outputs.revision }}' in deploy
    assert deploy.count('RELEASE_REVISION: ${{ needs.deploy-gate.outputs.revision }}') == 3
    assert 'github.sha' not in deploy
