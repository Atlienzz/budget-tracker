import anthropic
from dotenv import load_dotenv
import os
import database as db

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def generate_monthly_insight(month, year):
    bills = db.get_bills()
    payments = db.get_payments_df(month, year)

    if payments.empty:
        return "No payments recorded for this month yet."

    total_bills = bills['amount'].sum()
    total_paid = payments['amount'].sum()
    unpaid_count = len(bills) - len(payments)

    # Build payment summary text to pass to Claude
    payment_lines = []
    for _, row in payments.iterrows():
        payment_lines.append(f"  {row['name']} ({row['category']}): ${row['amount']:.2f}")

    unpaid_bills = bills[~bills['id'].isin(payments['bill_id'].tolist())]
    unpaid_lines = []
    for _, row in unpaid_bills.iterrows():
        unpaid_lines.append(f"  {row['name']}: ${row['amount']:.2f}")

    # Build multi-month history for trend analysis
    history_lines = []
    for m in range(1, month):
        prev = db.get_payments_df(m, year)
        if not prev.empty:
            history_lines.append(f"  {m}/{year}: ${prev['amount'].sum():.2f} paid across {len(prev)} bills")

    prompt = f"""You are a personal finance assistant analyzing someone's bill payment data.

Month: {month}/{year}
Total bills: ${total_bills:.2f}
Total paid so far: ${total_paid:.2f}
Unpaid bills remaining: {unpaid_count}

Payments made:
{chr(10).join(payment_lines)}

Unpaid bills:
{chr(10).join(unpaid_lines) if unpaid_lines else '  None — all paid!'}

Payment history this year:
{chr(10).join(history_lines) if history_lines else '  No prior months this year.'}

Write a conversational summary of this month's bill situation with 3-4 short paragraphs separated by blank lines. Each paragraph should cover one topic: overall status, concerns, positives, and priority action items. Be direct and specific, not generic. Do not use any markdown formatting, bold, italics, or special characters — plain text only."""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text
