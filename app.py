# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import matplotlib.pyplot as plt

# Import backend modules (assume they are in backend.py)
from backend import (
    SupabaseConnection,
    UserManager,
    ShiftManager,
    ExpenseHeadManager,
    VendorManager,
    PersonalLedgerManager,
    ReportsManager,
    SalesManager,
    ExpensesManager
)

# ============================================
# PAGE CONFIG & CUSTOM CSS
# ============================================
st.set_page_config(
    page_title="Pharmacy Cash & Ledger System",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for professional look
st.markdown("""
<style>
    /* Main container */
    .main {
        padding: 0 1rem;
    }
    /* Headers */
    h1, h2, h3 {
        color: #2c3e50;
    }
    /* Metric cards */
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: bold;
        color: #27ae60;
    }
    div[data-testid="stMetricDelta"] {
        font-size: 0.9rem;
    }
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #f8f9fa;
        padding: 1rem;
    }
    /* Buttons */
    .stButton > button {
        background-color: #3498db;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    .stButton > button:hover {
        background-color: #2980b9;
    }
    /* Success/Error messages */
    .stAlert {
        border-radius: 5px;
    }
    /* Tables */
    .dataframe {
        font-size: 0.9rem;
    }
    /* Form spacing */
    .stForm {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    /* Expander */
    .streamlit-expanderHeader {
        font-size: 1rem;
        font-weight: 600;
        color: #34495e;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# SESSION STATE INITIALIZATION
# ============================================
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.page = "Login"
    st.session_state.pdf_settings = {
        'primary_color': '#3498db',
        'secondary_color': '#2ecc71',
        'font_size': 10,
        'company_name': 'Pharmacy Store'
    }

# ============================================
# PDF GENERATION FUNCTIONS
# ============================================
def generate_pdf(dataframe: pd.DataFrame, title: str, filename: str) -> bytes:
    """Generate PDF from dataframe with customizable colors."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Use settings from session state
    primary = st.session_state.pdf_settings['primary_color']
    secondary = st.session_state.pdf_settings['secondary_color']
    font_size = st.session_state.pdf_settings['font_size']
    company = st.session_state.pdf_settings['company_name']

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor(primary))
    c.drawString(50, height - 50, company)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, title)
    c.drawString(50, height - 85, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Convert dataframe to list of lists for table
    data = [dataframe.columns.tolist()] + dataframe.values.tolist()
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(secondary)),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), font_size+2),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    # Wrap table to fit page width
    table.wrapOn(c, width-100, height)
    table.drawOn(c, 50, height - 200 - len(data)*20)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def get_pdf_download_link(pdf_bytes: bytes, filename: str) -> str:
    """Generate a download link for PDF."""
    b64 = base64.b64encode(pdf_bytes).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64}" download="{filename}">📥 Download PDF</a>'
    return href

