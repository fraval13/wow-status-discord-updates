"""Generous resource budgets, independent of claims about gameplay speed."""
import math


class Limited(Exception):
    def __init__(self, retry_after):
        self.retry_after = max(1, math.ceil(retry_after))
        super().__init__('Resource limit reached; retained data can be retried')


# These are resource limits, not levelling-speed or credibility thresholds.
UPLOADS_PER_MINUTE = 600
PRIVACY_PER_MINUTE = 120
ENROLLMENTS_PER_IP_HOUR = 30
ENROLLMENTS_PER_GROUP_DAY = 1000
AUTH_FAILURES_PER_IP_MINUTE = 120
NEW_CHARACTERS_PER_OWNER_DAY = 256
NEW_CHARACTERS_PER_GROUP_DAY = 2000
NEW_EVENTS_PER_OWNER_DAY = 100_000
NEW_EVENTS_PER_GROUP_DAY = 1_000_000
NEW_BYTES_PER_OWNER_DAY = 200 * 1024 * 1024
NEW_BYTES_PER_GROUP_DAY = 2 * 1024 * 1024 * 1024
GROUP_POST_SECONDS = 3
CHARACTER_POST_SECONDS = 10


def charge(db, entries, now):
    """Caller owns the transaction. Check all budgets before incrementing any.

    Entries are (scope, limit, window_seconds, amount). Fixed UTC resource windows
    are unrelated to the Oslo dates used for gameplay records and recaps.
    """
    updates = []
    for scope, limit, seconds, amount in entries:
        if amount <= 0:
            continue
        bucket = int(now // seconds) * seconds
        row = db.execute('SELECT amount FROM resource_usage WHERE scope=? AND bucket=?',
                         (scope, bucket)).fetchone()
        used = row['amount'] if row else 0
        if used + amount > limit:
            raise Limited(bucket + seconds - now)
        updates.append((scope, bucket, amount))
    db.execute('DELETE FROM resource_usage WHERE bucket<?', (now - 172800,))
    for scope, bucket, amount in updates:
        db.execute('''INSERT INTO resource_usage VALUES(?,?,?)
            ON CONFLICT(scope,bucket) DO UPDATE SET amount=amount+excluded.amount''',
            (scope, bucket, amount))
