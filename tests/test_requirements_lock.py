"""requirements.txt pins exactly what the server installs, by version and hash (issue #27).

The release receiver installs it with --require-hashes and wheels only, then builds
the project with no index, so it must pin every runtime dependency and the build
backend. CI also installs it the receiver's way and runs `pip check`, which catches
a missing transitive dependency; these checks run offline.
"""
import re
import tomllib
from pathlib import Path

import pytest

Requirement = pytest.importorskip('packaging.requirements').Requirement
from packaging.utils import canonicalize_name  # noqa: E402

ROOT = Path(__file__).parents[1]


def locked():
    """Name -> (Requirement, hashes) for each requirement in requirements.txt."""
    text = (ROOT / 'requirements.txt').read_text(encoding='utf-8').replace('\\\n', ' ')
    entries = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        requirement, *hashes = re.split(r'\s+--hash=', line.strip())
        parsed = Requirement(requirement)
        name = canonicalize_name(parsed.name)
        assert name not in entries, f'{name} is locked twice'
        entries[name] = parsed, hashes
    return entries


def project():
    return tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))


def test_every_locked_package_has_one_exact_version_and_its_hashes():
    for name, (requirement, hashes) in locked().items():
        specifiers = list(requirement.specifier)
        assert len(specifiers) == 1 and specifiers[0].operator == '==', name
        assert hashes and all(re.fullmatch('sha256:[0-9a-f]{64}', value) for value in hashes), name


@pytest.mark.parametrize('kind', ['dependencies', 'build-system'])
def test_the_lock_satisfies_every_requirement_in_pyproject(kind):
    data = project()
    wanted = data['project']['dependencies'] if kind == 'dependencies' else data['build-system']['requires']
    entries = locked()
    for text in wanted:
        requirement = Requirement(text)
        name = canonicalize_name(requirement.name)
        assert name in entries, f'{name} is not in requirements.txt; run python scripts/lock_requirements.py'
        version = next(iter(entries[name][0].specifier)).version
        assert requirement.specifier.contains(version, prereleases=True), (
            f'{name}=={version} does not satisfy pyproject.toml ({requirement.specifier}); '
            'run python scripts/lock_requirements.py')


def test_the_lock_says_how_to_regenerate_it():
    assert 'python scripts/lock_requirements.py' in (ROOT / 'requirements.txt').read_text(encoding='utf-8')
