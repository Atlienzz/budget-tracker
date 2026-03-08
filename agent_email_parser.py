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
                "content": f"""You are a bill payment assistant. Extract the company name and payment amount from this email. This could be a bill statement, payment reminder, or payment confirmation (e.g. "your payment has been processed").

If this email is related to a bill, subscription, loan, utility, insurance, or any recurring payment — extract the company and amount. The amount may be labeled as "amount due", "payment amount", "amount paid", "payment processed", or similar.

If this email has nothing to do with bills or payments, reply with:
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








