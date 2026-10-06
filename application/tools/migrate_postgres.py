#!/usr/bin/env python3
"""Load the packaged synthetic SQLite fixture into PostgreSQL.

Usage:
  DATABASE_URL='postgresql://...' python tools/migrate_postgres.py

The loader is intentionally explicit and repeatable for the demo. It recreates
the business schema, then streams rows in foreign-key dependency order.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = ROOT / "data" / "northstar.sqlite"
SCHEMA_PATH = ROOT.parent / "database-reference" / "business-schema.sql"

TABLES = [
    "customers", "suppliers", "warehouses", "manufacturers", "products",
    "orders", "order_lines", "purchase_lines", "inventory_balances",
    "inventory_movements", "invoice_lines", "quote_lines", "service_events",
    "pricing_records", "direct_fulfillment",
]


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    if not SQLITE_PATH.exists():
        raise SystemExit(f"Missing fixture: {SQLITE_PATH}")

    with sqlite3.connect(SQLITE_PATH) as source, psycopg.connect(database_url) as target:
        source.row_factory = sqlite3.Row
        with target.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            statements = [part.strip() for part in SCHEMA_PATH.read_text().split(";") if part.strip()]
            tables = [part for part in statements if part.upper().startswith("CREATE TABLE")]
            indexes = [part for part in statements if part.upper().startswith("CREATE INDEX")]
            cur.execute(";".join(tables) + ";")
            for table in TABLES:
                columns = [row[1] for row in source.execute(f"PRAGMA table_info({table})")]
                placeholders = sql.SQL(",").join(sql.Placeholder() for _ in columns)
                insert = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table),
                    sql.SQL(",").join(sql.Identifier(c) for c in columns),
                    placeholders,
                )
                rows = source.execute(f"SELECT {','.join(columns)} FROM {table}")
                count = 0
                while batch := rows.fetchmany(2000):
                    cur.executemany(insert, [tuple(row) for row in batch])
                    count += len(batch)
                print(f"loaded {table}: {count:,} rows")
            cur.execute(";".join(indexes) + ";")
        target.commit()
    print("PostgreSQL migration complete")


if __name__ == "__main__":
    main()
