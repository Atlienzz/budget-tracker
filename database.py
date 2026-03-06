import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "budget_tracker.db"

CATEGORIES = [
    "Housing",
    "Utilities",
    "Insurance",
    "Transportation",
    "Food & Groceries",
    "Subscriptions",
    "Healthcare",
    "Entertainment",
    "Savings",
    "Other",
]


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bills (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                amount      REAL    NOT NULL,
                due_day     INTEGER NOT NULL,
                category    TEXT    NOT NULL,
                is_recurring INTEGER DEFAULT 1,
                notes       TEXT    DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                bill_id   INTEGER NOT NULL,
                amount    REAL    NOT NULL,
                paid_date TEXT    NOT NULL,
                month     INTEGER NOT NULL,
                year      INTEGER NOT NULL,
                notes     TEXT    DEFAULT '',     
                FOREIGN KEY (bill_id) REFERENCES bills(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                category      TEXT    NOT NULL,
                monthly_limit REAL    NOT NULL,
                month         INTEGER NOT NULL,
                year          INTEGER NOT NULL,
                UNIQUE(category, month, year)
            )
        """)
        conn.commit()


# ── Bills ──────────────────────────────────────────────────────────────────────

def add_bill(name, amount, due_day, category, is_recurring=True, notes=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO bills (name, amount, due_day, category, is_recurring, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (name, amount, due_day, category, int(is_recurring), notes),
        )
        conn.commit()


def get_bills():
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM bills ORDER BY due_day", conn)


def update_bill(bill_id, name, amount, due_day, category, is_recurring, notes):
    with get_connection() as conn:
        conn.execute(
            "UPDATE bills SET name=?, amount=?, due_day=?, category=?, is_recurring=?, notes=? WHERE id=?",
            (name, amount, due_day, category, int(is_recurring), notes, bill_id),
        )
        conn.commit()


def delete_bill(bill_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM payments WHERE bill_id=?", (bill_id,))
        conn.execute("DELETE FROM bills WHERE id=?", (bill_id,))
        conn.commit()


# ── Payments ───────────────────────────────────────────────────────────────────

def mark_paid(bill_id, amount, month, year, notes=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO payments (bill_id, amount, paid_date, month, year, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (bill_id, amount, datetime.now().strftime("%Y-%m-%d"), month, year, notes),
        )
        conn.commit()



def unmark_paid(bill_id, month, year):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM payments WHERE bill_id=? AND month=? AND year=?",
            (bill_id, month, year),
        )
        conn.commit()


def is_paid(bill_id, month, year):
    with get_connection() as conn:
        result = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE bill_id=? AND month=? AND year=?",
            (bill_id, month, year),
        ).fetchone()
    return result[0] > 0


def get_payments_df(month, year):
    with get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT p.*, b.name, b.category
            FROM payments p
            JOIN bills b ON p.bill_id = b.id
            WHERE p.month=? AND p.year=?
            """,
            conn,
            params=(month, year),
        )


# ── Budgets ────────────────────────────────────────────────────────────────────

def set_budget(category, monthly_limit, month, year):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO budgets (category, monthly_limit, month, year) VALUES (?, ?, ?, ?)
            ON CONFLICT(category, month, year) DO UPDATE SET monthly_limit=excluded.monthly_limit
            """,
            (category, monthly_limit, month, year),
        )
        conn.commit()


def get_budgets_df(month, year):
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM budgets WHERE month=? AND year=?",
            conn,
            params=(month, year),
        )
