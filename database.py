import sqlite3
import json
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_logs (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp  TEXT NOT NULL,
                total_emails   INTEGER,
                recorded_count INTEGER,
                skipped_count  INTEGER,
                log_text       TEXT
            )
        """)

        try:
            conn.execute("ALTER TABLE pipeline_logs ADD COLUMN source TEXT DEFAULT 'manual'")
        except Exception:
            pass  # column already exists

        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_emails (
                email_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_queue (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                email_subject       TEXT    DEFAULT '',
                company_name        TEXT    NOT NULL,
                suggested_bill_id   INTEGER,
                suggested_bill_name TEXT    DEFAULT '',
                amount              REAL,
                email_date          TEXT    DEFAULT '',
                pipeline_run_id     TEXT    DEFAULT '',
                status              TEXT    DEFAULT 'pending',
                resolved_bill_id    INTEGER,
                created_at          TEXT    NOT NULL,
                resolved_at         TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_traces (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline_run_id    TEXT    NOT NULL,
                agent_name         TEXT    NOT NULL,
                model              TEXT    NOT NULL,
                turn               INTEGER DEFAULT 1,
                input_tokens       INTEGER DEFAULT 0,
                output_tokens      INTEGER DEFAULT 0,
                cache_read_tokens  INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                cost_usd           REAL    DEFAULT 0.0,
                latency_ms         INTEGER DEFAULT 0,
                tool_calls         TEXT    DEFAULT '[]',
                input_summary      TEXT    DEFAULT '',
                result             TEXT    DEFAULT '',
                timestamp          TEXT    NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS mcp_interactions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id     TEXT    NOT NULL,
                tool_name      TEXT    NOT NULL,
                input_summary  TEXT    DEFAULT '',
                response_chars INTEGER DEFAULT 0,
                timestamp      TEXT    NOT NULL
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
    
# ── Pipeline Logs & Email ID (late DB additions) ────────────────────────────────────────────────────────────────────
    
def save_pipeline_log(total_emails, recorded_count, skipped_count, log_text, source="manual"):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO pipeline_logs (run_timestamp, total_emails, recorded_count, skipped_count, log_text, source) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total_emails, recorded_count, skipped_count, log_text, source),
        )
        conn.commit()

def get_pipeline_logs(limit=10):
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM pipeline_logs ORDER BY run_timestamp DESC LIMIT ?",
            conn, params=(limit,)
        )

def get_last_pipeline_run_date():
    with get_connection() as conn:
        result = conn.execute(
            "SELECT run_timestamp FROM pipeline_logs ORDER BY run_timestamp DESC LIMIT 1"
        ).fetchone()
    if result:
        return datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
    return None

def is_email_processed(email_id):
    with get_connection() as conn:
        result = conn.execute(
            "SELECT COUNT(*) FROM processed_emails WHERE email_id=?", (email_id,)
        ).fetchone()
    return result[0] > 0

def mark_email_processed(email_id):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_emails (email_id, processed_at) VALUES (?, ?)",
            (email_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()


# ── Agent Traces ────────────────────────────────────────────────────────────────

def save_agent_trace(trace):
    """Save an AgentTrace dataclass to the database."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO agent_traces
                (pipeline_run_id, agent_name, model, turn,
                 input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                 cost_usd, latency_ms, tool_calls, input_summary, result, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.pipeline_run_id,
                trace.agent_name,
                trace.model,
                trace.turn,
                trace.input_tokens,
                trace.output_tokens,
                trace.cache_read_tokens,
                trace.cache_write_tokens,
                trace.cost_usd,
                trace.latency_ms,
                json.dumps(trace.tool_calls),
                trace.input_summary,
                trace.result,
                trace.timestamp,
            ),
        )
        conn.commit()


