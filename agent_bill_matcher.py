import anthropic
from dotenv import load_dotenv
import os
import database as db

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def match_bill(company_name):
    bills = db.get_bills()
    bill_names = bills['name'].tolist()
    bill_list  = "\n".join(bill_names)

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": f"""You are a bill matching assistant. Match the company name to the closest bill in the list.

Reply in this exact format and nothing else:
MATCH: <exact bill name from the list>
CONFIDENCE: <HIGH, MEDIUM, or LOW>

Company to match: {company_name}

Bill list:
{bill_list}"""
            }
        ]
    )

    result = message.content[0].text
    lines      = result.strip().split("\n")
    try:
        match      = lines[0].replace("MATCH: ", "").strip()
        confidence = lines[1].replace("CONFIDENCE: ", "").strip()
        matched_bill = bills[bills['name'] == match].iloc[0]
        return matched_bill, confidence
    except (IndexError, KeyError):
        return None, "LOW"




