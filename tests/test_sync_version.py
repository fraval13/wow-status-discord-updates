import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load_sync():
    spec = importlib.util.spec_from_file_location('sync_version', ROOT / 'scripts/sync_version.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sync = load_sync()

TOC = """## Interface: 11509
## Title: WoW Status — Vanilla Classic
## Author: fraval13
## Version: 0.1.0
## SavedVariables: WoWStatusDB
Safe.lua
"""


@pytest.fixture
def project(tmp_path):
    """A minimal tree laid out like the real repository, already in step."""
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "x"\nversion = "0.1.0"\n',
                                             encoding='utf-8')
    for edition in sync.EDITIONS:
        folder = tmp_path / 'addon' / edition / 'WoWStatus'
        folder.mkdir(parents=True)
        (folder / 'WoWStatus.toc').write_text(TOC, encoding='utf-8')
    return tmp_path


def bump(project, version):
    (project / 'pyproject.toml').write_text(f'[project]\nname = "x"\nversion = "{version}"\n',
                                            encoding='utf-8')


def test_in_step_project_has_nothing_to_do(project):
    version, stale = sync.plan(project)
    assert version == '0.1.0' and stale == []


def test_every_edition_is_reported_when_pyproject_moves_ahead(project):
    bump(project, '0.2.0')
    version, stale = sync.plan(project)
    assert version == '0.2.0'
    assert [path.parent.parent.name for path, _ in stale] == list(sync.EDITIONS)
    assert {current for _, current in stale} == {'0.1.0'}


def test_rewriting_touches_only_the_version_value():
    rewritten = sync.retarget(TOC, '9.9.9')
    assert '## Version: 9.9.9\n' in rewritten
    assert rewritten.splitlines()[:3] == TOC.splitlines()[:3]
    assert rewritten.endswith('Safe.lua\n')
    assert len(rewritten.splitlines()) == len(TOC.splitlines())


def test_rewriting_preserves_crlf_and_a_missing_trailing_newline():
    source = '## Title: x\r\n## Version: 0.1.0\r\nSafe.lua'
    rewritten = sync.retarget(source, '0.2.0')
    assert rewritten == '## Title: x\r\n## Version: 0.2.0\r\nSafe.lua'


def test_a_toc_without_a_version_line_is_an_error(project):
    toc = project / 'addon/vanilla/WoWStatus/WoWStatus.toc'
    toc.write_text('## Title: x\nSafe.lua\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Version'):
        sync.plan(project)


def test_a_duplicated_version_line_is_refused_rather_than_half_rewritten():
    with pytest.raises(ValueError, match='More than one'):
        sync.retarget('## Version: 1\n## Version: 2\n', '3')


def test_a_missing_toc_is_an_error(project):
    (project / 'addon/tbc/WoWStatus/WoWStatus.toc').unlink()
    with pytest.raises(ValueError, match='Missing TOC'):
        sync.plan(project)


def test_a_blank_or_absent_project_version_is_an_error(project):
    (project / 'pyproject.toml').write_text('[project]\nname = "x"\n', encoding='utf-8')
    with pytest.raises(ValueError, match='No project.version'):
        sync.project_version(project)
    bump(project, '   ')
    with pytest.raises(ValueError, match='non-empty'):
        sync.project_version(project)


def test_repository_tocs_all_declare_the_pyproject_version():
    """The published downloads carry the TOC version, so drift must fail here first."""
    version, stale = sync.plan(ROOT)
    assert stale == [], f'run scripts/sync_version.py; these differ from {version}: ' + ', '.join(
        f'{path.parent.parent.name} {current}' for path, current in stale)
