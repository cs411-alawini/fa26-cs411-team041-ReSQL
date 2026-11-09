"""Small helpers shared by the test modules."""


def scalar(db, sql: str, args=None):
    """First column of the first row, seeing everything the app has committed."""
    db.commit()
    with db.cursor() as cur:
        cur.execute(sql, args)
        row = cur.fetchone()
    return None if row is None else next(iter(row.values()))


def execute(db, sql: str, args=None) -> None:
    with db.cursor() as cur:
        cur.execute(sql, args)
    db.commit()
