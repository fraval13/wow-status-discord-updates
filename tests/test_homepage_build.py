"""Public addon ZIPs ship only what the game loads, and only at the project version."""
import importlib.util
import io
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load_builder():
    spec = importlib.util.spec_from_file_location('homepage_build', ROOT / 'scripts/build_homepage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def git(root, *args, data=None):
    # core.autocrlf=false: commit exactly the bytes a test writes, on Windows too.
    # core.hooksPath: a developer's global hooks must not run in the test repositories.
    return subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                           '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false',
                           '-c', 'core.hooksPath=no-hooks', *args],
                          input=data, check=True, capture_output=True).stdout


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
