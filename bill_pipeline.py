from agent_email_parser import extract_bill_info
from agent_bill_matcher import match_bill
from agent_payment_recorder import record_payment

def process_bill_email(email_text):
    print("📧 Step 1: Parsing email...")
    company, amount = extract_bill_info(email_text)
    print(f"   Found: {company} — ${amount:.2f}")

    print("🔍 Step 2: Matching to bill...")
    matched_bill, confidence = match_bill(company)
    print(f"   Matched: {matched_bill['name']} (Confidence: {confidence})")

    if confidence == "LOW":
        print("⚠️  Low confidence match — skipping. Manual review needed.")
        return

    print("💾 Step 3: Recording payment...")
    record_payment(matched_bill, amount)
    print("✅ Pipeline complete!")

# Test with a few fake emails
emails = [
    """From: billing@lendingclub.com
    Subject: Payment of $415.00 due March 8th""",

    """From: noreply@geico.com
    Subject: Your insurance payment of $351.00 is due""",

    """From: billing@rentcafe.com
    Subject: Your rent payment of $750.00 is due March 1st""",
]

for email in emails:
    print("\n" + "="*50)
    process_bill_email(email)
