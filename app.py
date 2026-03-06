import database as db

db.init_db()

def show_menu():
    print("\n--- Budget Tracker ---")
    print("1. View all bills")
    print("2. Add a bill")
    print("3. Mark bill as paid")
    print("4. View payments")
    print("5. Quit")

def view_bills():
    bills = db.get_bills()
    if bills.empty:
        print("No bills yet.")
    else:
        for _, bill in bills.iterrows():
            print(f"{bill['name']:<20} {bill['category']:<15} ${bill['amount']:>8.2f}   Due day: {bill['due_day']}")

def add_bill():
    name     = input("Bill name: ")
    amount   = float(input("Amount: "))
    due_day  = int(input("Due day of month: "))
    category = input("Category: ")
    db.add_bill(name, amount, due_day, category)
    print(f"{name} added!")

def mark_paid():
    bills = db.get_bills()
    for _, bill in bills.iterrows():
        print(f"{bill['id']}. {bill['name']:<20} ${bill['amount']:>8.2f}")
    
    bill_id = int(input("Enter bill ID to mark paid: "))
    month   = int(input("Month (1-12): "))
    year    = int(input("Year: "))

    bill = bills[bills['id'] == bill_id].iloc[0]
    
    db.mark_paid(bill_id, bill['amount'], month, year)
    print("Marked as paid!")

def view_payments():
    month   = int(input("Month (1-12): "))
    year    = int(input("Year: "))
    payments = db.get_payments_df(month,year)
    if payments.empty:
        print("No payments found.")
    else:
        print(payments)

while True:
    show_menu()
    choice = input("Choose: ")

    if choice == "1":
        view_bills()
    elif choice == "2":
        add_bill()
    elif choice == "3":
        mark_paid()
    elif choice == "4":
        view_payments()
    elif choice == "5":
        break











    




