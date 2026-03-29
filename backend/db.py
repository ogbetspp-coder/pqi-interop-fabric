"""Database connection pool. One module, imported everywhere."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

_pool: pool.SimpleConnectionPool | None = None


def get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        url = os.environ["DATABASE_URL"]
        _pool = pool.SimpleConnectionPool(1, 10, url)
    return _pool


def query(sql: str, params: tuple = ()) -> list[dict]:
    p = get_pool()
    conn = p.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    finally:
        p.putconn(conn)


def execute(sql: str, params: tuple = ()) -> None:
    p = get_pool()
    conn = p.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    finally:
        p.putconn(conn)


def execute_returning(sql: str, params: tuple = ()) -> dict | None:
    p = get_pool()
    conn = p.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        p.putconn(conn)
