"""The workflows run pinned actions, keep no token on disk and fence the deploy (issue #27)."""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WORKFLOWS = sorted((ROOT / '.github/workflows').glob('*.yml'))
# owner/repo[/path]@<full commit SHA> # v<tag>, so the tag can be read and updated.
PINNED = re.compile(r'uses: [\w.-]+/[\w.-]+(?:/[\w.-]+)*@[0-9a-f]{40} # v\d+(?:\.\d+)+')


def steps(text):
    return text.split('\n      - ')[1:]


def deploy_job():
    text = (ROOT / '.github/workflows/checks.yml').read_text(encoding='utf-8')
    return text[text.index('\n  deploy:\n'):]


@pytest.mark.parametrize('workflow', WORKFLOWS, ids=lambda path: path.name)
def test_no_plain_value_holds_a_colon_and_space(workflow):
    """YAML reads `key: a: b` as a nested mapping, and GitHub then rejects the whole file."""
    plain = [line for line in workflow.read_text(encoding='utf-8').splitlines()
             if (match := re.match(r'\s*(?:- )?[\w-]+: (.+)$', line))
             and match.group(1)[0] not in '|>\'"#{[' and ': ' in match.group(1).split(' #')[0]]
    assert plain == []


@pytest.mark.parametrize('workflow', WORKFLOWS, ids=lambda path: path.name)
def test_every_action_is_pinned_to_a_full_commit_sha(workflow):
    uses = [line.strip().removeprefix('- ') for line in workflow.read_text(encoding='utf-8').splitlines()
            if re.match(r'\s*(?:- )?uses:', line)]
    assert uses and [line for line in uses if not PINNED.fullmatch(line)] == []


@pytest.mark.parametrize('workflow', WORKFLOWS, ids=lambda path: path.name)
def test_no_checkout_leaves_the_github_token_in_the_repository(workflow):
    checkouts = [step for step in steps(workflow.read_text(encoding='utf-8')) if 'uses: actions/checkout@' in step]
    assert checkouts and all('persist-credentials: false' in step for step in checkouts)


def test_the_deploy_job_runs_in_a_protected_environment():
    job = deploy_job()
    header = job.split('\n    steps:\n')[0]
    assert re.search(r'\n    environment:\n      name: production\n', header)


def test_the_deploy_job_runs_no_third_party_action_besides_checkout():
    # It holds the deploy key and bot tokens; setup-python would run before them.
    job = deploy_job()
    assert re.findall(r'uses: ([\w.-]+/[\w.-]+)@', job) == ['actions/checkout']
    interpreters = re.findall(r'(?m)^\s+(?:run: )?(python\S*) (?:scripts|deploy)/', job)
    assert len(interpreters) == 4 and set(interpreters) == {'python3'}  # the runner image's own


def test_ci_installs_the_lock_with_the_receivers_own_pip_arguments(monkeypatch):
    """The validate job's mirror step must not drift from deploy/install_release.py."""
    spec = importlib.util.spec_from_file_location('ci_receiver', ROOT / 'deploy/install_release.py')
    receiver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(receiver)
    commands = []
    monkeypatch.setattr(receiver, 'run', lambda *args: commands.append(args))
    receiver.install_dependencies(Path('/release'))
    pip = [command[command.index('install') + 1:] for command in commands if 'pip' in command]
    text = (ROOT / '.github/workflows/checks.yml').read_text(encoding='utf-8')
    step = next(step for step in steps(text) if step.startswith('name: Install the locked release'))
    lines = [line.strip() for line in step.splitlines()]
    assert len(pip) == 2
    for command in pip:
        shared, own = ' '.join(command[:2]), ' '.join(command[2:])
        assert shared in next(line for line in lines if line.startswith('pip=('))
        own = own.replace('/release/requirements.txt', '"$release/requirements.txt"').replace('/release', '"$release"')
        assert f'"${{pip[@]}}" {own}' in lines