# ============================================
# LOGIN FUNCTION
# ============================================
def login():
    st.markdown("<h1 style='text-align: center;'>💊 Pharmacy Cash & Ledger System</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            st.subheader("Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                um = UserManager()
                user = um.authenticate(username, password)
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user = user
                    st.session_state.page = "Dashboard"
                    st.rerun()
                else:
                    st.error("Invalid username or password")

# ============================================
# LOGOUT FUNCTION
# ============================================
def logout():
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.page = "Login"
    st.rerun()

# ============================================
# SIDEBAR NAVIGATION
# ============================================
def sidebar_navigation():
    with st.sidebar:
        st.image("https://via.placeholder.com/150x50?text=Pharmacy+Logo", use_column_width=True)
        st.markdown(f"**Welcome, {st.session_state.user['full_name']}**")
        st.markdown(f"Role: **{st.session_state.user['role']}**")
        if st.session_state.user['shift']:
            st.markdown(f"Shift: **{st.session_state.user['shift']}**")
        st.divider()

        # Define menu based on role
        role = st.session_state.user['role']
        menu_options = []

        # Common menus
        menu_options.append("Dashboard")

        if role == 'Super User':
            menu_options.extend([
                "User Management",
                "Shift Management",
                "Sales Entry",
                "Expense Heads",
                "Expense Entry",
                "Vendor Master",
                "Vendor Ledger",
                "Personal Ledger",
                "Reports",
                "PDF Settings"
            ])
        elif role == 'Owner':
            menu_options.extend([
                "Shift Management",
                "Sales Entry",
                "Expense Heads",
                "Expense Entry",
                "Vendor Master",
                "Vendor Ledger",
                "Personal Ledger",
                "Reports",
                "PDF Settings"
            ])
        elif role == 'Accountant':
            menu_options.extend([
                "Shift Management",
                "Sales Entry",
                "Expense Heads",
                "Expense Entry",
                "Vendor Master",
                "Vendor Ledger",
                "Reports"
            ])
        elif role in ['Morning User', 'Evening User', 'Night User']:
            menu_options.extend([
                "My Shift",
                "Sales Entry",
                "Expense Entry"
            ])

        selected = st.radio("Navigation", menu_options, key="nav")
        st.session_state.page = selected

        st.divider()
        if st.button("Logout"):
            logout()

# ============================================
# DASHBOARD
# ============================================
def show_dashboard():
    st.header("📊 Dashboard")
    user = st.session_state.user
    role = user['role']

    if role in ['Morning User', 'Evening User', 'Night User']:
        # Shift user dashboard: show current shift status
        shift_mgr = ShiftManager()
        current_shift = shift_mgr.get_current_shift(user['shift'])
        if current_shift:
            st.subheader(f"Current {user['shift']} Shift")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Opening Cash", f"PKR {current_shift['opening_cash']:,.2f}")
            with col2:
                expected = shift_mgr.calculate_expected_cash(current_shift['id'])
                st.metric("Expected Cash (so far)", f"PKR {expected:,.2f}")
            with col3:
                st.metric("Status", current_shift['status'].upper())

            # Show recent transactions
            st.subheader("Recent Transactions")
            sales_mgr = SalesManager()
            recent_sales = sales_mgr.get_sales(shift_id=current_shift['id'], limit=5)
            if recent_sales:
                df = pd.DataFrame(recent_sales)
                st.dataframe(df[['sale_date', 'invoice_number', 'amount']])
        else:
            st.warning(f"No open {user['shift']} shift. Please open a shift from Shift Management.")

    else:
        # Owner/Accountant/Super User dashboard: day-wise KPIs
        reports_mgr = ReportsManager()
        today = date.today()
        summary = reports_mgr.get_daily_summary(today)

        st.subheader(f"Summary for {today.strftime('%d %b %Y')}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Sales Today", f"PKR {summary['total_sales']:,.2f}")
        with col2:
            st.metric("Total Expenses Today", f"PKR {summary['total_expenses']:,.2f}")
        with col3:
            st.metric("Net Cash Today", f"PKR {summary['net_cash']:,.2f}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Vendor Payable", f"PKR {summary['vendor_payable']:,.2f}")
        with col2:
            st.metric("Personal Balance", f"PKR {summary['personal_balance']:,.2f}")
        with col3:
            # Cash difference across all shifts today? We'll leave blank or add total opening
            st.metric("Drawer Opening", "PKR 10,000.00")

        # Optional chart
        st.subheader("Recent Activity")
        # Show last 5 transactions across modules (could be combined)
        # For simplicity, show recent sales
        sales_mgr = SalesManager()
        recent_sales = sales_mgr.get_sales(limit=5)
        if recent_sales:
            df = pd.DataFrame(recent_sales)
            st.dataframe(df[['sale_date', 'invoice_number', 'amount']])

# ============================================
# USER MANAGEMENT
# ============================================
def show_user_management():
    st.header("👥 User Management")
    um = UserManager()
    users = um.get_all_users(include_inactive=True)

    with st.expander("➕ Add New User", expanded=False):
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                username = st.text_input("Username*")
                password = st.text_input("Password*", type="password")
                full_name = st.text_input("Full Name*")
            with col2:
                role = st.selectbox("Role*", ['Morning User', 'Evening User', 'Night User', 'Accountant', 'Owner', 'Super User'])
                shift = st.selectbox("Shift (for shift users)", ['', 'Morning', 'Evening', 'Night'])
                if shift == '':
                    shift = None
            submitted = st.form_submit_button("Create User")
            if submitted:
                if not username or not password or not full_name:
                    st.error("Please fill all required fields.")
                else:
                    user_data = {
                        'username': username,
                        'password': password,
                        'full_name': full_name,
                        'role': role,
                        'shift': shift
                    }
                    success, msg = um.create_user(user_data, st.session_state.user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    st.subheader("Existing Users")
    if users:
        df = pd.DataFrame(users)
        # Show relevant columns
        df_display = df[['username', 'full_name', 'role', 'shift', 'is_active', 'created_at']]
        st.dataframe(df_display, use_container_width=True)

        # Deactivate/Reactivate
        st.subheader("Manage User Status")
        user_to_manage = st.selectbox("Select User", [u['username'] for u in users])
        selected_user = next(u for u in users if u['username'] == user_to_manage)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Deactivate User"):
                if selected_user['id'] == st.session_state.user['id']:
                    st.error("You cannot deactivate yourself.")
                else:
                    success, msg = um.deactivate_user(selected_user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        with col2:
            if st.button("Reactivate User"):
                success, msg = um.reactivate_user(selected_user['id'])
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    else:
        st.info("No users found.")

# ============================================
# SHIFT MANAGEMENT
# ============================================
def show_shift_management():
    st.header("🕒 Shift Management")
    user = st.session_state.user
    shift_mgr = ShiftManager()

    # Determine which shifts user can manage
    if user['role'] == 'Super User':
        shift_options = ['Morning', 'Evening', 'Night']
    elif user['role'] == 'Owner' or user['role'] == 'Accountant':
        shift_options = ['Morning', 'Evening', 'Night']
    else:
        shift_options = [user['shift']]

    selected_shift = st.selectbox("Select Shift", shift_options)

    current = shift_mgr.get_current_shift(selected_shift)
    if current:
        st.info(f"**Current {selected_shift} shift is OPEN**")
        st.write(f"Opened at: {current['opening_date']} {current['opening_time']}")
        st.write(f"Opening Cash: PKR {current['opening_cash']:,.2f}")

        # Show summary
        summary = shift_mgr.get_shift_summary(current['id'])
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Sales", f"PKR {summary['sales']:,.2f}")
        with col2:
            st.metric("Expenses", f"PKR {summary['expenses']:,.2f}")
        with col3:
            st.metric("Vendor Payments", f"PKR {summary['vendor_payments']:,.2f}")

        # Close shift form
        with st.form("close_shift_form"):
            closing_cash = st.number_input("Closing Cash (PKR)", min_value=0.0, step=100.0, format="%.2f")
            if st.form_submit_button("Close Shift"):
                if closing_cash <= 0:
                    st.error("Please enter closing cash amount.")
                else:
                    success, msg, _ = shift_mgr.close_shift(current['id'], closing_cash, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.warning(f"No open {selected_shift} shift.")
        if st.button(f"Open {selected_shift} Shift"):
            success, msg, _ = shift_mgr.open_shift(selected_shift, user['id'])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # Show past shifts for this shift type (recent 5)
    st.subheader("Recent Closed Shifts")
    shifts = shift_mgr.get_shifts_in_date_range(
        start_date=date.today().replace(day=1),  # from first of month
        end_date=date.today(),
        user=user
    )
    # Filter by selected shift
    shifts = [s for s in shifts if s['shift_name'] == selected_shift and s['status'] == 'closed']
    if shifts:
        df = pd.DataFrame(shifts)
        df_display = df[['opening_date', 'closing_date', 'opening_cash', 'closing_cash', 'cash_difference']]
        st.dataframe(df_display, use_container_width=True)
    else:
        st.info("No closed shifts found.")

# ============================================
# SALES ENTRY
# ============================================
def show_sales_entry():
    st.header("💰 Sales Entry")
    user = st.session_state.user
    shift_mgr = ShiftManager()
    sales_mgr = SalesManager()

    # Determine current shift for user
    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current_shift = shift_mgr.get_current_shift(user['shift'])
        if not current_shift:
            st.error(f"No open {user['shift']} shift. Please open a shift first.")
            return
        shift_id = current_shift['id']
    else:
        # For other roles, allow selecting shift
        shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts today.")
            return
        shift_options = {f"{s['shift_name']} (opened {s['opening_time']})": s['id'] for s in open_shifts}
        selected = st.selectbox("Select Shift", list(shift_options.keys()))
        shift_id = shift_options[selected]

    with st.form("sales_form"):
        col1, col2 = st.columns(2)
        with col1:
            invoice = st.text_input("Invoice Number*")
            amount = st.number_input("Amount (PKR)*", min_value=0.0, step=100.0, format="%.2f")
        with col2:
            sale_date = st.date_input("Date*", value=date.today())
            notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Sale")
        if submitted:
            if not invoice or amount <= 0:
                st.error("Invoice number and amount are required.")
            else:
                sale_data = {
                    'shift_id': shift_id,
                    'invoice_number': invoice,
                    'sale_date': sale_date.isoformat(),
                    'sale_time': datetime.now().time().isoformat(),
                    'amount': amount,
                    'notes': notes
                }
                success, msg = sales_mgr.add_sale(sale_data, user['id'])
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # Show recent sales for this shift
    st.subheader("Recent Sales")
    sales = sales_mgr.get_sales(shift_id=shift_id, limit=10)
    if sales:
        df = pd.DataFrame(sales)
        st.dataframe(df[['sale_date', 'invoice_number', 'amount', 'notes']], use_container_width=True)
    else:
        st.info("No sales recorded yet.")

# ============================================
# EXPENSE HEADS MASTER
# ============================================
def show_expense_heads():
    st.header("📋 Expense Heads")
    ehm = ExpenseHeadManager()
    heads = ehm.get_all_heads(include_inactive=True)

    with st.expander("➕ Add New Head", expanded=False):
        with st.form("add_head_form"):
            head_name = st.text_input("Head Name*")
            description = st.text_area("Description")
            submitted = st.form_submit_button("Create")
            if submitted:
                if not head_name:
                    st.error("Head name is required.")
                else:
                    data = {'head_name': head_name, 'description': description}
                    success, msg = ehm.create_head(data, st.session_state.user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    st.subheader("Existing Heads")
    if heads:
        df = pd.DataFrame(heads)
        df_display = df[['head_name', 'description', 'is_active']]
        st.dataframe(df_display, use_container_width=True)

        # Enable/Disable
        st.subheader("Toggle Status")
        head_options = {h['head_name']: h['id'] for h in heads}
        selected_head = st.selectbox("Select Head", list(head_options.keys()))
        head_id = head_options[selected_head]
        selected = next(h for h in heads if h['id'] == head_id)
        current_status = selected['is_active']
        new_status = not current_status
        if st.button(f"{'Enable' if not current_status else 'Disable'} Head"):
            success, msg = ehm.toggle_active(head_id, new_status)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("No expense heads found.")

# ============================================
# EXPENSE ENTRY
# ============================================
def show_expense_entry():
    st.header("💸 Expense Entry")
    user = st.session_state.user
    shift_mgr = ShiftManager()
    exp_mgr = ExpensesManager()
    ehm = ExpenseHeadManager()

    # Get current shift
    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current_shift = shift_mgr.get_current_shift(user['shift'])
        if not current_shift:
            st.error(f"No open {user['shift']} shift. Please open a shift first.")
            return
        shift_id = current_shift['id']
    else:
        shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts today.")
            return
        shift_options = {f"{s['shift_name']} (opened {s['opening_time']})": s['id'] for s in open_shifts}
        selected = st.selectbox("Select Shift", list(shift_options.keys()))
        shift_id = shift_options[selected]

    # Get active expense heads
    heads = ehm.get_all_heads(include_inactive=False)
    head_dict = {h['head_name']: h['id'] for h in heads}

    with st.form("expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            head = st.selectbox("Expense Head*", list(head_dict.keys()))
            amount = st.number_input("Amount (PKR)*", min_value=0.0, step=100.0, format="%.2f")
        with col2:
            exp_date = st.date_input("Date*", value=date.today())
            description = st.text_area("Description")
        submitted = st.form_submit_button("Add Expense")
        if submitted:
            if not head or amount <= 0:
                st.error("Please select head and enter amount.")
            else:
                exp_data = {
                    'shift_id': shift_id,
                    'expense_head_id': head_dict[head],
                    'expense_date': exp_date.isoformat(),
                    'expense_time': datetime.now().time().isoformat(),
                    'amount': amount,
                    'description': description
                }
                success, msg = exp_mgr.add_expense(exp_data, user['id'])
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # Show recent expenses for this shift
    st.subheader("Recent Expenses")
    expenses = exp_mgr.get_expenses(shift_id=shift_id, limit=10)
    if expenses:
        df = pd.DataFrame(expenses)
        # Extract head name
        df['head_name'] = df['expense_heads'].apply(lambda x: x['head_name'] if x else '')
        st.dataframe(df[['expense_date', 'head_name', 'amount', 'description']], use_container_width=True)
    else:
        st.info("No expenses recorded yet.")

# ============================================
# VENDOR MASTER
# ============================================
def show_vendor_master():
    st.header("🏢 Vendor Master")
    vm = VendorManager()
    vendors = vm.get_all_vendors(include_inactive=True)

    with st.expander("➕ Add New Vendor", expanded=False):
        with st.form("add_vendor_form"):
            col1, col2 = st.columns(2)
            with col1:
                vendor_name = st.text_input("Vendor Name*")
                contact_person = st.text_input("Contact Person")
                phone = st.text_input("Phone")
            with col2:
                email = st.text_input("Email")
                address = st.text_area("Address")
                opening_balance = st.number_input("Opening Balance (PKR)", value=0.0, step=100.0, format="%.2f")
            submitted = st.form_submit_button("Create")
            if submitted:
                if not vendor_name:
                    st.error("Vendor name is required.")
                else:
                    data = {
                        'vendor_name': vendor_name,
                        'contact_person': contact_person,
                        'phone': phone,
                        'email': email,
                        'address': address,
                        'opening_balance': opening_balance
                    }
                    success, msg = vm.create_vendor(data, st.session_state.user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    st.subheader("Existing Vendors")
    if vendors:
        df = pd.DataFrame(vendors)
        df_display = df[['vendor_name', 'contact_person', 'phone', 'current_balance', 'is_active']]
        st.dataframe(df_display, use_container_width=True)

        # Toggle active
        st.subheader("Toggle Status")
        vendor_options = {v['vendor_name']: v['id'] for v in vendors}
        selected_vendor = st.selectbox("Select Vendor", list(vendor_options.keys()))
        vendor_id = vendor_options[selected_vendor]
        selected = next(v for v in vendors if v['id'] == vendor_id)
        current_status = selected['is_active']
        new_status = not current_status
        if st.button(f"{'Enable' if not current_status else 'Disable'} Vendor"):
            success, msg = vm.toggle_active(vendor_id, new_status)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("No vendors found.")

# ============================================
# VENDOR LEDGER (PURCHASE + PAYMENT)
# ============================================
def show_vendor_ledger():
    st.header("📒 Vendor Ledger")
    user = st.session_state.user
    vm = VendorManager()
    shift_mgr = ShiftManager()

    vendors = vm.get_all_vendors(include_inactive=False)
    if not vendors:
        st.info("No active vendors. Please add vendors first.")
        return

    vendor_dict = {v['vendor_name']: v['id'] for v in vendors}
    selected_vendor = st.selectbox("Select Vendor", list(vendor_dict.keys()))
    vendor_id = vendor_dict[selected_vendor]

    # Date range
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From Date", value=date.today().replace(day=1))
    with col2:
        end_date = st.date_input("To Date", value=date.today())

    # Show ledger
    ledger = vm.get_vendor_ledger(vendor_id, start_date, end_date)
    if ledger:
        df = pd.DataFrame(ledger)
        st.dataframe(df, use_container_width=True)

        # PDF Export
        if st.button("Export Ledger as PDF"):
            pdf_bytes = generate_pdf(df, f"Vendor Ledger - {selected_vendor}", "vendor_ledger.pdf")
            st.markdown(get_pdf_download_link(pdf_bytes, "vendor_ledger.pdf"), unsafe_allow_html=True)
    else:
        st.info("No transactions in this period.")

    st.divider()

    # Add Purchase / Payment forms
    # Determine current shift (similar to sales)
    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current_shift = shift_mgr.get_current_shift(user['shift'])
        if not current_shift:
            st.error(f"No open {user['shift']} shift. Cannot add transactions.")
            return
        shift_id = current_shift['id']
    else:
        shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts today. Cannot add transactions.")
            return
        shift_options = {f"{s['shift_name']} (opened {s['opening_time']})": s['id'] for s in open_shifts}
        selected = st.selectbox("Select Shift for Transaction", list(shift_options.keys()))
        shift_id = shift_options[selected]

    tab1, tab2 = st.tabs(["➕ Add Purchase", "💳 Add Payment"])

    with tab1:
        with st.form("purchase_form"):
            col1, col2 = st.columns(2)
            with col1:
                invoice = st.text_input("Invoice Number")
                amount = st.number_input("Purchase Amount*", min_value=0.0, step=100.0, format="%.2f")
            with col2:
                purch_date = st.date_input("Purchase Date", value=date.today())
                due_date = st.date_input("Due Date (optional)", value=None)
                notes = st.text_area("Notes")
            submitted = st.form_submit_button("Add Purchase")
            if submitted:
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'vendor_id': vendor_id,
                        'purchase_date': purch_date.isoformat(),
                        'purchase_time': datetime.now().time().isoformat(),
                        'invoice_number': invoice,
                        'amount': amount,
                        'due_date': due_date.isoformat() if due_date else None,
                        'notes': notes
                    }
                    success, msg = vm.add_purchase(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab2:
        with st.form("payment_form"):
            col1, col2 = st.columns(2)
            with col1:
                amount = st.number_input("Payment Amount*", min_value=0.0, step=100.0, format="%.2f")
            with col2:
                pay_date = st.date_input("Payment Date", value=date.today())
                notes = st.text_area("Notes")
            submitted = st.form_submit_button("Add Payment")
            if submitted:
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'vendor_id': vendor_id,
                        'payment_date': pay_date.isoformat(),
                        'payment_time': datetime.now().time().isoformat(),
                        'amount': amount,
                        'notes': notes
                    }
                    success, msg = vm.add_payment(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# ============================================
# PERSONAL LEDGER (WITHDRAWALS + INVESTMENTS)
# ============================================
def show_personal_ledger():
    st.header("💰 Personal Ledger (Withdrawals & Investments)")
    user = st.session_state.user
    plm = PersonalLedgerManager()
    shift_mgr = ShiftManager()

    # Check permissions
    if user['role'] not in ['Super User', 'Owner']:
        st.error("You do not have permission to manage personal ledger.")
        return

    # Determine current shift (similar to others)
    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current_shift = shift_mgr.get_current_shift(user['shift'])
        if not current_shift:
            st.error("No open shift. Cannot add transactions.")
            return
        shift_id = current_shift['id']
    else:
        shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts today.")
            return
        shift_options = {f"{s['shift_name']} (opened {s['opening_time']})": s['id'] for s in open_shifts}
        selected = st.selectbox("Select Shift", list(shift_options.keys()))
        shift_id = shift_options[selected]

    # Show current balance
    balance = plm.get_balance()
    st.metric("Current Personal Balance", f"PKR {balance:,.2f}")

    tab1, tab2 = st.tabs(["➕ Add Withdrawal", "➕ Add Investment"])

    with tab1:
        with st.form("withdrawal_form"):
            amount = st.number_input("Withdrawal Amount*", min_value=0.0, step=100.0, format="%.2f")
            description = st.text_area("Description")
            trans_date = st.date_input("Date", value=date.today())
            submitted = st.form_submit_button("Add Withdrawal")
            if submitted:
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'transaction_type': 'withdrawal',
                        'transaction_date': trans_date.isoformat(),
                        'transaction_time': datetime.now().time().isoformat(),
                        'amount': amount,
                        'description': description
                    }
                    success, msg = plm.add_transaction(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab2:
        with st.form("investment_form"):
            amount = st.number_input("Investment Amount*", min_value=0.0, step=100.0, format="%.2f")
            description = st.text_area("Description")
            trans_date = st.date_input("Date", value=date.today())
            submitted = st.form_submit_button("Add Investment")
            if submitted:
                if amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'transaction_type': 'investment',
                        'transaction_date': trans_date.isoformat(),
                        'transaction_time': datetime.now().time().isoformat(),
                        'amount': amount,
                        'description': description
                    }
                    success, msg = plm.add_transaction(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    # Show recent transactions
    st.subheader("Recent Transactions")
    trans = plm.get_transactions(start_date=date.today().replace(day=1), end_date=date.today())
    if trans:
        df = pd.DataFrame(trans)
        st.dataframe(df[['transaction_date', 'transaction_type', 'amount', 'description']], use_container_width=True)
    else:
        st.info("No transactions found.")

# ============================================
# REPORTS
# ============================================
def show_reports():
    st.header("📈 Reports")
    reports_mgr = ReportsManager()

    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=date.today().replace(day=1))
    with col2:
        end_date = st.date_input("End Date", value=date.today())

    report_type = st.selectbox("Select Report Type", [
        "Sales Report",
        "Expenses Report",
        "Vendor Ledger",
        "Personal Ledger",
        "Shift Summary"
    ])

    if report_type == "Sales Report":
        df = reports_mgr.get_sales_report(start_date, end_date, st.session_state.user)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            total = df['amount'].sum() if 'amount' in df.columns else 0
            st.metric("Total Sales", f"PKR {total:,.2f}")
            if st.button("Export as PDF"):
                pdf = generate_pdf(df, f"Sales Report {start_date} to {end_date}", "sales_report.pdf")
                st.markdown(get_pdf_download_link(pdf, "sales_report.pdf"), unsafe_allow_html=True)
        else:
            st.info("No sales data for selected period.")

    elif report_type == "Expenses Report":
        df = reports_mgr.get_expenses_report(start_date, end_date)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            total = df['amount'].sum() if 'amount' in df.columns else 0
            st.metric("Total Expenses", f"PKR {total:,.2f}")
            if st.button("Export as PDF"):
                pdf = generate_pdf(df, f"Expenses Report {start_date} to {end_date}", "expenses_report.pdf")
                st.markdown(get_pdf_download_link(pdf, "expenses_report.pdf"), unsafe_allow_html=True)
        else:
            st.info("No expense data for selected period.")

    elif report_type == "Vendor Ledger":
        vm = VendorManager()
        vendors = vm.get_all_vendors(include_inactive=False)
        if vendors:
            vendor_dict = {v['vendor_name']: v['id'] for v in vendors}
            selected_vendor = st.selectbox("Select Vendor", list(vendor_dict.keys()))
            vendor_id = vendor_dict[selected_vendor]
            ledger = vm.get_vendor_ledger(vendor_id, start_date, end_date)
            if ledger:
                df = pd.DataFrame(ledger)
                st.dataframe(df, use_container_width=True)
                if st.button("Export as PDF"):
                    pdf = generate_pdf(df, f"Vendor Ledger - {selected_vendor}", "vendor_ledger.pdf")
                    st.markdown(get_pdf_download_link(pdf, "vendor_ledger.pdf"), unsafe_allow_html=True)
            else:
                st.info("No transactions for this vendor in selected period.")
        else:
            st.info("No vendors found.")

    elif report_type == "Personal Ledger":
        plm = PersonalLedgerManager()
        trans = plm.get_transactions(start_date=start_date, end_date=end_date)
        if trans:
            df = pd.DataFrame(trans)
            st.dataframe(df, use_container_width=True)
            total_inv = df[df['transaction_type']=='investment']['amount'].sum()
            total_wd = df[df['transaction_type']=='withdrawal']['amount'].sum()
            st.metric("Net Personal Balance", f"PKR {total_inv - total_wd:,.2f}")
            if st.button("Export as PDF"):
                pdf = generate_pdf(df, f"Personal Ledger {start_date} to {end_date}", "personal_ledger.pdf")
                st.markdown(get_pdf_download_link(pdf, "personal_ledger.pdf"), unsafe_allow_html=True)
        else:
            st.info("No personal transactions in selected period.")

    elif report_type == "Shift Summary":
        shift_mgr = ShiftManager()
        shifts = shift_mgr.get_shifts_in_date_range(start_date, end_date, st.session_state.user)
        if shifts:
            df = pd.DataFrame(shifts)
            st.dataframe(df, use_container_width=True)
            if st.button("Export as PDF"):
                pdf = generate_pdf(df, f"Shift Summary {start_date} to {end_date}", "shift_summary.pdf")
                st.markdown(get_pdf_download_link(pdf, "shift_summary.pdf"), unsafe_allow_html=True)
        else:
            st.info("No shifts in selected period.")

# ============================================
# PDF SETTINGS
# ============================================
def show_pdf_settings():
    st.header("🖨️ PDF Customization")
    st.markdown("Customize the appearance of exported PDFs.")

    with st.form("pdf_settings_form"):
        col1, col2 = st.columns(2)
        with col1:
            primary_color = st.color_picker("Primary Color", value=st.session_state.pdf_settings['primary_color'])
            secondary_color = st.color_picker("Secondary Color", value=st.session_state.pdf_settings['secondary_color'])
        with col2:
            font_size = st.slider("Font Size", min_value=8, max_value=14, value=st.session_state.pdf_settings['font_size'])
            company_name = st.text_input("Company Name", value=st.session_state.pdf_settings['company_name'])

        submitted = st.form_submit_button("Save Settings")
        if submitted:
            st.session_state.pdf_settings = {
                'primary_color': primary_color,
                'secondary_color': secondary_color,
                'font_size': font_size,
                'company_name': company_name
            }
            st.success("PDF settings saved!")

# ============================================
# MY SHIFT (for shift users)
# ============================================
def show_my_shift():
    st.header("🕒 My Shift")
    user = st.session_state.user
    shift_mgr = ShiftManager()
    current = shift_mgr.get_current_shift(user['shift'])
    if current:
        st.success(f"Your {user['shift']} shift is currently OPEN.")
        st.write(f"Opened: {current['opening_date']} at {current['opening_time']}")
        st.write(f"Opening Cash: PKR {current['opening_cash']:,.2f}")

        # Show summary
        summary = shift_mgr.get_shift_summary(current['id'])
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Sales", f"PKR {summary['sales']:,.2f}")
        with col2:
            st.metric("Expenses", f"PKR {summary['expenses']:,.2f}")
        with col3:
            st.metric("Vendor Payments", f"PKR {summary['vendor_payments']:,.2f}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Withdrawals", f"PKR {summary['withdrawals']:,.2f}")
        with col2:
            st.metric("Investments", f"PKR {summary['investments']:,.2f}")
        with col3:
            expected = shift_mgr.calculate_expected_cash(current['id'])
            st.metric("Expected Cash", f"PKR {expected:,.2f}")

        # Close shift form
        with st.form("my_shift_close"):
            closing_cash = st.number_input("Closing Cash (PKR)", min_value=0.0, step=100.0, format="%.2f")
            if st.form_submit_button("Close My Shift"):
                if closing_cash <= 0:
                    st.error("Please enter closing cash.")
                else:
                    success, msg, _ = shift_mgr.close_shift(current['id'], closing_cash, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.warning(f"No open {user['shift']} shift.")
        if st.button(f"Open {user['shift']} Shift"):
            success, msg, _ = shift_mgr.open_shift(user['shift'], user['id'])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# ============================================
# MAIN APP LOGIC
# ============================================
def main():
    if not st.session_state.authenticated:
        login()
    else:
        sidebar_navigation()
        page = st.session_state.page

        if page == "Dashboard":
            show_dashboard()
        elif page == "User Management":
            show_user_management()
        elif page == "Shift Management":
            show_shift_management()
        elif page == "Sales Entry":
            show_sales_entry()
        elif page == "Expense Heads":
            show_expense_heads()
        elif page == "Expense Entry":
            show_expense_entry()
        elif page == "Vendor Master":
            show_vendor_master()
        elif page == "Vendor Ledger":
            show_vendor_ledger()
        elif page == "Personal Ledger":
            show_personal_ledger()
        elif page == "Reports":
            show_reports()
        elif page == "PDF Settings":
            show_pdf_settings()
        elif page == "My Shift":
            show_my_shift()
        else:
            st.header("Page under construction")

if __name__ == "__main__":
    main()
