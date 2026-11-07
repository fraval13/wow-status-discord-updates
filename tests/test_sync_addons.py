import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

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


def test_stale_tracked_texture_is_deleted_with_its_empty_folders(repo):
    for folder in editions(repo):
        (folder / 'Textures/Old/Textures').mkdir(parents=True)
        (folder / 'Textures/Old/Textures/Gone.tga').write_bytes(b'old')
    git(repo, 'add', '-A')
    assert sync.main([], repo=repo) == 0
    for folder in editions(repo):
        assert not (folder / 'Textures/Old').exists()
        assert (folder / 'Textures/Logo.tga').exists()


def test_stale_file_with_unstaged_edits_stops_the_run(repo, capsys):
    (repo / 'addon/shared/Core.lua').unlink()
    git(repo, 'add', '-A')
    (repo / 'addon/tbc/WoWStatus/Core.lua').write_bytes(b'-- local edits\n')
    assert sync.main([], repo=repo) == 2
    assert 'unstaged edits' in capsys.readouterr().err
    assert (repo / 'addon/vanilla/WoWStatus/Core.lua').exists()
    assert (repo / 'addon/tbc/WoWStatus/Core.lua').read_bytes() == b'-- local edits\n'


def test_untracked_shared_source_stops_deleting_its_tracked_copies(repo, capsys):
    (repo / 'addon/shared/New.lua').write_bytes(b'-- new\n')
    for folder in editions(repo):
        (folder / 'New.lua').write_bytes(b'-- new\n')
    git(repo, 'add', 'addon/vanilla', 'addon/forever', 'addon/tbc', 'addon/retail')
    assert sync.main([], repo=repo) == 2
    assert 'addon/shared/New.lua is untracked' in capsys.readouterr().err
    assert all((folder / 'New.lua').exists() for folder in editions(repo))


def test_shared_file_moved_without_git_stops_the_run(repo, capsys):
    shared = repo / 'addon/shared'
    (shared / 'Core.lua').rename(shared / 'CoreRenamed.lua')
    assert sync.main([], repo=repo) == 2
    assert 'addon/shared/Core.lua' in capsys.readouterr().err
    for folder in editions(repo):
        assert (folder / 'Core.lua').exists()


def test_case_only_rename_rewrites_the_file_after_deleting_the_old_name(repo):
    git(repo, 'mv', 'addon/shared/Textures/Logo.tga', 'addon/shared/Textures/LOGO.tga')
    plan = sync.plan_sync(repo)
    for folder in editions(repo):
        assert (folder, PurePosixPath('Textures/Logo.tga')) in plan.deletes
        assert (repo / 'addon/shared/Textures/LOGO.tga', folder / 'Textures/LOGO.tga') in plan.copies


def test_case_only_rename_prints_a_git_mv_hint(repo, capsys):
    git(repo, 'mv', 'addon/shared/Textures/Logo.tga', 'addon/shared/Textures/LOGO.tga')
    plan = sync.plan_sync(repo)
    tbc = repo / 'addon/tbc/WoWStatus/Textures'
    assert (tbc / 'Logo.tga', tbc / 'LOGO.tga') in plan.case_renames
    assert sync.main(['--check'], repo=repo) == 1
    assert sync.main([], repo=repo) == 0
    assert ('case-only rename: on Windows/macOS run git mv addon/tbc/WoWStatus/Textures/Logo.tga '
            'addon/tbc/WoWStatus/Textures/LOGO.tga') in capsys.readouterr().out


def test_stale_file_where_a_shared_folder_now_is_is_replaced(repo):
    for folder in editions(repo):
        (folder / 'Textures/Icons').write_bytes(b'old file')
    git(repo, 'add', '-A')
    nested = repo / 'addon/shared/Textures/Icons'
    nested.mkdir()
    (nested / 'Star.tga').write_bytes(b'star')
    git(repo, 'add', '-A')
    assert sync.main([], repo=repo) == 0
    for folder in editions(repo):
        assert (folder / 'Textures/Icons/Star.tga').read_bytes() == b'star'


def test_apply_deletes_before_copying(tmp_path):
    # On a case-insensitive filesystem the old and new names are one file; model
    # that by deleting and copying the same path.
    source, folder = tmp_path / 'Logo.tga', tmp_path / 'WoWStatus'
    (folder / 'Textures').mkdir(parents=True)
    source.write_bytes(b'logo')
    (folder / 'Textures/Logo.tga').write_bytes(b'logo')
    plan = sync.Plan(copies=[(source, folder / 'Textures/Logo.tga')],
                     deletes=[(folder, PurePosixPath('Textures/Logo.tga'))])
    sync.apply(plan)
    assert (folder / 'Textures/Logo.tga').read_bytes() == b'logo'


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


def _in_git_checkout(path):
    result = subprocess.run(['git', '-C', str(path), 'rev-parse', '--is-inside-work-tree'],
                            capture_output=True, encoding='utf-8')
    return result.returncode == 0


@pytest.mark.skipif(shutil.which('git') is None or not _in_git_checkout(ROOT),
                    reason='needs a Git checkout')
def test_repository_editions_mirror_shared_files_both_ways():
    """CI guard: every tracked shared Lua/texture is in each edition, and nothing extra is."""
    plan = sync.plan_sync(ROOT)
    assert not plan.copies, [str(target) for _, target in plan.copies]
    assert not plan.deletes, [str(folder / path) for folder, path in plan.deletes]
    def mirrored(folder):
        return {path for path in sync._git_files(ROOT, folder) if sync.in_scope(path)}

    shared = mirrored(ROOT / 'addon/shared')
    assert shared
    for edition, owned in sync.EDITIONS.items():
        files = mirrored(ROOT / 'addon' / edition / 'WoWStatus')
        assert {PurePosixPath(name) for name in owned} <= files, edition
        assert files - {PurePosixPath(name) for name in owned} == shared, edition


def test_key_bindings_are_mirrored_like_shared_lua():
    assert sync.in_scope(PurePosixPath('Bindings.xml'))
    assert not sync.in_scope(PurePosixPath('Other.xml'))
    assert not sync.in_scope(PurePosixPath('Libs/Bindings.xml'))
