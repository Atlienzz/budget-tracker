import asyncio
import json
import os
import sys
import io
import uuid
from datetime import datetime

# ── Point to project root so database.py finds budget_tracker.db ─────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

import database as db
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

db.init_db()
server = Server("budget-tracker")

# One session ID per server process — groups all tool calls made in a single
# Claude Desktop conversation. Resets each time Claude Desktop reconnects.
SESSION_ID = str(uuid.uuid4())

# ── Helper: pandas DataFrame → plain list of dicts ───────────────────────────
def df_to_list(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _summarize_args(arguments: dict) -> str:
    """Compact, readable summary of tool arguments for the interaction log."""
    if not arguments:
        return "(no args)"
    return ", ".join(f"{k}={v}" for k, v in arguments.items())


# ── Tool Definitions ──────────────────────────────────────────────────────────
@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="get_bills",
            description="Get all bills with name, amount, due day, category, and recurring status",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_monthly_summary",
            description="Get a financial summary for a specific month: paid vs unpaid bills, dollar totals, and a list of what still needs to be paid",
            inputSchema={
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month number 1-12"},
                    "year":  {"type": "integer", "description": "4-digit year e.g. 2026"}
                },
                "required": ["month", "year"]
            }
        ),
        types.Tool(
            name="get_overdue_bills",
            description="Get bills not yet paid this month where the due date has already passed, including days overdue",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_budget_status",
            description="Get budget limits vs actual spending by category for a given month",
            inputSchema={
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month number 1-12"},
                    "year":  {"type": "integer", "description": "4-digit year e.g. 2026"}
                },
                "required": ["month", "year"]
            }
        ),
        types.Tool(
            name="get_recent_pipeline_runs",
            description="Get the last 5 email pipeline run logs — when it ran, how many emails processed, how many payments recorded",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="run_email_pipeline",
            description="Fetch new emails from Gmail and automatically record any bill payments found",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="get_mcp_stats",
            description="Get usage statistics for this MCP server — how many times each tool has been called, across how many sessions, and recent activity",
            inputSchema={"type": "object", "properties": {}}
        ),
    ]


