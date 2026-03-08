"""
model_router.py — Route pipeline tasks to the right model based on complexity.

Concept: not every task needs the same model. A simple extraction from a clear
"payment confirmed" email doesn't need claude-sonnet. A long, ambiguous email
might benefit from it. Routing by complexity optimises cost vs. quality.

Each route function returns (model_name, reason) so the tracer logs WHY a
particular model was chosen — useful for cost/accuracy audits in the UI.
"""

HAIKU  = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-5"

# Phrases that strongly signal a completed payment — haiku handles these easily
CLEAR_CONFIRMATION_KEYWORDS = [
    "payment confirmed",
    "payment received",
    "payment processed",
    "payment successful",
    "thank you for your payment",
    "your payment of",
    "we received your payment",
    "payment has been",
    "autopay processed",
    "autopayment processed",
    "payment complete",
]


def route_email_parser(email_text: str) -> tuple:
    """
    Choose the right model for parsing a bill payment email.

    Returns: (model_name: str, reason: str)

    Routing logic:
      1. Clear confirmation keywords present → haiku (fast, cheap, sufficient)
      2. Email longer than 1500 chars        → sonnet (better comprehension)
      3. Default                             → haiku
    """
    text_lower = email_text.lower()

    if any(kw in text_lower for kw in CLEAR_CONFIRMATION_KEYWORDS):
        return HAIKU, "clear_confirmation_keyword"

    if len(email_text) > 1500:
        return SONNET, "long_email_gt_1500_chars"

    return HAIKU, "default"


def route_bill_matcher(company_name: str) -> tuple:
    """
    Choose the right model for bill matching.

    Bill matching is straightforward list lookup with tool use — haiku every time.

    Returns: (model_name: str, reason: str)
    """
    return HAIKU, "simple_list_lookup"
