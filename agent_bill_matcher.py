import anthropic
from dotenv import load_dotenv
import os
import database as db
import tracer

load_dotenv(override=True)
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

GET_BILLS_TOOL = {
    "name": "get_bills",
    "description": "Returns the list of bills from the database",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": []
    }
}

RECORD_MATCH_TOOL = {
    "name": "record_match",
    "description": "Record the matched bill and confidence level",
    "input_schema": {
        "type": "object",
        "properties": {
            "bill_name": {
                "type": "string",
                "description": "Exact bill name from the list"
            },
            "confidence": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW"],
                "description": "Match confidence. Use LOW for retail stores, one-time purchases, or weak matches."
            }
        },
        "required": ["bill_name", "confidence"]
    }
}

def match_bill(company_name, pipeline_run_id: str = "manual"):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": """You are a bill matching assistant. Match this company to the correct bill.

IMPORTANT: Bill companies are typically financial services, utilities, insurance providers, loan servicers, or subscription services. Retail stores and one-time purchase companies are NOT bills — use LOW confidence for these.

First call get_bills to see the bill list, then call record_match with your answer.""",
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": f"Company to match: {company_name}"
                }
            ]
        }
    ]

    bills_df = None
    turn = 0

    # Multi-turn loop — keep going until Claude stops calling tools
    while True:
        turn += 1
        response, trace = tracer.trace_call(
            client,
            pipeline_run_id=pipeline_run_id,
            agent_name="bill_matcher",
            turn=turn,
            input_summary=f"company={company_name} turn={turn}",
            model="claude-haiku-4-5",
            max_tokens=256,
            tools=[GET_BILLS_TOOL, RECORD_MATCH_TOOL],
            messages=messages
        )

        # Add Claude's response to the conversation
        messages.append({"role": "assistant", "content": response.content})

        # Check what Claude wants to do
        tool_calls = [b for b in response.content if b.type == "tool_use"]

        if not tool_calls:
            # Claude stopped calling tools without a match
            trace.result = "no_match (no tool calls)"
            tracer.save_trace_result(trace)
            return None, "LOW"

        tool_results = []
        final_match = None
        final_confidence = None

        for tool_call in tool_calls:
            if tool_call.name == "get_bills":
                bills_df = db.get_bills()
                bill_names = bills_df['name'].tolist()
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": "\n".join(bill_names)
                })

            elif tool_call.name == "record_match":
                final_match = tool_call.input.get("bill_name")
                final_confidence = tool_call.input.get("confidence")
                trace.result = f"matched={final_match} confidence={final_confidence}"
                tracer.save_trace_result(trace)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": "Match recorded."
                })

        # Send tool results back to Claude
        messages.append({"role": "user", "content": tool_results})

        # If we got a final match, return it
        if final_match and final_confidence and bills_df is not None:
            try:
                matched_bill = bills_df[bills_df['name'] == final_match].iloc[0]
                return matched_bill, final_confidence
            except IndexError:
                return None, "LOW"

        # If Claude only called get_bills, loop continues so it can call record_match
        if response.stop_reason == "end_turn":
            return None, "LOW"
