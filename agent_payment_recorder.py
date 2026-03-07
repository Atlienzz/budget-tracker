import database as db
from datetime import datetime

def record_payment(bill, amount, notes="Recorded by AI agent"):
    month = datetime.now().month
    year  = datetime.now().year

    if db.is_paid(int(bill['id']), month, year):
        print(f"⚠️ {bill['name']} is already paid for this month.")
        return False

    db.mark_paid(int(bill['id']), amount, month, year, notes)
    print(f"✅ {bill['name']} marked as paid — ${amount:.2f}")
    return True

# Test it
import database as db
bills = db.get_bills()
test_bill = bills[bills['name'] == 'Lending Club (Auto Pay)'].iloc[0]
record_payment(test_bill, 415.00)
