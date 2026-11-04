"""Decide whether a pipeline run may deploy: only while its commit is the tip of main.

The "Checks and addon packages" workflow's `deploy-gate` job runs this before
`deploy` joins the production concurrency group, so an older run never queues
there and cancels a newer run's waiting deploy (issue #15).
"""
import argparse
import os
import subprocess
import sys


def main_revision(remote, branch):
    ref = f'refs/heads/{branch}'
    # git's stderr is left on the console so a failure (auth, network) says why.
    result = subprocess.run(['git', 'ls-remote', '--exit-code', remote, ref],
                            check=True, stdout=subprocess.PIPE, encoding='utf-8')
    # ls-remote matches the pattern against the end of each ref, so a branch such as
    # `x/refs/heads/main` is listed too. Only the exact ref counts.
    revisions = [line.split('\t')[0] for line in result.stdout.splitlines()
                 if line.split('\t')[-1] == ref]
    if len(revisions) != 1:
        raise ValueError(f'Expected one revision for {ref}, got {revisions}')
    return revisions[0]


def append(variable, text):
    path = os.environ.get(variable)
    if path:
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(text + '\n')


def gate(revision, remote='origin', branch='main'):
    """Return True when `revision` is the tip of `branch` on `remote`.

    Also writes `current=true|false` to GITHUB_OUTPUT and, when stale, a notice
    plus a step-summary line.
    """
    tip = main_revision(remote, branch)
    current = tip == revision
    append('GITHUB_OUTPUT', f'current={str(current).lower()}')
    if not current:
        message = (
            f'Not deploying {revision}: {branch} is now {tip}. That commit deploys from its own '
            f'run if it passes. To roll back, revert on {branch} instead of re-running an old run.')
        print(f'::notice title=Deploy skipped::{message}')
        append('GITHUB_STEP_SUMMARY', message)
    return current


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--revision', required=True, help='full commit SHA this run built')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--branch', default='main')
    args = parser.parse_args(argv)
    gate(args.revision, args.remote, args.branch)
    return 0


if __name__ == '__main__':
    sys.exit(run())
