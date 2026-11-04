"""An older pipeline run must never deploy over a newer one (issue #15)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GATE = ROOT / 'scripts' / 'deploy_gate.py'


def git(*args, cwd):
    # Same isolation as tests/test_homepage_build.py: no signing or global hooks.
    result = subprocess.run(
        ['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
         '-c', 'commit.gpgsign=false', '-c', 'core.autocrlf=false',
         '-c', 'core.hooksPath=no-hooks', *args],
        cwd=cwd, check=True, capture_output=True, encoding='utf-8')
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A clone whose `origin` is a local bare repository with commits A then B."""
    remote = tmp_path / 'remote.git'
    work = tmp_path / 'work'
    git('init', '--bare', str(remote), cwd=tmp_path)
    git('init', str(work), cwd=tmp_path)
    git('remote', 'add', 'origin', str(remote), cwd=work)
    commits = {}
    for name in ('A', 'B'):
        git('commit', '--allow-empty', '-m', name, cwd=work)
        commits[name] = git('rev-parse', 'HEAD', cwd=work)
    return work, commits


def push_main(work, revision):
    git('push', '--force', 'origin', f'{revision}:refs/heads/main', cwd=work)


def gate(work, tmp_path, revision, *extra):
    output = tmp_path / 'output'
    summary = tmp_path / 'summary'
    output.write_bytes(b'')
    summary.write_bytes(b'')
    env = {**os.environ, 'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary)}
    result = subprocess.run(
        [sys.executable, str(GATE), '--revision', revision, *extra],
        cwd=work, env=env, capture_output=True, encoding='utf-8')
    return result, output.read_text(encoding='utf-8'), summary.read_text(encoding='utf-8')


def test_tip_of_main_deploys(repo, tmp_path):
    work, commits = repo
    push_main(work, commits['B'])
    result, output, summary = gate(work, tmp_path, commits['B'])
    assert result.returncode == 0, result.stderr
    assert output == 'current=true\n'
    assert summary == ''
    assert 'Deploy skipped' not in result.stdout


def test_older_run_skips_with_notice(repo, tmp_path):
    work, commits = repo
    push_main(work, commits['B'])
    result, output, summary = gate(work, tmp_path, commits['A'])
    assert result.returncode == 0, result.stderr
    assert output == 'current=false\n'
    assert f'::notice title=Deploy skipped::Not deploying {commits["A"]}: main is now {commits["B"]}' in result.stdout
    assert commits['B'] in summary


def test_branch_ending_in_refs_heads_main_is_ignored(repo, tmp_path):
    work, commits = repo
    push_main(work, commits['B'])
    git('push', 'origin', f'{commits["A"]}:refs/heads/release/refs/heads/main', cwd=work)
    result, output, _ = gate(work, tmp_path, commits['B'])
    assert result.returncode == 0, result.stderr
    assert output == 'current=true\n'


def test_unreadable_main_fails_closed_and_says_why(repo, tmp_path):
    work, commits = repo
    git('remote', 'set-url', 'origin', str(tmp_path / 'missing.git'), cwd=work)
    result, output, _ = gate(work, tmp_path, commits['A'])
    assert result.returncode != 0
    assert output == ''
    assert 'missing.git' in result.stderr
