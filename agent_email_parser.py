import anthropic
from dotenv import load_dotenv
import os

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def parse_email(email_text):
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": f"""You are a bill payment assistant. Your job is to identify payment CONFIRMATION emails only.

Only extract information if this email confirms a payment was received, processed, or completed — such as "your payment has been received", "payment processed", "we received your payment", "autopay payment posted", etc.

Do NOT extract from:
- Payment reminders or upcoming payment alerts
- Bill statements or account summaries  
- Usage reports or account activity notifications
- Scheduled payment notifications (payment not yet taken)
- Minimum payment due alerts

If this email is NOT a confirmed payment, reply with:
NOT_A_BILL

Otherwise reply in this exact format and nothing else:
COMPANY: <company name>
AMOUNT: <amount as a number only, no $ sign, or UNKNOWN if no amount found>

Email:
{email_text}"""

            }
        ]
    )
    return message.content[0].text

def extract_bill_info(email_text):
    result = parse_email(email_text)
    lines = result.strip().split("\n")
    try:
        if not lines[0].startswith("COMPANY:"):    # ← add this check
            return None, None
        company = lines[0].replace("COMPANY: ", "").strip()
        if not company:
            return None, None
        try:
            amount = float(lines[1].replace("AMOUNT: ", "").strip())
        except (ValueError, IndexError):
            amount = None
        return company, amount
    except (IndexError):
        return None, None








