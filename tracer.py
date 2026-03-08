"""
tracer.py — Lightweight observability for AI agent calls.

Wraps client.messages.create() to capture:
  - Latency (ms)
  - Token usage (input, output, cache read/write)
  - Cost in USD
  - Tool calls made
  - Which agent, which model, which pipeline run

Saved to agent_traces table in the database.
This is the same concept behind tools like Langsmith and Langfuse — just local.
"""

import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import database as db

# ── Pricing (claude-haiku-4-5) ─────────────────────────────────────────
# https://www.anthropic.com/pricing
COST_PER_TOKEN = {
    "input":       0.80  / 1_000_000,   # $0.80 per million input tokens
    "output":      4.00  / 1_000_000,   # $4.00 per million output tokens
    "cache_write": 1.00  / 1_000_000,   # $1.00 per million cache-write tokens
    "cache_read":  0.08  / 1_000_000,   # $0.08 per million cache-read tokens
}

MODEL_COSTS = {
    "claude-haiku-4-5": COST_PER_TOKEN,
    # Add other models here as needed, e.g.:
    # "claude-sonnet-4-5": {"input": 3.00/1_000_000, "output": 15.00/1_000_000, ...}
}


@dataclass
class AgentTrace:
    pipeline_run_id: str
    agent_name: str
    model: str
    turn: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    tool_calls: list = field(default_factory=list)
    input_summary: str = ""
    result: str = ""
    timestamp: str = ""


def calculate_cost(model: str, input_tokens: int, output_tokens: int,
                   cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    """Calculate USD cost for an API call based on token counts."""
    pricing = MODEL_COSTS.get(model, COST_PER_TOKEN)
    return (
        input_tokens       * pricing["input"] +
        output_tokens      * pricing["output"] +
        cache_read_tokens  * pricing["cache_read"] +
        cache_write_tokens * pricing["cache_write"]
    )


def trace_call(client, pipeline_run_id: str, agent_name: str,
               turn: int = 1, input_summary: str = "", **api_kwargs):
    """
    Wrap a single client.messages.create() call with full observability.

    Usage:
        response, trace = trace_call(
            client,
            pipeline_run_id=run_id,
            agent_name="email_parser",
            input_summary="email from Xfinity",
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[...],
        )

    Returns: (response, AgentTrace)
    """
    start = time.time()
    response = client.messages.create(**api_kwargs)
    latency_ms = int((time.time() - start) * 1000)

    usage = response.usage
    input_tokens       = getattr(usage, "input_tokens", 0) or 0
    output_tokens      = getattr(usage, "output_tokens", 0) or 0
    cache_read_tokens  = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0

    model = api_kwargs.get("model", "unknown")
    cost  = calculate_cost(model, input_tokens, output_tokens,
                           cache_read_tokens, cache_write_tokens)

    # Extract tool calls from response content
    tool_calls = [
        {"name": block.name, "input": block.input}
        for block in response.content
        if hasattr(block, "type") and block.type == "tool_use"
    ]

    trace = AgentTrace(
        pipeline_run_id   = pipeline_run_id,
        agent_name        = agent_name,
        model             = model,
        turn              = turn,
        input_tokens      = input_tokens,
        output_tokens     = output_tokens,
        cache_read_tokens = cache_read_tokens,
        cache_write_tokens= cache_write_tokens,
        cost_usd          = cost,
        latency_ms        = latency_ms,
        tool_calls        = tool_calls,
        input_summary     = input_summary[:200],  # cap length
        timestamp         = datetime.now(timezone.utc).isoformat(),
    )

    # Note: trace.result can be updated by the caller after this returns.
    # Call db.update_trace_result(trace) afterwards if you want it persisted.
    db.save_agent_trace(trace)
    return response, trace


def save_trace_result(trace: AgentTrace):
    """Call this after setting trace.result to persist it to the DB."""
    db.update_trace_result(trace)
