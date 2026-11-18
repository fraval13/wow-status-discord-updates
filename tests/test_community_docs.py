"""The public-facing files an outsider meets first (#197).

There is no YAML parser in the development environment, so the issue forms are
checked as text: GitHub validates the schema itself when it renders them, and
what matters here is that the fields the maintainer needs are actually asked for
and that nothing private leaks into a file strangers read.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / '.github/ISSUE_TEMPLATE'
# Anything that must never be repeated into a public-facing file. The server
# address and the private configuration path are deployment details.
PRIVATE = (re.compile(r'\b193\.243\.189\.202\b'), re.compile(r'/etc/wow-character-status'),
           re.compile(r'CURSEFORGE_\w*TOKEN'), re.compile(r'\bGITHUB_TOKEN\b'),
           re.compile(r'groups\.json'))


def public_files():
    return [ROOT / 'CONTRIBUTING.md', ROOT / 'SECURITY.md', *sorted(TEMPLATES.glob('*.yml'))]


def test_the_three_public_files_exist():
    assert (ROOT / 'CONTRIBUTING.md').is_file()
    assert (ROOT / 'SECURITY.md').is_file()
    assert {path.name for path in TEMPLATES.glob('*')} == {
        'bug_report.yml', 'feature_request.yml', 'config.yml'}


@pytest.mark.parametrize('path', public_files(), ids=lambda path: path.name)
def test_no_private_deployment_detail_reaches_a_public_file(path):
    text = path.read_text(encoding='utf-8')
    for pattern in PRIVATE:
        assert pattern.search(text) is None, f'{path.name} names {pattern.pattern}'


def test_the_bug_form_asks_for_everything_a_fix_needs_without_a_follow_up():
    form = (TEMPLATES / 'bug_report.yml').read_text(encoding='utf-8')
    for field in ('what-happened', 'steps', 'edition', 'addon-version', 'client-build',
                  'diagnostics'):
        assert f'id: {field}' in form, field
    # The four editions a reporter can be playing, so nobody has to be asked.
    for edition in ('Vanilla', 'Forever', 'TBC', 'Retail'):
        assert edition in form, edition
    # /wstatus errors is the one command that answers most follow-up questions.
    assert '/wstatus errors' in form
    # A group ID is a shared secret: the form says so and makes the reporter confirm.
    assert 'group ID' in form
    assert form.count('required: true') >= 4


def test_the_feature_form_asks_what_and_why():
    form = (TEMPLATES / 'feature_request.yml').read_text(encoding='utf-8')
    assert 'id: idea' in form and 'id: why' in form
    assert 'required: true' in form


def test_blank_issues_are_off_and_questions_are_sent_elsewhere():
    config = (TEMPLATES / 'config.yml').read_text(encoding='utf-8')
    assert 'blank_issues_enabled: false' in config
    assert 'curseforge.com' in config
    # A security problem must never arrive as an ordinary issue.
    assert 'security/policy' in config


def test_security_policy_keeps_reports_private_and_names_the_real_risks():
    policy = (ROOT / 'SECURITY.md').read_text(encoding='utf-8')
    assert 'do not open a public issue' in policy.lower()
    assert 'Report a vulnerability' in policy
    # The risks that are actually specific to this addon.
    for subject in ('Group names', 'privacy choice', 'homepage'):
        assert subject in policy, subject


def test_contributing_states_the_rules_that_break_a_pull_request():
    guide = (ROOT / 'CONTRIBUTING.md').read_text(encoding='utf-8')
    for rule in ('pytest -q', '--lua=5.1', 'addon/shared/', 'scripts/sync_addons.py',
                 'changelog.d/', 'LocaleNN.lua', 'Gamepad.lua', 'AGENTS.md'):
        assert rule in guide, rule
    # Feature branches must not bump the version.
    assert 'Do not change the version' in guide
