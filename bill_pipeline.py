import gmail_poller
from agent_email_parser import extract_bill_info
from agent_bill_matcher import match_bill
from agent_payment_recorder import record_payment

def process_bill_email(email_text, email_date=None):
    print("📧 Step 1: Parsing email...")
    company, amount = extract_bill_info(email_text)
    if company is None:
        print("   ⚠️ Not a bill email — skipping")
        return
    if amount is None:
        print(f"   Found: {company} — no amount in email")
    else:
        print(f"   Found: {company} — ${amount:.2f}")
    print("🔍 Step 2: Matching to bill...")
    matched_bill, confidence = match_bill(company)
    if matched_bill is None:
        print("   ⚠️ Could not match to any bill — skipping")
        return
    print(f"   Matched: {matched_bill['name']} (Confidence: {confidence})")
    if confidence == "LOW":
        print("⚠️  Low confidence match — skipping. Manual review needed.")
        return
    if amount is None:
        amount = matched_bill['amount']
        print(f"   No amount found — using stored bill amount: ${amount:.2f}")
    print("💾 Step 3: Recording payment...")
    record_payment(matched_bill, amount, email_date=email_date)
    print("✅ Pipeline complete!")


def run_gmail_pipeline():
    print("📬 Connecting to Gmail...")
    service = gmail_poller.get_gmail_service()
    emails = gmail_poller.get_bill_emails(service)
    print(f"Found {len(emails)} emails to process\n")
    for email in emails:
        print(f"📧 Processing: {email['subject']}")
        email_text = f"Subject: {email['subject']}\n\n{email['body']}"
        process_bill_email(email_text, email_date=email['date'])
        print()

if __name__ == '__main__':
    run_gmail_pipeline()
