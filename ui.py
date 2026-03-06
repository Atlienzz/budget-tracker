import streamlit as st
import database as db
from datetime import datetime


db.init_db()

st.title("💰 Budget Tracker")

page = st.sidebar.radio("Menu", ["View Bills", "Add a Bill", "Mark Paid", "View Payments"])

if page == "View Bills":
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
        month = st.number_input("Month", min_value=1, max_value=12, value=datetime.now().month)
        year  = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)

    if st.button("Mark as Paid"):
        bill = bills[bills['name'] == selected].iloc[0]
        db.mark_paid(int(bill['id']), bill['amount'], int(month), int(year))
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



