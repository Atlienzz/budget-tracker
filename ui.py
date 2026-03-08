import streamlit as st
import database as db
import pandas as pd
from datetime import datetime
from database import get_connection

db.init_db()
st.set_page_config(layout="wide")
st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        min-width: 240px !important;
        max-width: 240px !important;
    }
    </style>
""", unsafe_allow_html=True)
st.title("💰 Ben & Heather's Bills")

pending_count = db.get_pending_review_count()
review_label  = f"👀 Review Queue ({pending_count})" if pending_count > 0 else "👀 Review Queue"

page = st.sidebar.radio("Menu", ["Dashboard", "View Bills", "Add a Bill", "Edit / Delete Bills", "Mark Paid", "Unmark Paid", "View Payments", "📧 Run Pipeline", "📋 Pipeline Log", "🤖 Monthly Insights", "🔍 Agent Traces", review_label])

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
    total_count = len(bills)
    paid_count  = len(payments)
    if total_count > 0:
        progress = paid_count / total_count
        st.progress(progress)
        st.caption(f"{paid_count} of {total_count} bills paid this month ({progress*100:.0f}%)")
    paid_ids = payments['bill_id'].tolist()
    unpaid   = bills[~bills['id'].isin(paid_ids)].copy()
    today    = datetime.now()
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
    if int(month) == today.month and int(year) == today.year:
        overdue  = unpaid[unpaid['due_day'] < today.day]
        due_soon = unpaid[(unpaid['due_day'] >= today.day) & (unpaid['due_day'] <= today.day + 3)]
        for _, row in overdue.iterrows():
            days_overdue = today.day - int(row['due_day'])
            st.error(f"🚨 {row['name']} is {days_overdue} day(s) overdue (due day {int(row['due_day'])}) — ${row['amount']:.2f}")
        for _, row in due_soon.iterrows():
            days_left = int(row['due_day']) - today.day
            if days_left == 0:
                st.error(f"🚨 {row['name']} is due TODAY — ${row['amount']:.2f}")
            elif days_left == 1:
                st.warning(f"⚠️ {row['name']} is due TOMORROW — ${row['amount']:.2f}")
            else:
                st.warning(f"⚠️ {row['name']} due in {days_left} days (day {int(row['due_day'])}) — ${row['amount']:.2f}")

    if pending_count > 0:
        st.warning(f"⏸️ **{pending_count} item(s) in the Review Queue** need your attention — the AI wasn't confident enough to record them automatically.")

    left_col, right_col = st.columns(2)
    with left_col:
        if not unpaid.empty:
            st.subheader("Still Unpaid")
            st.dataframe(unpaid[cols].sort_values('due_day'), width='stretch')
        else:
            st.success("All bills paid this month!")
    with right_col:
        if not payments.empty:
            st.subheader("Spending by Category")
            by_category = payments.groupby('category')['amount'].sum()
            st.bar_chart(by_category)

    st.divider()
    budget_col, form_col = st.columns(2)
    with budget_col:
        st.subheader("📊 Budget vs Actual")
        budgets_df = db.get_budgets_df(int(month), int(year))
        if not payments.empty:
            by_cat = payments.groupby('category')['amount'].sum().reset_index()
            by_cat.columns = ['category', 'spent']
            if not budgets_df.empty:
                budgets_renamed = budgets_df.rename(columns={'monthly_limit': 'budget'})[['category', 'budget']]
                merged = budgets_renamed.merge(by_cat, on='category', how='left')
                merged['spent'] = merged['spent'].fillna(0)
                merged['status'] = merged.apply(
                    lambda r: '✅ Under' if r['budget'] > 0 and r['spent'] <= r['budget']
                              else ('🚨 Over!' if r['budget'] > 0 and r['spent'] > r['budget']
                              else '— No budget set'), axis=1)
                merged['spent']  = merged['spent'].map('${:.2f}'.format)
                merged['budget'] = merged['budget'].apply(lambda x: f'${x:.2f}' if x > 0 else '—')
                st.dataframe(merged[['category', 'spent', 'budget', 'status']], width='stretch')
            else:
                st.info("No budgets set yet. Use Set Budgets to get started.")
        else:
            st.info("No payments this month to compare against budgets.")
    with form_col:
        st.subheader("⚙️ Set Category Budgets")
        budget_cat = st.selectbox("Category", db.CATEGORIES, key="budget_cat")
        budget_amt = st.number_input("Monthly Budget ($)", min_value=0.0, step=10.0, key="budget_amt")
        if st.button("Save Budget", key="save_budget"):
            db.set_budget(budget_cat, float(budget_amt), int(month), int(year))
            st.success(f"Budget set for {budget_cat}: ${budget_amt:.2f}")

elif page == "View Bills":
    st.subheader("Your Bills")
    bills = db.get_bills()
    if bills.empty:
        st.info("No bills yet. Go to Add a Bill to get started.")
    else:
        display_cols = ['name', 'amount', 'due_day', 'category', 'notes']
        st.dataframe(bills[display_cols], width='stretch')

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
        bills      = db.get_bills()
        bill_names = bills['name'].tolist()
        selected   = st.selectbox("Select a bill", bill_names)
        notes      = st.text_input("Payment note (optional)", placeholder="e.g. paid via autopay, paid late, etc.")
        month      = st.number_input("Month", min_value=1, max_value=12, value=datetime.now().month)
        year       = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)
    if st.button("Mark as Paid"):
        bill = bills[bills['name'] == selected].iloc[0]
        if db.is_paid(int(bill['id']), int(month), int(year)):
            st.warning(f"{selected} is already marked as paid for that month.")
        else:
            db.mark_paid(int(bill['id']), bill['amount'], int(month), int(year), notes)
            st.success(f"{selected} marked as paid!")

elif page == "Unmark Paid":
    bills = db.get_bills()
    if bills.empty:
        st.info("No bills yet. Go to Add a Bill to get started.")
    else:
        bill_names = bills['name'].tolist()
        selected   = st.selectbox("Select a bill", bill_names)
        month      = st.number_input("Month", min_value=1, max_value=12, value=datetime.now().month)
        year       = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)
    if st.button("Mark as Unpaid"):
        bill = bills[bills['name'] == selected].iloc[0]
        if db.is_paid(int(bill['id']), int(month), int(year)):
            db.unmark_paid(int(bill['id']), int(month), int(year))
            st.success(f"{selected} marked as unpaid!")
        else:
            st.warning(f"{selected} is not marked as paid for that month.")

elif page == "View Payments":
    st.subheader("Payment History")
    month    = st.number_input("Month", min_value=1, max_value=12, value=datetime.now().month)
    year     = st.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)
    payments = db.get_payments_df(int(month), int(year))
    if payments.empty:
        st.info("No payments found for that month.")
    else:
        display_cols = ['name', 'category', 'amount', 'paid_date', 'notes']
        st.dataframe(payments[display_cols], width="stretch")
        csv = payments[display_cols].to_csv(index=False)
        st.download_button(
            label="⬇️ Download CSV",
            data=csv,
            file_name=f"payments_{int(month)}_{int(year)}.csv",
            mime="text/csv"
        )

elif page == "Edit / Delete Bills":
    st.subheader("Edit or Delete a Bill")
    bills = db.get_bills()
    if bills.empty:
        st.info("No bills yet.")
    else:
        bill_names = bills['name'].tolist()
        selected   = st.selectbox("Select a bill", bill_names)
        bill       = bills[bills['name'] == selected].iloc[0]
        name     = st.text_input("Bill Name", value=bill['name'])
        amount   = st.number_input("Amount ($)", min_value=0.01, step=0.01, value=float(bill['amount']))
        due_day  = st.number_input("Due Day", min_value=1, max_value=31, value=int(bill['due_day']))
        category = st.selectbox("Category", db.CATEGORIES, index=db.CATEGORIES.index(bill['category']))
        notes    = st.text_input("Notes", value=bill['notes'])
        if st.button("Save Changes"):
            db.update_bill(int(bill['id']), name, amount, due_day, category, bool(bill['is_recurring']), notes)
            st.success(f"{name} updated!")
        st.divider()
        st.subheader("⚠️ Danger Zone")
        confirm = st.checkbox(f"I want to permanently delete '{selected}'")
        if confirm:
            if st.button("Delete Bill"):
                db.delete_bill(int(bill['id']))
                st.success(f"{selected} deleted.")
                st.rerun()

elif page == "📧 Run Pipeline":
    st.header("📧 Run Bill Pipeline")
    st.write("Connects to Gmail, finds bill emails, and records payments automatically.")

    if st.button("▶️ Run Pipeline Now"):
        import io, sys
        from bill_pipeline import run_gmail_pipeline

        output_capture = io.StringIO()
        sys.stdout = output_capture

        with st.spinner("Running pipeline..."):
            try:
                run_gmail_pipeline()
            finally:
                sys.stdout = sys.__stdout__

        output = output_capture.getvalue()

        total    = output.count("📧 Processing:")
        recorded = output.count("marked as paid")
        skipped  = output.count("skipping") + output.count("already paid")
        db.save_pipeline_log(total, recorded, skipped, output)

        st.text(output)
        st.success(f"Done! {recorded} payments recorded, {skipped} skipped out of {total} emails.")

elif page == "📋 Pipeline Log":
    st.header("📋 Pipeline Run History")

    logs = db.get_pipeline_logs(limit=20)

    if logs.empty:
        st.info("No pipeline runs yet.")
    else:
        for _, row in logs.iterrows():
            with st.expander(f"🕐 {row['run_timestamp']} — {row['recorded_count']} recorded, {row['skipped_count']} skipped  |  {row.get('source', 'manual')}"):
                st.text(row['log_text'])

elif page == "🤖 Monthly Insights":
    st.header("🤖 Monthly Insights")
    MONTH_NAMES = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"]
    col_month, col_year = st.columns(2)
    month_name = col_month.selectbox("Month", MONTH_NAMES, index=datetime.now().month - 1)
    month      = MONTH_NAMES.index(month_name) + 1
    year       = col_year.number_input("Year", min_value=2020, max_value=2030, value=datetime.now().year)

    if st.button("Generate Insights"):
        from agent_insight import generate_monthly_insight
        st.write_stream(generate_monthly_insight(int(month), int(year)))

elif page.startswith("👀 Review Queue"):
    from agent_payment_recorder import record_payment

    st.header("👀 Review Queue")
    st.caption("Items the AI wasn't confident enough to record automatically. You decide.")

    pending = db.get_pending_reviews()

    if pending.empty:
        st.success("Nothing pending — all caught up!")
    else:
        st.info(f"**{len(pending)} item(s)** waiting for your review")
        bills    = db.get_bills()
        bill_map = dict(zip(bills['name'], bills.index))  # name → df index

        for _, item in pending.iterrows():
            amount_str = f"${item['amount']:.2f}" if item['amount'] else "amount unknown"
            label      = f"🔍 {item['company_name']}  →  {item['suggested_bill_name'] or 'no suggestion'}  |  {amount_str}"

            with st.expander(label, expanded=True):
                col_info, col_actions = st.columns([2, 3])

                with col_info:
                    st.markdown(f"**Detected company:** {item['company_name']}")
                    st.markdown(f"**AI suggested:** {item['suggested_bill_name'] or '—'}")
                    st.markdown(f"**Amount:** {amount_str}")
                    st.markdown(f"**Email:** {item['email_subject'] or '—'}")
                    st.markdown(f"**Email date:** {item['email_date'] or '—'}")
                    st.caption(f"Queued: {item['created_at']}")

                with col_actions:
                    # ── Confirm AI's suggestion ──────────────────────────
                    if item['suggested_bill_id']:
                        if st.button("✅ Confirm AI suggestion", key=f"confirm_{item['id']}"):
                            suggested = bills[bills['id'] == item['suggested_bill_id']]
                            if not suggested.empty:
                                bill_row = suggested.iloc[0]
                                amount   = item['amount'] if item['amount'] else bill_row['amount']
                                record_payment(bill_row, amount, email_date=item['email_date'],
                                               notes="Recorded via review queue (confirmed)")
                                db.resolve_review(item['id'], 'approved', int(item['suggested_bill_id']))
                                st.success(f"Recorded as {bill_row['name']}!")
                                st.rerun()

                    # ── Pick a different bill ────────────────────────────
                    st.markdown("**Or pick a different bill:**")
                    corrected_name = st.selectbox(
                        "Select bill", ["— choose —"] + bills['name'].tolist(),
                        key=f"select_{item['id']}"
                    )
                    if corrected_name != "— choose —":
                        if st.button("🔄 Record with this bill", key=f"correct_{item['id']}"):
                            bill_row = bills[bills['name'] == corrected_name].iloc[0]
                            amount   = item['amount'] if item['amount'] else bill_row['amount']
                            record_payment(bill_row, amount, email_date=item['email_date'],
                                           notes=f"Recorded via review queue (corrected from '{item['suggested_bill_name']}')")
                            db.resolve_review(item['id'], 'corrected', int(bill_row['id']))
                            st.success(f"Recorded as {corrected_name}!")
                            st.rerun()

                    st.divider()

                    # ── Dismiss ──────────────────────────────────────────
                    if st.button("❌ Dismiss (not a bill payment)", key=f"dismiss_{item['id']}"):
                        db.resolve_review(item['id'], 'rejected')
                        st.info("Dismissed.")
                        st.rerun()

    # ── Resolved history ─────────────────────────────────────────────────
    st.divider()
    st.subheader("Resolved History")
    with get_connection() as conn:
        history = pd.read_sql_query(
            "SELECT * FROM review_queue WHERE status != 'pending' ORDER BY resolved_at DESC LIMIT 20",
            conn,
        )
    if history.empty:
        st.caption("No resolved items yet.")
    else:
        display_cols = ['company_name', 'suggested_bill_name', 'amount', 'status', 'resolved_at']
        st.dataframe(history[display_cols], use_container_width=True)

elif page == "🔍 Agent Traces":
    import json
    st.header("🔍 Agent Traces")
    st.caption("Every AI API call logged — tokens, cost, latency, tool calls. One row per agent turn.")

    runs = db.get_recent_pipeline_run_ids(limit=20)

    if not runs:
        st.info("No traces yet. Run the pipeline first and traces will appear here.")
    else:
        # Build labels for the selectbox
        run_labels = [
            f"{row[1][:19]}  |  {row[2]} calls  |  ${row[3]*100:.4f}¢  |  {row[4]:,} tokens  |  {row[0][:8]}..."
            for row in runs
        ]
        selected_label = st.selectbox("Select a pipeline run", run_labels)
        selected_idx   = run_labels.index(selected_label)
        selected_run   = runs[selected_idx]
        run_id         = selected_run[0]

        # ── Run summary metrics ──────────────────────────────────────────
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("API Calls",     selected_run[2])
        col2.metric("Total Cost",    f"${selected_run[3]*100:.5f}¢" if selected_run[3] < 0.01 else f"${selected_run[3]:.4f}")
        col3.metric("Total Tokens",  f"{selected_run[4]:,}")
        col4.metric("Started",       selected_run[1][:19] if selected_run[1] else "—")

        # ── Per-agent breakdown ──────────────────────────────────────────
        traces = db.get_traces_for_run(run_id)

        if traces.empty:
            st.info("No traces found for this run.")
        else:
            st.subheader("Per-Call Breakdown")

            # Format for display
            display = traces[[
                "agent_name", "turn", "model", "input_tokens", "output_tokens",
                "cache_read_tokens", "cost_usd", "latency_ms", "result"
            ]].copy()

            display["cost_usd"]    = display["cost_usd"].apply(lambda x: f"${x:.6f}")
            display["latency_ms"]  = display["latency_ms"].apply(lambda x: f"{x:,}ms")
            display["total_tokens"]= traces["input_tokens"] + traces["output_tokens"]
            display = display.rename(columns={
                "agent_name":        "Agent",
                "turn":              "Turn",
                "model":             "Model",
                "input_tokens":      "In Tokens",
                "output_tokens":     "Out Tokens",
                "cache_read_tokens": "Cache Read",
                "cost_usd":          "Cost",
                "latency_ms":        "Latency",
                "result":            "Result",
            })
            st.dataframe(display, use_container_width=True)

            # ── Aggregate by agent ──────────────────────────────────────
            st.subheader("Cost & Tokens by Agent")
            agg = traces.groupby("agent_name").agg(
                calls        = ("id", "count"),
                total_in     = ("input_tokens", "sum"),
                total_out    = ("output_tokens", "sum"),
                cache_read   = ("cache_read_tokens", "sum"),
                total_cost   = ("cost_usd", "sum"),
                avg_latency  = ("latency_ms", "mean"),
            ).reset_index()
            agg["total_cost"]  = agg["total_cost"].apply(lambda x: f"${x:.6f}")
            agg["avg_latency"] = agg["avg_latency"].apply(lambda x: f"{x:.0f}ms")
            st.dataframe(agg, use_container_width=True)

            # ── Tool calls detail ───────────────────────────────────────
            st.subheader("Tool Calls Made")
            has_tools = False
            for _, row in traces.iterrows():
                try:
                    calls = json.loads(row["tool_calls"]) if isinstance(row["tool_calls"], str) else row["tool_calls"]
                except Exception:
                    calls = []
                if calls:
                    has_tools = True
                    for c in calls:
                        st.code(
                            f"Agent: {row['agent_name']}  |  Turn {row['turn']}\n"
                            f"Tool:  {c.get('name')}\n"
                            f"Input: {json.dumps(c.get('input', {}), indent=2)}",
                            language="yaml"
                        )
            if not has_tools:
                st.info("No tool calls recorded for this run.")

