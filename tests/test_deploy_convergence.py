import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load():
    spec = importlib.util.spec_from_file_location(
        'deploy_convergence', ROOT / 'scripts/deploy_convergence.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


converge = load()

TIP = 'a' * 40
OLD = 'b' * 40


def run(sha, status='completed', conclusion='success'):
    return {'head_sha': sha, 'status': status, 'conclusion': conclusion}


def test_nothing_to_do_when_production_serves_the_tip():
    verdict, _ = converge.decide(TIP, TIP, [run(TIP)])
    assert verdict == 'in-sync'


def test_a_successful_tip_that_never_deployed_is_dispatched():
    # The exact gap: checks passed, but the deploy was skipped for a newer commit
    # that has since failed or vanished, so nothing ever published this tip.
    verdict, reason = converge.decide(TIP, OLD, [run(TIP)])
    assert verdict == 'dispatch'
    assert TIP[:12] in reason


def test_a_failing_tip_is_never_dispatched_so_the_workflow_cannot_loop():
    verdict, reason = converge.decide(TIP, OLD, [run(TIP, conclusion='failure')])
    assert verdict == 'blocked'
    assert 'fail' in reason


def test_a_cancelled_tip_run_is_also_blocked_rather_than_retried_forever():
    verdict, _ = converge.decide(TIP, OLD, [run(TIP, conclusion='cancelled')])
    assert verdict == 'blocked'


def test_an_unfinished_run_defers_the_decision():
    verdict, _ = converge.decide(TIP, OLD, [run(TIP, status='in_progress', conclusion=None)])
    assert verdict == 'wait'


def test_a_queued_run_for_an_older_commit_also_defers():
    verdict, _ = converge.decide(TIP, OLD, [run(TIP), run(OLD, status='queued', conclusion=None)])
    assert verdict == 'wait'


def test_a_tip_with_no_run_at_all_is_dispatched():
    verdict, reason = converge.decide(TIP, OLD, [run(OLD)])
    assert verdict == 'dispatch'
    assert 'no run yet' in reason


def test_only_the_newest_run_for_the_tip_decides():
    """A re-run that succeeded must not be overruled by an older failure."""
    runs = [run(TIP), run(TIP, conclusion='failure')]
    assert converge.decide(TIP, OLD, runs)[0] == 'dispatch'
    runs = [run(TIP, conclusion='failure'), run(TIP)]
    assert converge.decide(TIP, OLD, runs)[0] == 'blocked'


def test_an_empty_deployed_revision_still_dispatches():
    verdict, reason = converge.decide(TIP, '', [run(TIP)])
    assert verdict == 'dispatch'
    assert 'nothing' in reason


def test_a_missing_tip_is_an_error():
    with pytest.raises(ValueError, match='No tip'):
        converge.decide('', OLD, [])


def test_main_reads_the_rest_payload_and_reports_the_verdict(tmp_path, capsys, monkeypatch):
    runs = tmp_path / 'runs.json'
    runs.write_text(json.dumps({'workflow_runs': [run(TIP)]}), encoding='utf-8')
    output = tmp_path / 'out.txt'
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    assert converge.main(['--tip', TIP, '--deployed', OLD, '--runs', str(runs)]) == 0
    assert 'dispatch' in capsys.readouterr().out
    assert 'verdict=dispatch' in output.read_text(encoding='utf-8')


def test_main_warns_but_succeeds_on_a_blocked_tip(tmp_path, capsys):
    runs = tmp_path / 'runs.json'
    runs.write_text(json.dumps({'workflow_runs': [run(TIP, conclusion='failure')]}),
                    encoding='utf-8')
    assert converge.main(['--tip', TIP, '--deployed', OLD, '--runs', str(runs)]) == 0
    out = capsys.readouterr().out
    assert '::warning' in out and 'blocked' in out


def test_concatenated_pages_report_the_paginate_cause(tmp_path, capsys):
    """`gh api --paginate` emits one object per page; that is not valid JSON."""
    runs = tmp_path / 'runs.json'
    page = json.dumps({'workflow_runs': [run(TIP)]})
    runs.write_text(page + page, encoding='utf-8')
    assert converge.main(['--tip', TIP, '--deployed', OLD, '--runs', str(runs)]) == 2
    assert '--paginate' in capsys.readouterr().err


def test_a_payload_that_is_not_a_list_of_runs_is_refused(tmp_path, capsys):
    runs = tmp_path / 'runs.json'
    runs.write_text(json.dumps({'workflow_runs': {'oops': True}}), encoding='utf-8')
    assert converge.main(['--tip', TIP, '--deployed', OLD, '--runs', str(runs)]) == 2
    assert 'expected a list' in capsys.readouterr().err