# ── Internal tool dispatch (no logging here — logging happens in call_tool) ───
async def _dispatch_tool(name: str, arguments: dict):

    # ── get_bills ─────────────────────────────────────────────────────────────
    if name == "get_bills":
        bills = df_to_list(db.get_bills())
        return [types.TextContent(type="text", text=json.dumps(bills, indent=2))]

    # ── get_monthly_summary ───────────────────────────────────────────────────
    elif name == "get_monthly_summary":
        month = arguments["month"]
        year  = arguments["year"]

        bills_df    = db.get_bills()
        payments_df = db.get_payments_df(month, year)
        paid_ids    = set(payments_df["bill_id"].tolist()) if not payments_df.empty else set()

        total_bills  = len(bills_df)
        paid_count   = sum(1 for bid in bills_df["id"] if bid in paid_ids)
        unpaid_count = total_bills - paid_count
        total_owed   = bills_df["amount"].sum()
        total_paid   = float(payments_df["amount"].sum()) if not payments_df.empty else 0.0

        unpaid_bills = (
            bills_df[~bills_df["id"].isin(paid_ids)][["name", "amount", "due_day", "category"]]
            .to_dict("records")
        )

        summary = {
            "month": month,
            "year":  year,
            "total_bills":               total_bills,
            "paid_count":                paid_count,
            "unpaid_count":              unpaid_count,
            "total_monthly_obligations": round(float(total_owed), 2),
            "total_paid_so_far":         round(total_paid, 2),
            "remaining_to_pay":          round(float(total_owed) - total_paid, 2),
            "unpaid_bills":              unpaid_bills,
        }
        return [types.TextContent(type="text", text=json.dumps(summary, indent=2))]

    # ── get_overdue_bills ─────────────────────────────────────────────────────
    elif name == "get_overdue_bills":
        now   = datetime.now()
        today = now.day
        month = now.month
        year  = now.year

        bills_df    = db.get_bills()
        payments_df = db.get_payments_df(month, year)
        paid_ids    = set(payments_df["bill_id"].tolist()) if not payments_df.empty else set()

        overdue = [
            {
                "name":         bill["name"],
                "amount":       bill["amount"],
                "due_day":      int(bill["due_day"]),
                "category":     bill["category"],
                "days_overdue": today - int(bill["due_day"]),
            }
            for _, bill in bills_df.iterrows()
            if bill["id"] not in paid_ids and int(bill["due_day"]) < today
        ]
        overdue.sort(key=lambda x: x["days_overdue"], reverse=True)

        result = {
            "as_of":         now.strftime("%Y-%m-%d"),
            "overdue_count": len(overdue),
            "overdue_bills": overdue,
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # ── get_budget_status ─────────────────────────────────────────────────────
    elif name == "get_budget_status":
        month = arguments["month"]
        year  = arguments["year"]

        budgets_df  = db.get_budgets_df(month, year)
        payments_df = db.get_payments_df(month, year)

        if budgets_df.empty:
            return [types.TextContent(
                type="text",
                text=json.dumps({"message": f"No budgets set for {month}/{year}"})
            )]

        spending = (
            payments_df.groupby("category")["amount"].sum().to_dict()
            if not payments_df.empty else {}
        )

        status = [
            {
                "category":  row["category"],
                "budget":    round(row["monthly_limit"], 2),
                "spent":     round(float(spending.get(row["category"], 0.0)), 2),
                "remaining": round(row["monthly_limit"] - float(spending.get(row["category"], 0.0)), 2),
                "status":    "Over" if spending.get(row["category"], 0.0) > row["monthly_limit"] else "Under",
            }
            for _, row in budgets_df.iterrows()
        ]
        return [types.TextContent(type="text", text=json.dumps(status, indent=2))]

    # ── get_recent_pipeline_runs ──────────────────────────────────────────────
    elif name == "get_recent_pipeline_runs":
        logs = df_to_list(db.get_pipeline_logs(limit=5))
        for log in logs:
            log.pop("log_text", None)
        return [types.TextContent(type="text", text=json.dumps(logs, indent=2))]

    # ── run_email_pipeline ────────────────────────────────────────────────────
    elif name == "run_email_pipeline":
        from bill_pipeline import run_gmail_pipeline

        output_capture = io.StringIO()
        old_stdout     = sys.stdout
        sys.stdout     = output_capture

        try:
            run_gmail_pipeline()
        finally:
            sys.stdout = old_stdout

        output   = output_capture.getvalue()
        total    = output.count("📧 Processing:")
        recorded = output.count("marked as paid")
        skipped  = output.count("skipping") + output.count("already paid")

        db.save_pipeline_log(total, recorded, skipped, output, source="mcp")

        summary = (
            f"Pipeline complete.\n"
            f"  Emails processed : {total}\n"
            f"  Payments recorded: {recorded}\n"
            f"  Skipped          : {skipped}\n\n"
            f"Full output:\n{output}"
        )
        return [types.TextContent(type="text", text=summary)]

    # ── get_mcp_stats ─────────────────────────────────────────────────────────
    elif name == "get_mcp_stats":
        stats = db.get_mcp_stats()
        stats["current_session_id"] = SESSION_ID
        return [types.TextContent(type="text", text=json.dumps(stats, indent=2))]

    else:
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Tool Handlers (with interaction logging) ──────────────────────────────────
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    result        = await _dispatch_tool(name, arguments)
    response_text = result[0].text if result else ""
    db.log_mcp_interaction(
        session_id     = SESSION_ID,
        tool_name      = name,
        input_summary  = _summarize_args(arguments),
        response_chars = len(response_text),
    )
    return result


# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options()
        )

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
