"""Decide whether a pipeline run may deploy: only while its commit is the tip of main.

Used twice by the "Checks and addon packages" workflow (issue #15). The
`deploy-gate` job runs it before `deploy` joins the production concurrency
group, so an older run never queues there and cancels a newer run's waiting
deploy. The `deploy` job runs it again with `--strict` on re-run attempts,
whose `deploy-gate` result can be from an earlier attempt.
"""
import argparse
import os
import subprocess
import sys


def main_revision(remote, branch):
    result = subprocess.run(
        ['git', 'ls-remote', '--exit-code', remote, f'refs/heads/{branch}'],
        check=True, capture_output=True, encoding='utf-8')
    revisions = {line.split('\t', 1)[0] for line in result.stdout.splitlines() if line}
    if len(revisions) != 1:
        raise ValueError(f'Expected one revision for {branch}, got {sorted(revisions)}')
    return revisions.pop()


def append(variable, text):
    path = os.environ.get(variable)
    if path:
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(text + '\n')


def gate(revision, remote='origin', branch='main', strict=False):
    """Return True when `revision` is the tip of `branch` on `remote`.

    Also writes `current=true|false` to GITHUB_OUTPUT and, when stale, a notice
    (an error with `strict`) plus a step-summary line.
    """
    tip = main_revision(remote, branch)
    current = tip == revision
    append('GITHUB_OUTPUT', f'current={str(current).lower()}')
    if not current:
        message = (
            f'Not deploying {revision}: {branch} is now {tip}. That commit deploys from its own '
            f'run if it passes. To roll back, revert on {branch} instead of re-running an old run.')
        level = 'error' if strict else 'notice'
        print(f'::{level} title=Deploy skipped::{message}')
        append('GITHUB_STEP_SUMMARY', message)
    return current


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--revision', required=True, help='full commit SHA this run built')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--branch', default='main')
    parser.add_argument('--strict', action='store_true',
                        help='exit 1 instead of 0 when the revision is no longer the tip')
    args = parser.parse_args(argv)
    current = gate(args.revision, args.remote, args.branch, args.strict)
    return 0 if current or not args.strict else 1


if __name__ == '__main__':
    sys.exit(run())
