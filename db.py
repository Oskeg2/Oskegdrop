import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone

import config

USE_PG = bool(config.DATABASE_URL)

if USE_PG:
    import psycopg2
    #from psycopg.rows import dict_row


class Conn:
    """Тонкая обёртка: один и тот же SQL работает и в SQLite, и в Postgres."""

    def __init__(self, raw):
        self.raw = raw

    def _prep(self, sql):
        return sql.replace("?", "%s") if USE_PG else sql

    def run(self, sql, params=()):
        cur = self.raw.cursor()
        cur.execute(self._prep(sql), params)
        return cur.rowcount

    def one(self, sql, params=()):
        row = self.raw.execute(self._prep(sql), params).fetchone()
        return dict(row) if row else None

    def all(self, sql, params=()):
        rows = self.raw.execute(self._prep(sql), params).fetchall()
        return [dict(r) for r in rows]


@contextmanager
def tx():
    if USE_PG:
        raw = psycopg2.connect(config.DATABASE_URL)
    else:
        raw = sqlite3.connect(config.DATABASE_PATH, timeout=10)
        raw.row_factory = sqlite3.Row
    try:
        yield Conn(raw)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


PK = "BIGSERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT DEFAULT '', "
    "stars BIGINT NOT NULL DEFAULT 0, created_at BIGINT NOT NULL DEFAULT 0, "
    "last_bonus TEXT NOT NULL DEFAULT '')",
    f"CREATE TABLE IF NOT EXISTS inventory (id {PK}, user_id BIGINT NOT NULL, gift_key TEXT NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'owned', created_at BIGINT NOT NULL DEFAULT 0)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory (user_id)",
    "CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, "
    "amount BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', "
    "charge_id TEXT DEFAULT '', created_at BIGINT NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS stats (user_id BIGINT NOT NULL, stat TEXT NOT NULL, "
    "value BIGINT NOT NULL DEFAULT 0, PRIMARY KEY (user_id, stat))",
    "CREATE TABLE IF NOT EXISTS achievements (user_id BIGINT NOT NULL, key TEXT NOT NULL, "
    "unlocked_at BIGINT NOT NULL DEFAULT 0, PRIMARY KEY (user_id, key))",
    f"CREATE TABLE IF NOT EXISTS mines_games (id {PK}, user_id BIGINT NOT NULL, bet BIGINT NOT NULL, "
    "mines INTEGER NOT NULL, mine_cells TEXT NOT NULL, revealed TEXT NOT NULL DEFAULT '[]', "
    "status TEXT NOT NULL DEFAULT 'active', created_at BIGINT NOT NULL DEFAULT 0)",
    f"CREATE TABLE IF NOT EXISTS crash_games (id {PK}, user_id BIGINT NOT NULL, bet BIGINT NOT NULL, "
    "crash_point DOUBLE PRECISION NOT NULL, auto_cashout DOUBLE PRECISION, "
    "started_at DOUBLE PRECISION NOT NULL, status TEXT NOT NULL DEFAULT 'active', "
    "payout BIGINT NOT NULL DEFAULT 0, final_mult DOUBLE PRECISION)",
    f"CREATE TABLE IF NOT EXISTS withdrawals (id {PK}, user_id BIGINT NOT NULL, item_id BIGINT NOT NULL, "
    "gift_key TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at BIGINT NOT NULL DEFAULT 0)",
    f"CREATE TABLE IF NOT EXISTS ledger (id {PK}, user_id BIGINT NOT NULL, delta BIGINT NOT NULL, "
    "reason TEXT NOT NULL DEFAULT '', created_at BIGINT NOT NULL DEFAULT 0)",
]


def init_db():
    with tx() as c:
        for statement in SCHEMA:
            c.run(statement)


def now() -> int:
    return int(time.time())


def ensure_user(user_id: int, username: str = ""):
    with tx() as c:
        c.run(
            "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET username = excluded.username",
            (user_id, username or "", now()),
        )


def get_user(user_id: int):
    with tx() as c:
        return c.one("SELECT * FROM users WHERE user_id = ?", (user_id,))


def add_stars(c: Conn, user_id: int, delta: int, reason: str):
    c.run("UPDATE users SET stars = stars + ? WHERE user_id = ?", (delta, user_id))
    c.run(
        "INSERT INTO ledger (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
        (user_id, delta, reason, now()),
    )


def spend(c: Conn, user_id: int, amount: int, reason: str) -> bool:
    changed = c.run(
        "UPDATE users SET stars = stars - ? WHERE user_id = ? AND stars >= ?",
        (amount, user_id, amount),
    )
    if changed != 1:
        return False
    c.run(
        "INSERT INTO ledger (user_id, delta, reason, created_at) VALUES (?, ?, ?, ?)",
        (user_id, -amount, reason, now()),
    )
    return True


def balance(c: Conn, user_id: int) -> int:
    return c.one("SELECT stars FROM users WHERE user_id = ?", (user_id,))["stars"]


def bump(c: Conn, user_id: int, stat: str, n: int = 1):
    c.run(
        "INSERT INTO stats (user_id, stat, value) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, stat) DO UPDATE SET value = stats.value + excluded.value",
        (user_id, stat, n),
    )


def set_max(c: Conn, user_id: int, stat: str, value: int):
    c.run(
        "INSERT INTO stats (user_id, stat, value) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, stat) DO UPDATE SET value = "
        "CASE WHEN excluded.value > stats.value THEN excluded.value ELSE stats.value END",
        (user_id, stat, value),
    )


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
