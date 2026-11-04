import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git is required')


def load_sync():
    spec = importlib.util.spec_from_file_location('sync_addons', ROOT / 'scripts/sync_addons.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


sync = load_sync()


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A minimal repository laid out like the real addon folders, already in sync."""
    git(tmp_path, 'init', '-q')
    shared = tmp_path / 'addon/shared'
    (shared / 'Textures').mkdir(parents=True)
    (shared / 'Core.lua').write_bytes(b'-- core\n')
    (shared / 'Textures/Logo.tga').write_bytes(b'logo')
    for edition, owned in sync.EDITIONS.items():
        folder = tmp_path / 'addon' / edition / 'WoWStatus'
        (folder / 'Textures').mkdir(parents=True)
        (folder / 'Core.lua').write_bytes(b'-- core\n')
        (folder / 'Textures/Logo.tga').write_bytes(b'logo')
        (folder / 'WoWStatus.toc').write_bytes(b'## Title: WoW Status\n')
        for name in owned:
            (folder / name).write_bytes(f'-- {edition} adapter\n'.encode('utf-8'))
    git(tmp_path, 'add', '-A')
    return tmp_path


def editions(repo):
    return [repo / 'addon' / edition / 'WoWStatus' for edition in sync.EDITIONS]


def test_in_sync_repository_has_nothing_to_do(repo):
    plan = sync.plan_sync(repo)
    assert plan.in_sync and not plan.untracked_extras and not plan.untracked_shared
    assert sync.main(['--check'], repo=repo) == 0


def test_changed_shared_file_is_copied_to_every_edition(repo):
    (repo / 'addon/shared/Core.lua').write_bytes(b'-- core v2\n')
    assert sync.main(['--check'], repo=repo) == 1
    assert sync.main([], repo=repo) == 0
    for folder in editions(repo):
        assert (folder / 'Core.lua').read_bytes() == b'-- core v2\n'
    assert sync.plan_sync(repo).in_sync


def test_stale_tracked_edition_file_is_deleted_and_edition_files_kept(repo):
    (repo / 'addon/shared/Core.lua').unlink()
    (repo / 'addon/shared/Other.lua').write_bytes(b'-- other\n')
    git(repo, 'add', '-A')
    assert sync.main([], repo=repo) == 0
    for folder, owned in zip(editions(repo), sync.EDITIONS.values()):
        assert not (folder / 'Core.lua').exists()
        assert (folder / 'Other.lua').read_bytes() == b'-- other\n'
        assert (folder / 'WoWStatus.toc').exists()
        assert all((folder / name).exists() for name in owned)


def test_stale_tracked_texture_is_deleted_with_its_empty_folder(repo):
    for folder in editions(repo):
        (folder / 'Textures/Old').mkdir()
        (folder / 'Textures/Old/Gone.tga').write_bytes(b'old')
    git(repo, 'add', '-A')
    assert sync.main([], repo=repo) == 0
    for folder in editions(repo):
        assert not (folder / 'Textures/Old').exists()
        assert (folder / 'Textures/Logo.tga').exists()


def test_dotfiles_and_untracked_shared_files_are_not_copied(repo, capsys):
    shared = repo / 'addon/shared'
    (shared / 'Textures/.DS_Store').write_bytes(b'junk')
    (shared / '.scratch.lua').write_bytes(b'-- dotfile\n')
    (shared / 'Scratch.lua').write_bytes(b'-- untracked\n')
    git(repo, 'add', '-f', 'addon/shared/Textures/.DS_Store')
    assert sync.main([], repo=repo) == 0
    for folder in editions(repo):
        assert not (folder / 'Textures/.DS_Store').exists()
        assert not (folder / '.scratch.lua').exists()
        assert not (folder / 'Scratch.lua').exists()
    assert 'skipped untracked shared file (git add it to sync): addon/shared/Scratch.lua' in (
        capsys.readouterr().out)


def test_untracked_edition_files_are_reported_but_kept(repo, capsys):
    vanilla = repo / 'addon/vanilla/WoWStatus'
    (vanilla / 'Local.lua').write_bytes(b'-- uncommitted work\n')
    (vanilla / 'Textures/.DS_Store').write_bytes(b'junk')
    plan = sync.plan_sync(repo)
    assert plan.in_sync and plan.untracked_extras == [vanilla / 'Local.lua']
    assert sync.main([], repo=repo) == 0
    assert (vanilla / 'Local.lua').exists()
    assert 'left untracked edition file in place: addon/vanilla/WoWStatus/Local.lua' in (
        capsys.readouterr().out)


def test_texture_subfolders_are_mirrored_without_crashing(repo):
    nested = repo / 'addon/shared/Textures/Icons'
    nested.mkdir()
    (nested / 'Star.tga').write_bytes(b'star')
    git(repo, 'add', '-A')
    assert sync.main([], repo=repo) == 0
    for folder in editions(repo):
        assert (folder / 'Textures/Icons/Star.tga').read_bytes() == b'star'


def test_problems_are_found_before_any_edition_is_written(repo):
    (repo / 'addon/shared/Core.lua').write_bytes(b'-- core v2\n')
    retail = repo / 'addon/retail/WoWStatus'
    (retail / 'Textures/Logo.tga').unlink()
    (retail / 'Textures/Logo.tga').mkdir()
    assert sync.main([], repo=repo) == 2
    assert (repo / 'addon/vanilla/WoWStatus/Core.lua').read_bytes() == b'-- core\n'


def test_repository_editions_mirror_shared_files_both_ways():
    """CI guard: every tracked shared Lua/texture is in each edition, and nothing extra is."""
    plan = sync.plan_sync(ROOT)
    assert not plan.copies, [str(target) for _, target in plan.copies]
    assert not plan.deletes, [str(target) for target in plan.deletes]
    tracked = subprocess.run(
        ['git', '-C', str(ROOT), 'ls-files', '-z', '--', 'addon'],
        check=True, capture_output=True, encoding='utf-8',
    ).stdout.split('\0')
    for edition, owned in sync.EDITIONS.items():
        prefix = f'addon/{edition}/WoWStatus/'
        mirrored = {
            name[len(prefix):] for name in tracked
            if name.startswith(prefix) and name.endswith(('.lua', '.tga', '.blp'))
        }
        shared = {
            name[len('addon/shared/'):] for name in tracked
            if name.startswith('addon/shared/') and name.endswith(('.lua', '.tga', '.blp'))
        }
        assert mirrored - owned == shared, edition
