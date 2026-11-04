import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load():
    spec = importlib.util.spec_from_file_location('bump_version', ROOT / 'scripts/bump_version.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bump_version = load()


@pytest.fixture
def repo(tmp_path):
    shutil.copy(ROOT / 'pyproject.toml', tmp_path / 'pyproject.toml')
    for edition in bump_version.EDITIONS:
        folder = tmp_path / 'addon' / edition / 'WoWStatus'
        folder.mkdir(parents=True)
        shutil.copy(ROOT / 'addon' / edition / 'WoWStatus' / 'WoWStatus.toc', folder / 'WoWStatus.toc')
    return tmp_path


def test_repository_versions_agree():
    assert len(set(bump_version.current().values())) == 1


def test_bump_changes_only_the_five_version_lines(repo):
    before = {path: path.read_text(encoding='utf-8') for path, _ in bump_version.files(repo)}
    bump_version.bump('9.8.7', repo)
    assert set(bump_version.current(repo).values()) == {'9.8.7'}
    for path, text in before.items():
        after = path.read_text(encoding='utf-8')
        changed = [(a, b) for a, b in zip(text.splitlines(), after.splitlines(), strict=True) if a != b]
        assert len(changed) == 1 and '9.8.7' in changed[0][1]


def test_bump_rejects_a_malformed_version(repo):
    with pytest.raises(SystemExit):
        bump_version.bump('v1.2', repo)
    assert len(set(bump_version.current(repo).values())) == 1
