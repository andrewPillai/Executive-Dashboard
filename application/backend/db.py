"""Small SQLite/PostgreSQL compatibility layer for the demo read models."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from collections.abc import Mapping
from pathlib import Path


class Row(Mapping):
    def __init__(self, values, columns):
        self._values = tuple(values)
        self._columns = tuple(columns)
        self._mapping = dict(zip(self._columns, self._values))

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, int) else self._mapping[key]

    def __iter__(self):
        return iter(self._mapping)

    def __len__(self):
        return len(self._values)


class Cursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def _row(self, values):
        if values is None:
            return None
        return Row(values, [d.name if hasattr(d, 'name') else d[0] for d in self._cursor.description])

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(x) for x in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, args=()):
        cursor = self._connection.cursor()
        cursor.execute(sql.replace('?', '%s'), tuple(args))
        return Cursor(cursor)

    def close(self):
        self._connection.close()


@contextmanager
def open_business(data_dir: Path):
    url = os.getenv('DATABASE_URL')
    if url:
        import psycopg
        raw = psycopg.connect(url, connect_timeout=8)
        db = Connection(raw)
        try:
            yield db
        finally:
            db.close()
    else:
        raw = sqlite3.connect((data_dir / 'northstar.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
        raw.row_factory = sqlite3.Row
        try:
            yield raw
        finally:
            raw.close()
