"""Public addon ZIPs ship only what the game loads, and only at the project version."""
import importlib.util
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
EDITIONS = ('vanilla', 'forever', 'tbc', 'retail')


def builder():
    spec = importlib.util.spec_from_file_location('homepage_build', ROOT / 'scripts/build_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                           '-c', 'commit.gpgsign=false', *args], check=True, capture_output=True).stdout


def zip_names(output, edition):
    with zipfile.ZipFile(output / f'downloads/WoWStatus-{edition}.zip') as package:
        return package.namelist()


@pytest.fixture
def addon_repo(tmp_path):
    """A small Git repository holding this checkout's website, addons and pyproject.toml."""
    repo = tmp_path / 'repo'
    shutil.copytree(ROOT / 'website', repo / 'website')
    for edition in EDITIONS:
        shutil.copytree(ROOT / f'addon/{edition}/WoWStatus', repo / f'addon/{edition}/WoWStatus')
    shutil.copy2(ROOT / 'pyproject.toml', repo / 'pyproject.toml')
    git(repo, 'init', '-q')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'release')
    return repo


def commit(repo, files):
    for name, data in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # -f: the project .gitignore does not apply here, but a developer's global one might.
    git(repo, 'add', '-f', *files)
    git(repo, 'commit', '-q', '-m', 'change')


def test_current_release_ships_every_committed_addon_file(tmp_path):
    builder().build(ROOT, tmp_path, 'HEAD')
    for edition in EDITIONS:
        folder = f'addon/{edition}/WoWStatus/'
        tracked = git(ROOT, 'ls-tree', '-r', '--name-only', 'HEAD', '--', folder).decode().splitlines()
        assert zip_names(tmp_path, edition) == sorted('WoWStatus/' + name.removeprefix(folder) for name in tracked)


def test_unlisted_committed_files_stay_out_of_every_zip(addon_repo, tmp_path):
    module = builder()
    module.build(addon_repo, tmp_path / 'clean', 'HEAD')
    stray = {}
    for edition in EDITIONS:
        folder = f'addon/{edition}/WoWStatus/'
        stray |= {folder + '.DS_Store': b'\0\0\0\1Bud1', folder + 'WTF/WoWStatus.lua': b'WoWStatusDB = {}\n',
                  folder + 'Textures/.DS_Store': b'\0', folder + 'Textures/Logo.psd': b'8BPS',
                  folder + 'Textures/Old/Logo.tga': b'\0', folder + 'Notes.lua': b'-- not in the TOC\n'}
    commit(addon_repo, stray)
    module.build(addon_repo, tmp_path / 'stray', 'HEAD')
    for edition in EDITIONS:
        names = zip_names(tmp_path / 'stray', edition)
        assert names == zip_names(tmp_path / 'clean', edition)
        assert 'WoWStatus/Textures/Logo.tga' in names
        assert 'WoWStatus/Textures/LevelUp.tga' in names


def test_pyproject_version_must_match_the_addon_tocs(addon_repo, tmp_path):
    pyproject = (addon_repo / 'pyproject.toml').read_text(encoding='utf-8')
    version = builder().project_version(addon_repo, 'HEAD')
    commit(addon_repo, {'pyproject.toml': pyproject.replace(f'version = "{version}"',
                                                            'version = "9.9.9"').encode()})
    with pytest.raises(ValueError, match='pyproject.toml version 9.9.9'):
        builder().build(addon_repo, tmp_path, 'HEAD')


def test_a_toc_listed_file_must_be_committed(addon_repo, tmp_path):
    git(addon_repo, 'rm', '-q', 'addon/tbc/WoWStatus/Popups.lua')
    git(addon_repo, 'commit', '-q', '-m', 'drop')
    with pytest.raises(ValueError, match='Missing addon file: Popups.lua'):
        builder().build(addon_repo, tmp_path, 'HEAD')


def test_package_files_reads_toc_paths_and_allowlisted_textures():
    toc = '## Version: 1.0\n# comment\r\nLibs\\Lib.lua\r\n\nCore.lua\n'
    tracked = {'WoWStatus.toc', 'Libs/Lib.lua', 'Core.lua', 'Extra.lua', 'Textures/Logo.tga',
               'Textures/Logo.TGA.bak', 'Textures/Deep/Logo.tga', 'WTF/WoWStatus.lua', '.DS_Store'}
    assert builder().package_files(toc, tracked) == ['Core.lua', 'Libs/Lib.lua', 'Textures/Logo.tga',
                                                     'WoWStatus.toc']
