"""Thin PyMySQL layer. All SQL in the app is hand-written; this module only manages connections."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence

import pymysql
from flask import current_app, g


def _connect(cfg: dict) -> pymysql.connections.Connection:
    kwargs: dict[str, Any] = dict(
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        database=cfg["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=10,
        # Store and read every DATETIME as UTC; the API sends them with a "Z" suffix.
        init_command="SET time_zone = '+00:00'",
    )
    if cfg.get("DB_UNIX_SOCKET"):
        kwargs["unix_socket"] = cfg["DB_UNIX_SOCKET"]
    else:
        kwargs["host"] = cfg["DB_HOST"]
        kwargs["port"] = int(cfg["DB_PORT"])
    if cfg.get("DB_SSL_CA"):
        kwargs["ssl"] = {"ca": cfg["DB_SSL_CA"]}
    return pymysql.connect(**kwargs)


def get_db() -> pymysql.connections.Connection:
    if "db" not in g:
        g.db = _connect(current_app.config)
    return g.db


def close_db(_exc: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        try:
            db.rollback()
        finally:
            db.close()


def query(sql: str, args: Sequence[Any] | dict | None = None) -> list[dict]:
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def query_one(sql: str, args: Sequence[Any] | dict | None = None) -> dict | None:
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def execute(sql: str, args: Sequence[Any] | dict | None = None) -> tuple[int, int]:
    """Run a write statement inside the current transaction. Returns (lastrowid, rowcount)."""
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.lastrowid, cur.rowcount


def commit() -> None:
    get_db().commit()


@contextmanager
def transaction() -> Iterator[pymysql.connections.Connection]:
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def placeholders(n: int) -> str:
    return ", ".join(["%s"] * n)
