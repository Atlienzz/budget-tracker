import gmail_poller
from agent_email_parser import extract_bill_info
from agent_bill_matcher import match_bill
from agent_payment_recorder import record_payment

def process_bill_email(email_text):
    print("📧 Step 1: Parsing email...")
    company, amount = extract_bill_info(email_text)
    if company is None or amount is None:
        print("   ⚠️ Not a bill email — skipping")
        return
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

def run_gmail_pipeline():
    print("📬 Connecting to Gmail...")
    service = gmail_poller.get_gmail_service()
    emails = gmail_poller.get_bill_emails(service)
    print(f"Found {len(emails)} emails to process\n")
    for email in emails:
        print(f"📧 Processing: {email['subject']}")
        email_text = f"Subject: {email['subject']}\n\n{email['body']}"
        process_bill_email(email_text)
        print()

if __name__ == '__main__':
    run_gmail_pipeline()
