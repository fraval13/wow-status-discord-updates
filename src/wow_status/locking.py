"""Cross-platform advisory lock: one service/operator per database, one uploader per state."""
import os
from pathlib import Path


class FileLock:
    def __init__(self, path):
        self.path = Path(str(path) + '.lock')
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        try:
            # The size comes from a seek, not a read: Windows refuses to read a byte that
            # another handle has locked, which would fail here before reaching the lock
            # and leave this handle open (#26).
            if self.stream.seek(0, os.SEEK_END) == 0:
                self.stream.write(b'0')  # Windows locks a byte, so the file needs one.
                self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise OSError('Another process is using this database or companion state') from None
        return self

    def __exit__(self, *args):
        if self.stream:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
