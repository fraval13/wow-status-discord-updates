"""One service or operator per database, one uploader per state file (#26)."""
import subprocess
import sys
import textwrap

import pytest

from wow_status.locking import FileLock

TRY_LOCK = textwrap.dedent('''
    import sys
    from wow_status.locking import FileLock
    try:
        with FileLock(sys.argv[1]):
            print('locked')
    except OSError as error:
        print(error)
''')


def try_from_another_process(path):
    result = subprocess.run([sys.executable, '-c', TRY_LOCK, str(path)], capture_output=True,
                            text=True, encoding='utf-8', timeout=60, check=True)
    return result.stdout.strip()


def test_a_second_holder_is_refused_until_the_first_releases(tmp_path):
    path = tmp_path / 'state' / 'service.sqlite3'  # The folder doesn't exist yet.
    with FileLock(path):
        with pytest.raises(OSError, match='Another process is using this database'):
            with FileLock(path):
                pass
        # A refused attempt leaves the holder's lock in place.
        with pytest.raises(OSError):
            FileLock(path).__enter__()
    # Windows locks the byte itself, so the file is only read once it is released.
    lock_file = tmp_path / 'state' / 'service.sqlite3.lock'
    assert lock_file.read_bytes() == b'0'
    with FileLock(path):  # Released on exit; the existing lock file is reused.
        pass
    assert lock_file.read_bytes() == b'0'


def test_the_lock_holds_against_another_process(tmp_path):
    path = tmp_path / 'service.sqlite3'
    with FileLock(path):
        assert try_from_another_process(path) == (
            'Another process is using this database or companion state')
    assert try_from_another_process(path) == 'locked'


def test_a_holder_that_raises_still_releases_the_lock(tmp_path):
    path = tmp_path / 'credentials.json'
    with pytest.raises(RuntimeError):
        with FileLock(path):
            raise RuntimeError('upload failed')
    with FileLock(path):
        pass
