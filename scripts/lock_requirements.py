"""Regenerate requirements.txt, the exact packages the server installs (issue #27).

The deployment receiver installs requirements.txt with pip's --require-hashes and
wheels only, then builds the project from the release without contacting an index.
So the lock holds every runtime dependency from pyproject.toml plus the build
backend from its [build-system] table, each pinned to one version and the SHA-256 of
every file published for it. It is universal: it resolves for each Python from
requires-python up and for every platform, so CI on Windows can install it too.

Needs uv (https://docs.astral.sh/uv/). Existing pins are kept where they still
satisfy pyproject.toml; pass --upgrade to move everything to the newest versions.
tests/test_requirements_lock.py checks the result against pyproject.toml.
"""
import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'requirements.txt'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--upgrade', action='store_true', help='move every pin to the newest allowed version')
    args = parser.parse_args(argv)
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
    oldest = re.fullmatch(r'>=\s*(3\.\d+)', project['project']['requires-python']).group(1)
    build = ''.join(requirement + '\n' for requirement in project['build-system']['requires'])
    # Wheels only, as the receiver installs them: a version without wheels is never locked.
    command = ['uv', 'pip', 'compile', 'pyproject.toml', '-', '--universal', '--python-version', oldest,
               '--only-binary', ':all:', '--generate-hashes', '--no-annotate', '--quiet', '--output-file', LOCK.name,
               '--custom-compile-command', 'python scripts/lock_requirements.py',
               *(['--upgrade'] if args.upgrade else [])]
    # The build backend arrives on stdin, so it is locked without being a runtime dependency.
    return subprocess.run(command, cwd=ROOT, input=build, encoding='utf-8').returncode


if __name__ == '__main__':
    sys.exit(main())
