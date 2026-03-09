import gmail_poller
import os
import uuid
import database as db
import rag_memory
import agent_orchestrator as orchestrator
from agent_email_parser import extract_bill_info
from agent_bill_matcher import match_bill
from agent_payment_recorder import record_payment

def process_bill_email(email_text, email_date=None, pipeline_run_id: str = "manual",
                       email_subject: str = ""):
    print("📧 Step 1: Parsing email...")
    company, amount = extract_bill_info(email_text, pipeline_run_id=pipeline_run_id)
    if company is None:
        print("   ⚠️ Not a bill email — skipping")
        return
    if amount is None:
        print(f"   Found: {company} — no amount in email")
    else:
        print(f"   Found: {company} — ${amount:.2f}")
    print("🔍 Step 2: Matching to bill...")
    matched_bill, confidence = match_bill(company, pipeline_run_id=pipeline_run_id, amount=amount)
    if matched_bill is None:
        print("   ⚠️ Could not match to any bill — skipping")
        return
    print(f"   Matched: {matched_bill['name']} (Confidence: {confidence})")
    if confidence == "LOW":
        # Instead of discarding, park it for human review
        db.add_to_review_queue(
            email_subject    = email_subject,
            company_name     = company,
            suggested_bill_id   = int(matched_bill['id']),
            suggested_bill_name = matched_bill['name'],
            amount           = amount,
            email_date       = email_date or "",
            pipeline_run_id  = pipeline_run_id,
        )
        print(f"⏸️  Low confidence queued for review: '{company}' → '{matched_bill['name']}'")
        return
    if amount is None:
        amount = matched_bill['amount']
        print(f"   No amount found — using stored bill amount: ${amount:.2f}")
    print("💾 Step 3: Recording payment...")
    recorded = record_payment(matched_bill, amount, email_date=email_date)
    if recorded:
        rag_memory.add_payment_memory(company, matched_bill['name'], confidence, amount)
        print("🧠 RAG memory updated.")
    print("✅ Pipeline complete!")

def run_gmail_pipeline(token_files=None):
    if token_files is None:
        token_files = ['token.json', 'token2.json']

    # Unique ID that links all agent traces for this pipeline run
    pipeline_run_id = str(uuid.uuid4())
    print(f"🔎 Pipeline run ID: {pipeline_run_id}")

    all_emails = []
    for token_file in token_files:
        if not os.path.exists(token_file):
            print(f"⚠️ No token found for {token_file} — skipping")
            continue
        print(f"📬 Connecting to Gmail ({token_file})...")
        try:
            service = gmail_poller.get_gmail_service(token_file=token_file)
            last_run = db.get_last_pipeline_run_date()
            emails = gmail_poller.get_bill_emails(service, after_date=last_run)
            print(f"   Found {len(emails)} emails")
            all_emails.extend(emails)
        except Exception as e:
            print(f"⚠️ Could not connect ({token_file}): {e}")

    print(f"\n📊 Total: {len(all_emails)} emails to process\n")

    for email in all_emails:
        if db.is_email_processed(email['id']):
            print(f"⏭️ Already processed: {email['subject']}")
            print()
            continue

        # Orchestrator decides the route before any downstream agents run
        route, reason = orchestrator.route_email(
            subject=email['subject'],
            body_preview=email['body'][:500],
            pipeline_run_id=pipeline_run_id,
        )
        print(f"📧 {email['subject']}")
        print(f"🧭 Route: {route} — {reason}")

        if route == "skip":
            db.mark_email_processed(email['id'])
            print()
            continue

        elif route == "dispute":
            print(f"⚠️  DISPUTE flagged — review manually")
            db.mark_email_processed(email['id'])
            print()
            continue

        elif route == "force_review":
            db.add_to_review_queue(
                email_subject=email['subject'],
                company_name=reason,
                suggested_bill_id=None,
                suggested_bill_name="",
                amount=None,
                email_date=email['date'],
                pipeline_run_id=pipeline_run_id,
            )
            print(f"⏸️  Routed to review queue")
            db.mark_email_processed(email['id'])
            print()
            continue

        # route == "standard" — run the full pipeline
        email_text = f"Subject: {email['subject']}\n\n{email['body']}"
        process_bill_email(email_text, email_date=email['date'],
                           pipeline_run_id=pipeline_run_id,
                           email_subject=email['subject'])
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

