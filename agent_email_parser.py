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
                "content": f"""You are a bill payment assistant. Extract the company name and amount due from this email.
                
Reply in this exact format and nothing else:
COMPANY: <company name>
AMOUNT: <amount as a number only, no $ sign>

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







