import anthropic
from dotenv import load_dotenv
import os
import tracer
import model_router

load_dotenv(override=True)
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TOOL = {
    "name": "extract_payment_info",
    "description": "Extract payment confirmation details from an email",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_payment_confirmation": {
                "type": "boolean",
                "description": "True only if this email confirms a payment was received or processed"
            },
            "company": {
                "type": "string",
                "description": "The company that received the payment"
            },
            "amount": {
                "type": "number",
                "description": "The payment amount as a number, no currency symbols"
            }
        },
        "required": ["is_payment_confirmation"]
    }
}

def parse_email(email_text, pipeline_run_id: str = "manual"):
    model, routing_reason = model_router.route_email_parser(email_text)
    message, trace = tracer.trace_call(
        client,
        pipeline_run_id=pipeline_run_id,
        agent_name="email_parser",
        input_summary=f"[{routing_reason}] {email_text[:100].replace(chr(10), ' ')}",
        model=model,
        max_tokens=256,
        tools=[TOOL],
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": f"""You are a bill payment assistant. Analyze this email and call extract_payment_info.

Only set is_payment_confirmation=true if this email confirms a payment was received, processed, or completed.

Do NOT treat these as confirmations:
- Payment reminders or upcoming payment alerts
- Bill statements or account summaries
- Usage reports or account activity notifications
- Scheduled payment notifications (payment not yet taken)
- Minimum payment due alerts

Email:
{email_text}"""
            }
        ]
    )

    for block in message.content:
        if block.type == "tool_use":
            result = block.input
            trace.result = f"is_payment={result.get('is_payment_confirmation')} company={result.get('company')} amount={result.get('amount')}"
            tracer.save_trace_result(trace)
            return result

    return {"is_payment_confirmation": False}


def extract_bill_info(email_text, pipeline_run_id: str = "manual"):
    result = parse_email(email_text, pipeline_run_id=pipeline_run_id)

    if not result.get("is_payment_confirmation"):
        return None, None

    company = result.get("company", "").strip()
    if not company:
        return None, None

    amount = result.get("amount")
    if amount is not None:
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = None

    return company, amount
