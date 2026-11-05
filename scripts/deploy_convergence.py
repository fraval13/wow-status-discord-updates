"""Decide whether production needs a fresh deploy run to catch up with main.

`deploy_gate.py` keeps an older commit from deploying over a newer one: a run whose
commit is no longer the tip of `main` skips its deploy. That ordering is right, but
on its own it never converges. While merges land faster than a run takes, every run
finds a newer tip and stands aside, and the run for the final commit may fail its
checks, so the last successful deploy can stay many commits behind indefinitely with
nothing left to publish it.

This decides, after each pipeline finishes, whether to dispatch one more run for the
current tip:

- `in-sync`  production already serves the tip; nothing to do.
- `wait`     a run for `main` is queued or running; let it finish and decide then.
- `dispatch` the tip validated successfully but production is behind, or the tip has
             no run at all. One `workflow_dispatch` on the tip publishes it.
- `blocked`  the tip's own run failed its checks. Dispatching would repeat that
             failure forever, so this reports instead; fix the commit or push a new
             one. This is what keeps the workflow from looping on a broken tip.

The decision is pure, so the caller fetches the facts and acts on the verdict.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

UNFINISHED = ('queued', 'in_progress', 'waiting', 'requested', 'pending')


def latest_run_for(runs, revision):
    """The newest run for `revision`, by the order GitHub returns (newest first)."""
    for run in runs:
        if run.get('head_sha') == revision:
            return run
    return None


def decide(tip, deployed, runs):
    """Return (verdict, reason). `runs` is newest-first, as the REST API returns."""
    if not tip:
        raise ValueError('No tip revision')
    if deployed == tip:
        return 'in-sync', f'production already serves {tip[:12]}'
    busy = [run for run in runs if run.get('status') in UNFINISHED]
    if busy:
        return 'wait', (f"{len(busy)} run(s) for main still going, newest "
                        f"{busy[0].get('head_sha', '?')[:12]}; deciding after they finish")
    run = latest_run_for(runs, tip)
    serving = deployed[:12] if deployed else 'nothing'
    if run is None:
        return 'dispatch', f'tip {tip[:12]} has no run yet; production serves {serving}'
    conclusion = run.get('conclusion')
    if conclusion == 'success':
        return 'dispatch', (f'tip {tip[:12]} passed its checks but production serves '
                            f'{serving}; dispatching one run to publish it')
    return 'blocked', (f'tip {tip[:12]} concluded {conclusion!r}, so a new run would fail the '
                       f'same way; production stays on {serving} until the tip is fixed')


def load_runs(text):
    """Runs from `gh api` output, newest first.

    With --paginate, gh prints one JSON document per page back to back, so the
    file can hold several objects; their workflow_runs are joined in page order.
    """
    decoder, runs, index = json.JSONDecoder(), [], 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            return runs
        payload, index = decoder.raw_decode(text, index)
        if isinstance(payload, dict):
            payload = payload.get('workflow_runs', [])
        runs.extend(payload)


def append_output(name, value):
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(f'{name}={value}\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tip', required=True, help='Current revision of main.')
    parser.add_argument('--deployed', default='', help='Revision production serves.')
    parser.add_argument('--runs', required=True,
                        help='JSON file of the workflow runs for main, newest first.')
    args = parser.parse_args(argv)
    with open(args.runs, encoding='utf-8') as handle:
        runs = load_runs(handle.read())
    try:
        verdict, reason = decide(args.tip, args.deployed, runs)
    except ValueError as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    print(f'{verdict}: {reason}')
    append_output('verdict', verdict)
    append_output('reason', reason)
    if verdict == 'blocked':
        # A notice, not a failure: the broken tip is the problem to fix, not this run.
        print(f'::warning title=Production is behind main::{reason}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
