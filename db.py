import os
import sqlite3
from datetime import date

from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "oskegdrop.db")


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                coins INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_bonus TEXT DEFAULT ''
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            )
        """)


def ensure_user(user_id: int, username: str = ""):
    with connect() as db:
        db.execute("""
            INSERT INTO users (user_id, username)
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET username = excluded.username
        """, (user_id, username or ""))


def get_user(user_id: int):
    with connect() as db:
        row = db.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        return dict(row) if row else None


def get_inventory(user_id: int):
    with connect() as db:
        rows = db.execute(
            "SELECT item_name FROM inventory WHERE user_id = ?",
            (user_id,)
        ).fetchall()

        return [row["item_name"] for row in rows]


def claim_daily_bonus(user_id: int):
    today = date.today().isoformat()

    with connect() as db:
        cursor = db.execute("""
            UPDATE users
            SET coins = coins + 100,
                last_bonus = ?
            WHERE user_id = ?
              AND last_bonus != ?
        """, (today, user_id, today))

        return cursor.rowcount == 1


def create_order(order_id: str, user_id: int, product_id: str):
    with connect() as db:
        db.execute("""
            INSERT INTO orders (order_id, user_id, product_id, status)
            VALUES (?, ?, ?, 'pending')
        """, (order_id, user_id, product_id))


def get_order(order_id: str):
    with connect() as db:
        row = db.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (order_id,)
        ).fetchone()

        return dict(row) if row else None


def fulfill_order(order_id: str, coins: int, items: list):
    with connect() as db:
        order = db.execute(
            "SELECT * FROM orders WHERE order_id = ?",
            (order_id,)
        ).fetchone()

        if not order or order["status"] != "pending":
            return False

        user_id = order["user_id"]

        cursor = db.execute("""
            UPDATE orders
            SET status = 'paid'
            WHERE order_id = ? AND status = 'pending'
        """, (order_id,))

        if cursor.rowcount != 1:
            return False

        db.execute("""
            UPDATE users
            SET coins = coins + ?
            WHERE user_id = ?
        """, (coins, user_id))

        for item in items:
            db.execute("""
                INSERT INTO inventory (user_id, item_name)
                VALUES (?, ?)
            """, (user_id, item))

        return True


def leaderboard(limit: int = 10):
    with connect() as db:
        rows = db.execute("""
            SELECT username, coins
            FROM users
            ORDER BY coins DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [dict(row) for row in rows]