def get_traces_for_run(pipeline_run_id: str):
    """Return all agent traces for a specific pipeline run."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM agent_traces WHERE pipeline_run_id=? ORDER BY id",
            conn,
            params=(pipeline_run_id,),
        )


# ── Review Queue ────────────────────────────────────────────────────────────────

def add_to_review_queue(email_subject, company_name, suggested_bill_id,
                        suggested_bill_name, amount, email_date, pipeline_run_id):
    """Park a LOW-confidence match for human review."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO review_queue
                (email_subject, company_name, suggested_bill_id, suggested_bill_name,
                 amount, email_date, pipeline_run_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (email_subject, company_name, suggested_bill_id, suggested_bill_name,
             amount, email_date, pipeline_run_id,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()


def get_pending_reviews():
    """Return all pending review queue items."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM review_queue WHERE status='pending' ORDER BY created_at DESC",
            conn,
        )


def get_pending_review_count():
    """Return count of pending items — used for dashboard badge."""
    with get_connection() as conn:
        result = conn.execute(
            "SELECT COUNT(*) FROM review_queue WHERE status='pending'"
        ).fetchone()
    return result[0]


def resolve_review(review_id, status, resolved_bill_id=None):
    """Mark a review item as approved, corrected, or rejected."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE review_queue
            SET status=?, resolved_bill_id=?, resolved_at=?
            WHERE id=?
            """,
            (status, resolved_bill_id,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), review_id),
        )
        conn.commit()


def update_trace_result(trace):
    """Update the result field on an already-saved trace row."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE agent_traces SET result=? WHERE pipeline_run_id=? AND agent_name=? AND turn=?",
            (trace.result, trace.pipeline_run_id, trace.agent_name, trace.turn),
        )
        conn.commit()


def get_recent_pipeline_run_ids(limit: int = 20):
    """Return distinct pipeline_run_ids ordered by most recent first."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT pipeline_run_id, MIN(timestamp) as started_at, COUNT(*) as call_count,
                   SUM(cost_usd) as total_cost, SUM(input_tokens + output_tokens) as total_tokens
            FROM agent_traces
            GROUP BY pipeline_run_id
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows


# ── MCP Interactions ─────────────────────────────────────────────────────────

def log_mcp_interaction(session_id: str, tool_name: str,
                        input_summary: str = "", response_chars: int = 0):
    """Log a single MCP tool invocation from Claude Desktop."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO mcp_interactions
                (session_id, tool_name, input_summary, response_chars, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, tool_name, input_summary, response_chars,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()


def get_mcp_interactions(limit: int = 100):
    """Return recent MCP tool invocations."""
    with get_connection() as conn:
        return pd.read_sql_query(
            "SELECT * FROM mcp_interactions ORDER BY timestamp DESC LIMIT ?",
            conn, params=(limit,)
        )


def get_mcp_stats() -> dict:
    """Return aggregate MCP usage stats for the Cost Dashboard."""
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM mcp_interactions"
        ).fetchone()[0]

        sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM mcp_interactions"
        ).fetchone()[0]

        recent_7d = conn.execute(
            "SELECT COUNT(*) FROM mcp_interactions WHERE timestamp >= date('now', '-7 days')"
        ).fetchone()[0]

        by_tool = pd.read_sql_query(
            """
            SELECT tool_name, COUNT(*) as call_count
            FROM mcp_interactions
            GROUP BY tool_name
            ORDER BY call_count DESC
            """,
            conn
        )

    return {
        "total_calls":      total,
        "total_sessions":   sessions,
        "calls_last_7_days": recent_7d,
        "by_tool":          by_tool.to_dict("records") if not by_tool.empty else [],
    }


def get_agent_model_breakdown():
    """Return per-model cost and call counts across all pipeline runs."""
    with get_connection() as conn:
        return pd.read_sql_query(
            """
            SELECT model,
                   COUNT(*) as calls,
                   SUM(input_tokens + output_tokens) as total_tokens,
                   SUM(cost_usd) as total_cost,
                   AVG(latency_ms) as avg_latency_ms
            FROM agent_traces
            GROUP BY model
            ORDER BY total_cost DESC
            """,
            conn
        )
