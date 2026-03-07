import database as db
from datetime import datetime

def record_payment(bill, amount, notes="Recorded by AI agent", email_date=None):
    if email_date:
        month = email_date.month
        year  = email_date.year
    else:
        month = datetime.now().month
        year  = datetime.now().year

    if db.is_paid(int(bill['id']), month, year):
        print(f"⚠️ {bill['name']} is already paid for this month.")
        return False

    db.mark_paid(int(bill['id']), amount, month, year, notes)
    print(f"✅ {bill['name']} marked as paid — ${amount:.2f}")
    return True


