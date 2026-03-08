import gmail_poller
import os
import database as db
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

import os

def run_gmail_pipeline(token_files=None):
    if token_files is None:
        token_files = ['token.json', 'token2.json']

    all_emails = []
    for token_file in token_files:
        if not os.path.exists(token_file):
            print(f"⚠️ No token found for {token_file} — skipping")
            continue
        print(f"📬 Connecting to Gmail ({token_file})...")
        try:
            service = gmail_poller.get_gmail_service(token_file=token_file)
            emails = gmail_poller.get_bill_emails(service)
            print(f"   Found {len(emails)} emails")
            all_emails.extend(emails)
        except Exception as e:
            print(f"⚠️ Could not connect ({token_file}): {e}")

    print(f"\n📊 Total: {len(all_emails)} emails to process\n")

    SKIP_KEYWORDS = [
    # Marketing / retail
    'unsubscribe', 'sale', 'deal', 'offer', 'coupon', 'promo', 'discount',
    'newsletter', 'limited time', 'exclusive', 'flash sale', '%  off',
    # Shopping / orders
    'order confirmation', 'order shipped', 'order delivered', 'order update',
    'shipping', 'tracking', 'delivered', 'out for delivery', 'your package',
    # Account / auth (non-billing)
    'verify', 'verification', 'welcome', 'confirm your', 'reset your password',
    'sign in', 'login attempt', 'new device',
    # Surveys / misc
    'survey', 'feedback', 'how did we do', 'rate your', 'unsubscribe',
    'you\'ve been selected', 'congratulations',
    # Payment reminders & non-confirmation bill emails
    'upcoming', 'due alert', 'minimum payment due', 'statement is ready',
    'bill statement', 'peak hours', 'bill period', 'you spent',
    'last day to make changes', 'scheduled for',

]

    for email in all_emails:
        subject_lower = email['subject'].lower()
        if any(kw in subject_lower for kw in SKIP_KEYWORDS):
            print(f"⏭️ Skipping (subject filter): {email['subject']}")
            print()
            continue
        if db.is_email_processed(email['id']):
            print(f"⏭️ Already processed: {email['subject']}")
            print()
            continue
        print(f"📧 Processing: {email['subject']}")
        email_text = f"Subject: {email['subject']}\n\n{email['body']}"
        process_bill_email(email_text, email_date=email['date'])
        db.mark_email_processed(email['id'])
        print()

if __name__ == '__main__':
    import io, sys
    
    db.init_db()

    output_capture = io.StringIO()
    sys.stdout = output_capture

    try:
        run_gmail_pipeline()
    finally:
        sys.stdout = sys.__stdout__

    output = output_capture.getvalue()
    print(output)

    total    = output.count("📧 Processing:")
    recorded = output.count("marked as paid")
    skipped  = output.count("skipping") + output.count("already paid")
    db.save_pipeline_log(total, recorded, skipped, output, source="scheduler")

