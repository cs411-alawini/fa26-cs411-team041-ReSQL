"""Create the schema in a LOCAL database from the files in ../database (used by tests and `flask init-db`)."""
from __future__ import annotations

import os
import re

DATABASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "database"))
SCHEMA_FILES = ("schema.sql", "triggers.sql", "views.sql", "seed_lookups.sql")


def split_sql(text: str) -> list[str]:
    """Split a .sql file into statements, honouring the mysql client's DELIMITER command."""
    statements, buf, delimiter = [], [], ";"
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"(?i)^DELIMITER\s+(\S+)\s*$", stripped)
        if m:
            delimiter = m.group(1)
            continue
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        buf.append(line)
        if stripped.endswith(delimiter):
            stmt = "\n".join(buf).rstrip()
            stmt = stmt[: -len(delimiter)].strip()
            if stmt:
                statements.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def run_sql_file(conn, path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        statements = split_sql(fh.read())
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def drop_all(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("SELECT table_name AS t, table_type AS k FROM information_schema.tables WHERE table_schema = DATABASE()")
        for row in cur.fetchall():
            name = row["t"] if isinstance(row, dict) else row[0]
            kind = row["k"] if isinstance(row, dict) else row[1]
            cur.execute(f"DROP {'VIEW' if kind == 'VIEW' else 'TABLE'} IF EXISTS `{name}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()


def apply_schema(conn, database_dir: str = DATABASE_DIR) -> None:
    for name in SCHEMA_FILES:
        run_sql_file(conn, os.path.join(database_dir, name))
