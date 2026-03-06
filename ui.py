import streamlit as st
import database as db
from datetime import datetime


db.init_db()

st.title("💰 Budget Tracker")

page = st.sidebar.radio("Menu", ["Dashboard", "View Bills", "Add a Bill", "Mark Paid", "View Payments"])

if page == "Dashboard":
    MONTH_NAMES = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    
    col_month, col_year = st.columns(2)
    month_name = col_month.selectbox("Month", MONTH_NAMES, index=datetime.now().month - 1)
    month      = MONTH_NAMES.index(month_name) + 1
    year       = col_year.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)

    st.subheader(f"{month_name} {int(year)} Summary")

    bills    = db.get_bills()
    payments = db.get_payments_df(int(month), int(year))
    total_bills     = bills['amount'].sum()
    total_paid      = payments['amount'].sum()
    total_remaining = total_bills - total_paid

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Bills", f"${total_bills:.2f}")
    col2.metric("Paid",        f"${total_paid:.2f}")
    col3.metric("Remaining",   f"${total_remaining:.2f}")

    paid_ids   = payments['bill_id'].tolist()
    unpaid     = bills[~bills['id'].isin(paid_ids)]

    unpaid = unpaid.copy()
    today  = datetime.now()

    if int(month) == today.month and int(year) == today.year:
        unpaid.loc[:, 'days_until_due'] = unpaid['due_day'].apply(
            lambda d: f"{d - today.day} days" if d >= today.day else "Overdue")
        cols = ['name', 'category', 'amount', 'due_day', 'days_until_due']
    else:
        from datetime import date
        selected_date = date(int(year), int(month), 1)
        current_date  = date(today.year, today.month, 1)
        if selected_date < current_date:
            unpaid.loc[:, 'days_until_due'] = "Overdue"
            cols = ['name', 'category', 'amount', 'due_day', 'days_until_due']
        else:
            cols = ['name', 'category', 'amount', 'due_day']

    if not unpaid.empty:
        st.subheader("Still Unpaid")
        st.dataframe(unpaid[cols].sort_values('due_day'), width='stretch')
    else:
        st.success("All bills paid this month!")

    if not payments.empty:
        st.subheader("Spending by Category")
        by_category = payments.groupby('category')['amount'].sum()
        st.bar_chart(by_category)


elif page == "View Bills":
    st.subheader("Your Bills")
    bills = db.get_bills()
    if bills.empty:
        st.info("No bills yet. Go to Add a Bill to get started.")
    else:
        st.dataframe(bills, width='stretch')

elif page == "Add a Bill":
    st.subheader("Add a New Bill")
    
    name     = st.text_input("Bill Name")
    amount   = st.number_input("Amount ($)", min_value=0.01, step=0.01)
    due_day  = st.number_input("Due Day of Month", min_value=1, max_value=31, value=1)
    category = st.selectbox("Category", db.CATEGORIES)
    notes    = st.text_input("Notes (optional)")
    
    if st.button("Add Bill"):
        if name:
            db.add_bill(name, amount, due_day, category, notes=notes)
            st.success(f"{name} added!")
        else:
            st.error("Bill name is required.")

elif page == "Mark Paid":
    bills = db.get_bills()
    if bills.empty:
        st.info("No bills yet. Go to Add a Bill to get started.")
    else:
        st.dataframe(bills, width="stretch")
        bills = db.get_bills()
        bill_names = bills['name'].tolist()
        selected = st.selectbox("Select a bill", bill_names)
        notes    = st.text_input("Payment note (optional)", placeholder="e.g. paid via autopay, paid late, etc.")
        month    = st.number_input("Month", min_value=1, max_value=12, value=datetime.now().month)
        year     = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)


    if st.button("Mark as Paid"):
        bill = bills[bills['name'] == selected].iloc[0]
        if db.is_paid(int(bill['id']), int(month), int(year)):
            st.warning(f"{selected} is already marked as paid for that month.")
        else:
            db.mark_paid(int(bill['id']), bill['amount'], int(month), int(year), notes)
            st.success(f"{selected} marked as paid!")



elif page == "View Payments":
    st.subheader("Payment History")
    month    = st.number_input("Month", min_value=1, max_value=12, value=datetime.now().month)
    year     = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)
    payments = db.get_payments_df(int(month), int(year))

    if payments.empty:
        st.info("No payments found for that month.")
    else:
        st.dataframe(payments, width="stretch")



