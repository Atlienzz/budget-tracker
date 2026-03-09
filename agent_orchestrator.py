"""
agent_orchestrator.py — Email routing supervisor agent.

Reads each incoming email and decides which pipeline path to take.
This is the "planner decides, specialists execute" pattern used in
every serious multi-agent system.

Routes:
  skip          — Marketing, shipping, reminders, account alerts. No AI needed.
  standard      — Confirmed payment. Run the full parse → match → record pipeline.
  force_review  — Ambiguous. Might be a payment but unclear. Route to human review queue.
  dispute       — Payment failure, incorrect charge, or refund request. Flag for attention.

Adding a new route later means adding one enum value here and one elif in bill_pipeline.py.
No downstream agents need to change.
"""

import anthropic
from dotenv import load_dotenv
import os
import tracer

load_dotenv(override=True)
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ROUTE_TOOL = {
    "name": "route_email",
    "description": "Route this email to the correct processing path",
    "input_schema": {
        "type": "object",
        "properties": {
            "route": {
                "type": "string",
                "enum": ["skip", "standard", "force_review", "dispute"],
                "description": (
                    "skip: Not a payment-related email. Marketing, shipping, reminders, "
                    "account summaries, login alerts, surveys.\n"
                    "standard: Email confirms a payment was received or processed. "
                    "Run the full pipeline.\n"
                    "force_review: Might be a payment but unclear — ambiguous language, "
                    "receipt from an unusual source, service company with order-like wording. "
                    "Send to human review queue.\n"
                    "dispute: Payment failed, payment declined, incorrect charge, "
                    "unauthorized transaction, or refund request."
                )
            },
            "reason": {
                "type": "string",
                "description": "One short phrase explaining the routing decision. e.g. 'Verizon payment confirmation' or 'promotional email from Amazon'"
            }
        },
        "required": ["route", "reason"]
    }
}

SYSTEM_PROMPT = """You are an email routing agent for a personal bill payment tracker.

Your only job is to read an email and decide which processing path it belongs to.

ROUTING RULES:

route = "standard" — ONLY if the email explicitly confirms that a payment was:
  - Received by the company
  - Processed successfully
  - Posted to an account
  Examples: "Your payment of $142.00 has been received", "Payment confirmation", "Thank you for your payment"
  NOT: upcoming payments, scheduled payments, payment reminders, minimum due alerts

route = "dispute" — If the email describes:
  - A payment that failed or was declined
  - An incorrect or unauthorized charge
  - A refund request or refund confirmation
  Examples: "Your payment could not be processed", "Dispute a charge", "Refund issued"

route = "force_review" — If the email might be a payment but you're not certain:
  - A service company mentioning a dollar amount without clear confirmation language
  - Receipts that could be purchases or bill payments
  - Ambiguous subject lines with financial content

route = "skip" — Everything else:
  - Marketing, promotions, sales
  - Shipping and order updates
  - Account activity summaries
  - Login alerts, security notices
  - Payment reminders or upcoming due dates
  - Statements or usage reports

Call route_email with your decision and a brief reason phrase."""


def route_email(subject: str, body_preview: str, pipeline_run_id: str = "manual") -> tuple[str, str]:
    """
    Route an email to the correct processing path.

    Args:
        subject:         Email subject line
        body_preview:    First 500 chars of email body (enough context, not the whole email)
        pipeline_run_id: Links this trace to the current pipeline run

    Returns:
        (route, reason) — e.g. ("standard", "Verizon payment confirmation")
        Falls back to ("skip", "routing error") if the agent fails to respond.
    """
    email_text = f"Subject: {subject}\n\n{body_preview}"

    response, trace = tracer.trace_call(
        client,
        pipeline_run_id=pipeline_run_id,
        agent_name="orchestrator",
        input_summary=f"subject={subject[:80]}",
        model="claude-haiku-4-5",
        max_tokens=128,
        tools=[ROUTE_TOOL],
        tool_choice={"type": "any"},
        messages=[
            {"role": "user", "content": email_text}
        ],
        system=SYSTEM_PROMPT,
    )

    for block in response.content:
        if block.type == "tool_use":
            route  = block.input.get("route", "skip")
            reason = block.input.get("reason", "")
            trace.result = f"route={route} reason={reason}"
            tracer.save_trace_result(trace)
            return route, reason

    # Fallback — treat as skip if agent didn't respond with a tool call
    trace.result = "route=skip reason=routing_error"
    tracer.save_trace_result(trace)
    return "skip", "routing error"
