# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import matplotlib.pyplot as plt

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
# PAGE CONFIG
# ============================================
st.set_page_config(
    page_title="Pharmacy ERP - Cash & Ledger",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# CUSTOM CSS (Enhanced UI/UX)
# ============================================
st.markdown("""
<style>
    /* Global */
    .main {
        background-color: #f8fafc;
    }
    h1, h2, h3 {
        color: #0f172a;
        font-weight: 600;
    }
    /* Metric cards */
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
        color: #0f172a;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.9rem;
        font-weight: 500;
        color: #64748b;
    }
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #f1f5f9 100%);
        padding: 1.5rem 1rem;
    }
    .sidebar .sidebar-content {
        background: transparent;
    }
    /* Buttons */
    .stButton > button {
        background-color: #3b82f6;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
        width: 100%;
    }
    .stButton > button:hover {
        background-color: #2563eb;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    /* Forms */
    .stForm {
        background-color: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border: 1px solid #e2e8f0;
        margin-bottom: 2rem;
    }
    /* Dataframes */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #e2e8f0;
    }
    .dataframe th {
        background-color: #f1f5f9;
        color: #0f172a;
        font-weight: 600;
        padding: 0.75rem !important;
    }
    .dataframe td {
        padding: 0.75rem !important;
        border-bottom: 1px solid #e2e8f0;
    }
    /* Expanders */
    .streamlit-expanderHeader {
        background-color: white;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        padding: 0.75rem 1rem;
        font-weight: 600;
        color: #0f172a;
    }
    .streamlit-expanderContent {
        background-color: white;
        border-radius: 0 0 8px 8px;
        border: 1px solid #e2e8f0;
        border-top: none;
        padding: 1rem;
    }
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    /* Alerts */
    .stAlert {
        border-radius: 8px;
        border-left-width: 4px;
    }
    /* Select boxes */
    div[data-baseweb="select"] > div {
        border-radius: 8px;
        border: 1px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# SESSION STATE
# ============================================
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.page = "Login"
    st.session_state.pdf_settings = {
        'primary_color': '#3b82f6',
        'secondary_color': '#10b981',
        'font_size': 10,
        'company_name': 'Pharmacy Store'
    }

# ============================================
# PDF GENERATION
# ============================================
def generate_pdf(dataframe: pd.DataFrame, title: str, filename: str) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    primary = st.session_state.pdf_settings['primary_color']
    secondary = st.session_state.pdf_settings['secondary_color']
    font_size = st.session_state.pdf_settings['font_size']
    company = st.session_state.pdf_settings['company_name']

    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor(primary))
    c.drawString(50, height - 50, company)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 70, title)
    c.drawString(50, height - 85, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

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

    table.wrapOn(c, width-100, height)
    table.drawOn(c, 50, height - 200 - len(data)*20)

    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def get_pdf_download_link(pdf_bytes: bytes, filename: str) -> str:
    b64 = base64.b64encode(pdf_bytes).decode()
    return f'<a href="data:application/octet-stream;base64,{b64}" download="{filename}" style="text-decoration: none; background-color: #3b82f6; color: white; padding: 0.5rem 1rem; border-radius: 8px; display: inline-block;">📥 Download PDF</a>'

# ============================================
# LOGIN
# ============================================
def login():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #0f172a;'>💊 Pharmacy ERP</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #64748b; margin-bottom: 2rem;'>Cash & Ledger Control System</p>", unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=True):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Login", use_container_width=True)
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
# LOGOUT
# ============================================
def logout():
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.page = "Login"
    st.rerun()

# ============================================
# SIDEBAR NAVIGATION (Enhanced)
# ============================================
def sidebar_navigation():
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <h2 style="color: #0f172a; margin-bottom: 0;">💊 Pharmacy ERP</h2>
            <p style="color: #64748b; font-size: 0.9rem;">Cash & Ledger</p>
        </div>
        """, unsafe_allow_html=True)

        user = st.session_state.user
        st.markdown(f"""
        <div style="background: white; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; border: 1px solid #e2e8f0;">
            <p style="margin: 0; color: #0f172a; font-weight: 600;">👤 {user['full_name']}</p>
            <p style="margin: 0; color: #64748b; font-size: 0.9rem;">{user['role']}</p>
            {f"<p style='margin: 0; color: #3b82f6; font-size: 0.9rem;'>Shift: {user['shift']}</p>" if user.get('shift') else ""}
        </div>
        """, unsafe_allow_html=True)

        role = user['role']
        menu_map = {}

        if role == 'Super User':
            menu_map = {
                "🏠 Dashboard": "Dashboard",
                "👥 User Management": "User Management",
                "🕒 Shift Management": "Shift Management",
                "💰 Sales Entry": "Sales Entry",
                "📋 Expense Heads": "Expense Heads",
                "💸 Expense Entry": "Expense Entry",
                "🏢 Vendor Master": "Vendor Master",
                "📒 Vendor Ledger": "Vendor Ledger",
                "💳 Personal Ledger": "Personal Ledger",
                "📊 Reports": "Reports",
                "📈 Profit & Loss": "Profit & Loss",
                "🖨️ PDF Settings": "PDF Settings"
            }
        elif role == 'Owner':
            menu_map = {
                "🏠 Dashboard": "Dashboard",
                "🕒 Shift Management": "Shift Management",
                "💰 Sales Entry": "Sales Entry",
                "📋 Expense Heads": "Expense Heads",
                "💸 Expense Entry": "Expense Entry",
                "🏢 Vendor Master": "Vendor Master",
                "📒 Vendor Ledger": "Vendor Ledger",
                "💳 Personal Ledger": "Personal Ledger",
                "📊 Reports": "Reports",
                "📈 Profit & Loss": "Profit & Loss",
                "🖨️ PDF Settings": "PDF Settings"
            }
        elif role == 'Accountant':
            menu_map = {
                "🏠 Dashboard": "Dashboard",
                "🕒 Shift Management": "Shift Management",
                "💰 Sales Entry": "Sales Entry",
                "📋 Expense Heads": "Expense Heads",
                "💸 Expense Entry": "Expense Entry",
                "🏢 Vendor Master": "Vendor Master",
                "📒 Vendor Ledger": "Vendor Ledger",
                "📊 Reports": "Reports",
                "📈 Profit & Loss": "Profit & Loss"
            }
        elif role in ['Morning User', 'Evening User', 'Night User']:
            menu_map = {
                "🏠 My Shift": "My Shift",
                "💰 Sales Entry": "Sales Entry",
                "💸 Expense Entry": "Expense Entry"
            }

        selected_label = st.selectbox("Navigation", list(menu_map.keys()), key="nav_select")
        st.session_state.page = menu_map[selected_label]

        st.divider()
        if st.button("Logout", use_container_width=True):
            logout()

# ============================================
# DASHBOARD (Enhanced with charts)
# ============================================
def show_dashboard():
    st.header("📊 Dashboard")
    user = st.session_state.user
    role = user['role']

    if role in ['Morning User', 'Evening User', 'Night User']:
        shift_mgr = ShiftManager()
        current = shift_mgr.get_current_shift(user['shift'])
        if current:
            st.subheader(f"Current {user['shift']} Shift")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Opening Cash", f"PKR {current['opening_cash']:,.2f}")
            with col2:
                expected = shift_mgr.calculate_expected_cash(current['id'])
                st.metric("Expected Cash", f"PKR {expected:,.2f}")
            with col3:
                st.metric("Status", current['status'].upper())

            summary = shift_mgr.get_shift_summary(current['id'])
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Sales", f"PKR {summary['sales']:,.2f}")
            with col2:
                st.metric("Expenses", f"PKR {summary['expenses']:,.2f}")
            with col3:
                st.metric("Payments", f"PKR {summary['vendor_payments']:,.2f}")
            with col4:
                st.metric("Net", f"PKR {summary['sales'] - summary['expenses'] - summary['vendor_payments']:,.2f}")

            sales_mgr = SalesManager()
            recent = sales_mgr.get_sales(shift_id=current['id'], limit=5)
            if recent:
                st.subheader("Recent Sales")
                df = pd.DataFrame(recent)
                st.dataframe(df[['sale_date', 'invoice_number', 'amount']], use_container_width=True, hide_index=True)
            else:
                st.info("No recent sales.")
        else:
            st.warning(f"No open {user['shift']} shift. Please open a shift from Shift Management.")
    else:
        reports = ReportsManager()
        today = date.today()
        summary = reports.get_daily_summary(today)

        st.subheader(f"📅 Summary for {today.strftime('%d %B %Y')}")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sales", f"PKR {summary['total_sales']:,.2f}")
        with col2:
            st.metric("Total Expenses", f"PKR {summary['total_expenses']:,.2f}")
        with col3:
            st.metric("Net Cash", f"PKR {summary['net_cash']:,.2f}")
        with col4:
            st.metric("Vendor Payable", f"PKR {summary['vendor_payable']:,.2f}")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Personal Balance", f"PKR {summary['personal_balance']:,.2f}")
        with col2:
            st.metric("Drawer Opening", "PKR 10,000.00")

        # Simple chart
        st.subheader("Recent Activity")
        sales_mgr = SalesManager()
        recent = sales_mgr.get_sales(limit=10)
        if recent:
            df = pd.DataFrame(recent)
            st.dataframe(df[['sale_date', 'invoice_number', 'amount']], use_container_width=True, hide_index=True)
        else:
            st.info("No recent sales.")

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
                shift = st.selectbox("Shift", ['', 'Morning', 'Evening', 'Night'])
                if shift == '':
                    shift = None
            submitted = st.form_submit_button("Create User", use_container_width=True)
            if submitted:
                if not username or not password or not full_name:
                    st.error("Please fill all required fields.")
                else:
                    data = {
                        'username': username,
                        'password': password,
                        'full_name': full_name,
                        'role': role,
                        'shift': shift
                    }
                    success, msg = um.create_user(data, st.session_state.user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    if users:
        df = pd.DataFrame(users)
        st.dataframe(df[['username', 'full_name', 'role', 'shift', 'is_active']], use_container_width=True, hide_index=True)

        with st.form("manage_user"):
            user_options = {u['username']: u['id'] for u in users}
            selected = st.selectbox("Select User", list(user_options.keys()))
            user_id = user_options[selected]
            selected_user = next(u for u in users if u['id'] == user_id)
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("Deactivate"):
                    if selected_user['id'] == st.session_state.user['id']:
                        st.error("Cannot deactivate yourself.")
                    else:
                        success, msg = um.deactivate_user(user_id)
                        st.success(msg) if success else st.error(msg)
                        st.rerun()
            with col2:
                if st.form_submit_button("Reactivate"):
                    success, msg = um.reactivate_user(user_id)
                    st.success(msg) if success else st.error(msg)
                    st.rerun()
    else:
        st.info("No users found.")

# ============================================
# SHIFT MANAGEMENT
# ============================================
def show_shift_management():
    st.header("🕒 Shift Management")
    user = st.session_state.user
    shift_mgr = ShiftManager()

    shifts = ['Morning', 'Evening', 'Night']
    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        shifts = [user['shift']]

    selected = st.selectbox("Select Shift", shifts)

    current = shift_mgr.get_current_shift(selected)
    if current:
        st.info(f"**{selected} shift is OPEN**")
        st.write(f"Opened: {current['opening_date']} {current['opening_time']}")
        st.write(f"Opening Cash: PKR {current['opening_cash']:,.2f}")

        summary = shift_mgr.get_shift_summary(current['id'])
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Sales", f"PKR {summary['sales']:,.2f}")
        with col2:
            st.metric("Expenses", f"PKR {summary['expenses']:,.2f}")
        with col3:
            st.metric("Payments", f"PKR {summary['vendor_payments']:,.2f}")

        with st.form("close_shift"):
            closing = st.number_input("Closing Cash (PKR)", min_value=0.0, step=100.0, format="%.2f")
            if st.form_submit_button("Close Shift", use_container_width=True):
                if closing <= 0:
                    st.error("Enter closing cash.")
                else:
                    success, msg, _ = shift_mgr.close_shift(current['id'], closing, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.warning(f"No open {selected} shift.")
        if st.button(f"Open {selected} Shift", use_container_width=True):
            success, msg, _ = shift_mgr.open_shift(selected, user['id'])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.subheader("Recent Closed Shifts")
    shifts_list = shift_mgr.get_shifts_in_date_range(
        start_date=date.today().replace(day=1),
        end_date=date.today(),
        user=user
    )
    closed = [s for s in shifts_list if s['shift_name'] == selected and s['status'] == 'closed']
    if closed:
        df = pd.DataFrame(closed)
        st.dataframe(df[['opening_date', 'closing_date', 'opening_cash', 'closing_cash', 'cash_difference']], use_container_width=True, hide_index=True)
    else:
        st.info("No closed shifts.")

# ============================================
# SALES ENTRY (with optional invoice)
# ============================================
def show_sales_entry():
    st.header("💰 Sales Entry")
    user = st.session_state.user
    shift_mgr = ShiftManager()
    sales_mgr = SalesManager()

    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current = shift_mgr.get_current_shift(user['shift'])
        if not current:
            st.error(f"No open {user['shift']} shift.")
            return
        shift_id = current['id']
    else:
        today_shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in today_shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts today.")
            return
        shift_options = {f"{s['shift_name']} ({s['opening_time']})": s['id'] for s in open_shifts}
        selected = st.selectbox("Select Shift", list(shift_options.keys()))
        shift_id = shift_options[selected]

    with st.form("sales_form"):
        col1, col2 = st.columns(2)
        with col1:
            invoice = st.text_input("Invoice Number (optional)")
            amount = st.number_input("Total Sales (PKR)*", min_value=0.0, step=100.0, format="%.2f")
        with col2:
            sale_date = st.date_input("Date", value=date.today())
            notes = st.text_area("Notes")
        submitted = st.form_submit_button("Record Sale", use_container_width=True)
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'shift_id': shift_id,
                    'invoice_number': invoice or f"SALE-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    'sale_date': sale_date.isoformat(),
                    'sale_time': datetime.now().time().isoformat(),
                    'amount': amount,
                    'notes': notes
                }
                success, msg = sales_mgr.add_sale(data, user['id'])
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    st.subheader("Recent Sales")
    sales = sales_mgr.get_sales(shift_id=shift_id, limit=10)
    if sales:
        df = pd.DataFrame(sales)
        st.dataframe(df[['sale_date', 'invoice_number', 'amount', 'notes']], use_container_width=True, hide_index=True)
    else:
        st.info("No sales recorded.")

# ============================================
# EXPENSE HEADS
# ============================================
def show_expense_heads():
    st.header("📋 Expense Heads")
    ehm = ExpenseHeadManager()
    heads = ehm.get_all_heads(include_inactive=True)

    with st.expander("➕ Add New Head", expanded=False):
        with st.form("add_head"):
            name = st.text_input("Head Name*")
            desc = st.text_area("Description")
            if st.form_submit_button("Create", use_container_width=True):
                if not name:
                    st.error("Head name required.")
                else:
                    success, msg = ehm.create_head({'head_name': name, 'description': desc}, st.session_state.user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    if heads:
        df = pd.DataFrame(heads)
        st.dataframe(df[['head_name', 'description', 'is_active']], use_container_width=True, hide_index=True)

        st.subheader("Toggle Status")
        head_options = {h['head_name']: h['id'] for h in heads}
        selected = st.selectbox("Select Head", list(head_options.keys()))
        head_id = head_options[selected]
        selected_head = next(h for h in heads if h['id'] == head_id)
        current = selected_head['is_active']
        if st.button(f"{'Disable' if current else 'Enable'} Head", use_container_width=True):
            success, msg = ehm.toggle_active(head_id, not current)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("No expense heads.")

# ============================================
# EXPENSE ENTRY
# ============================================
def show_expense_entry():
    st.header("💸 Expense Entry")
    user = st.session_state.user
    shift_mgr = ShiftManager()
    exp_mgr = ExpensesManager()
    ehm = ExpenseHeadManager()

    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current = shift_mgr.get_current_shift(user['shift'])
        if not current:
            st.error(f"No open {user['shift']} shift.")
            return
        shift_id = current['id']
    else:
        today_shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in today_shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts today.")
            return
        shift_options = {f"{s['shift_name']} ({s['opening_time']})": s['id'] for s in open_shifts}
        selected = st.selectbox("Select Shift", list(shift_options.keys()))
        shift_id = shift_options[selected]

    heads = ehm.get_all_heads(include_inactive=False)
    if not heads:
        st.warning("No active expense heads. Please add heads first.")
        return
    head_dict = {h['head_name']: h['id'] for h in heads}

    with st.form("expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            head = st.selectbox("Expense Head*", list(head_dict.keys()))
            amount = st.number_input("Amount (PKR)*", min_value=0.0, step=100.0, format="%.2f")
        with col2:
            exp_date = st.date_input("Date", value=date.today())
            description = st.text_area("Description")
        submitted = st.form_submit_button("Add Expense", use_container_width=True)
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'shift_id': shift_id,
                    'expense_head_id': head_dict[head],
                    'expense_date': exp_date.isoformat(),
                    'expense_time': datetime.now().time().isoformat(),
                    'amount': amount,
                    'description': description
                }
                success, msg = exp_mgr.add_expense(data, user['id'])
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    st.subheader("Recent Expenses")
    expenses = exp_mgr.get_expenses(shift_id=shift_id, limit=10)
    if expenses:
        df = pd.DataFrame(expenses)
        df['head'] = df['expense_heads'].apply(lambda x: x['head_name'] if x else '')
        st.dataframe(df[['expense_date', 'head', 'amount', 'description']], use_container_width=True, hide_index=True)
    else:
        st.info("No expenses recorded.")

# ============================================
# VENDOR MASTER
# ============================================
def show_vendor_master():
    st.header("🏢 Vendor Master")
    vm = VendorManager()
    vendors = vm.get_all_vendors(include_inactive=True)

    with st.expander("➕ Add New Vendor", expanded=False):
        with st.form("add_vendor"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Vendor Name*")
                contact = st.text_input("Contact Person")
                phone = st.text_input("Phone")
            with col2:
                email = st.text_input("Email")
                address = st.text_area("Address")
                opening = st.number_input("Opening Balance (PKR)", value=0.0, step=100.0, format="%.2f")
            if st.form_submit_button("Create", use_container_width=True):
                if not name:
                    st.error("Vendor name required.")
                else:
                    data = {
                        'vendor_name': name,
                        'contact_person': contact,
                        'phone': phone,
                        'email': email,
                        'address': address,
                        'opening_balance': opening
                    }
                    success, msg = vm.create_vendor(data, st.session_state.user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    if vendors:
        df = pd.DataFrame(vendors)
        st.dataframe(df[['vendor_name', 'contact_person', 'phone', 'current_balance', 'is_active']], use_container_width=True, hide_index=True)

        st.subheader("Toggle Status")
        vendor_options = {v['vendor_name']: v['id'] for v in vendors}
        selected = st.selectbox("Select Vendor", list(vendor_options.keys()))
        vendor_id = vendor_options[selected]
        selected_vendor = next(v for v in vendors if v['id'] == vendor_id)
        current = selected_vendor['is_active']
        if st.button(f"{'Disable' if current else 'Enable'} Vendor", use_container_width=True):
            success, msg = vm.toggle_active(vendor_id, not current)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
    else:
        st.info("No vendors.")

# ============================================
# VENDOR LEDGER
# ============================================
def show_vendor_ledger():
    st.header("📒 Vendor Ledger")
    user = st.session_state.user
    vm = VendorManager()
    shift_mgr = ShiftManager()

    vendors = vm.get_all_vendors(include_inactive=False)
    if not vendors:
        st.info("No active vendors.")
        return

    vendor_dict = {v['vendor_name']: v['id'] for v in vendors}
    selected = st.selectbox("Select Vendor", list(vendor_dict.keys()))
    vendor_id = vendor_dict[selected]

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("From", value=date.today().replace(day=1))
    with col2:
        end = st.date_input("To", value=date.today())

    ledger = vm.get_vendor_ledger(vendor_id, start, end)
    if ledger:
        df = pd.DataFrame(ledger)
        st.dataframe(df, use_container_width=True, hide_index=True)
        if st.button("Export PDF", use_container_width=True):
            pdf = generate_pdf(df, f"Ledger - {selected}", "vendor_ledger.pdf")
            st.markdown(get_pdf_download_link(pdf, "vendor_ledger.pdf"), unsafe_allow_html=True)
    else:
        st.info("No transactions.")

    st.divider()

    # Determine shift for adding transactions
    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current = shift_mgr.get_current_shift(user['shift'])
        if not current:
            st.error("No open shift.")
            return
        shift_id = current['id']
    else:
        today_shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in today_shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts.")
            return
        shift_options = {f"{s['shift_name']} ({s['opening_time']})": s['id'] for s in open_shifts}
        shift_choice = st.selectbox("Select Shift for Transaction", list(shift_options.keys()), key="shift_tx")
        shift_id = shift_options[shift_choice]

    tab1, tab2 = st.tabs(["➕ Add Purchase", "💳 Add Payment"])

    with tab1:
        with st.form("purchase_form"):
            col1, col2 = st.columns(2)
            with col1:
                inv = st.text_input("Invoice")
                amt = st.number_input("Amount*", min_value=0.0, step=100.0, format="%.2f")
            with col2:
                pdate = st.date_input("Date", value=date.today())
                due = st.date_input("Due Date", value=None)
                notes = st.text_area("Notes")
            if st.form_submit_button("Add Purchase", use_container_width=True):
                if amt <= 0:
                    st.error("Amount must be > 0.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'vendor_id': vendor_id,
                        'purchase_date': pdate.isoformat(),
                        'purchase_time': datetime.now().time().isoformat(),
                        'invoice_number': inv,
                        'amount': amt,
                        'due_date': due.isoformat() if due else None,
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
                amt = st.number_input("Amount*", min_value=0.0, step=100.0, format="%.2f")
            with col2:
                pdate = st.date_input("Date", value=date.today())
                notes = st.text_area("Notes")
            if st.form_submit_button("Add Payment", use_container_width=True):
                if amt <= 0:
                    st.error("Amount must be > 0.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'vendor_id': vendor_id,
                        'payment_date': pdate.isoformat(),
                        'payment_time': datetime.now().time().isoformat(),
                        'amount': amt,
                        'notes': notes
                    }
                    success, msg = vm.add_payment(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

# ============================================
# PERSONAL LEDGER
# ============================================
def show_personal_ledger():
    st.header("💰 Personal Ledger")
    user = st.session_state.user
    if user['role'] not in ['Super User', 'Owner']:
        st.error("Access denied.")
        return

    plm = PersonalLedgerManager()
    shift_mgr = ShiftManager()

    if user['role'] in ['Morning User', 'Evening User', 'Night User']:
        current = shift_mgr.get_current_shift(user['shift'])
        if not current:
            st.error("No open shift.")
            return
        shift_id = current['id']
    else:
        today_shifts = shift_mgr.get_shifts_in_date_range(date.today(), date.today())
        open_shifts = [s for s in today_shifts if s['status'] == 'open']
        if not open_shifts:
            st.error("No open shifts.")
            return
        shift_options = {f"{s['shift_name']} ({s['opening_time']})": s['id'] for s in open_shifts}
        shift_choice = st.selectbox("Select Shift", list(shift_options.keys()), key="personal_shift")
        shift_id = shift_options[shift_choice]

    balance = plm.get_balance()
    st.metric("Current Balance", f"PKR {balance:,.2f}")

    tab1, tab2 = st.tabs(["➕ Withdrawal", "➕ Investment"])

    with tab1:
        with st.form("withdrawal"):
            amt = st.number_input("Amount*", min_value=0.0, step=100.0, format="%.2f")
            desc = st.text_area("Description")
            tdate = st.date_input("Date", value=date.today())
            if st.form_submit_button("Add Withdrawal", use_container_width=True):
                if amt <= 0:
                    st.error("Amount must be > 0.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'transaction_type': 'withdrawal',
                        'transaction_date': tdate.isoformat(),
                        'transaction_time': datetime.now().time().isoformat(),
                        'amount': amt,
                        'description': desc
                    }
                    success, msg = plm.add_transaction(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab2:
        with st.form("investment"):
            amt = st.number_input("Amount*", min_value=0.0, step=100.0, format="%.2f")
            desc = st.text_area("Description")
            tdate = st.date_input("Date", value=date.today())
            if st.form_submit_button("Add Investment", use_container_width=True):
                if amt <= 0:
                    st.error("Amount must be > 0.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'transaction_type': 'investment',
                        'transaction_date': tdate.isoformat(),
                        'transaction_time': datetime.now().time().isoformat(),
                        'amount': amt,
                        'description': desc
                    }
                    success, msg = plm.add_transaction(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    st.subheader("Recent Transactions")
    trans = plm.get_transactions(start_date=date.today().replace(day=1), end_date=date.today(), limit=20)
    if trans:
        df = pd.DataFrame(trans)
        st.dataframe(df[['transaction_date', 'transaction_type', 'amount', 'description']], use_container_width=True, hide_index=True)
    else:
        st.info("No transactions.")

# ============================================
# REPORTS (with filter by head)
# ============================================
def show_reports():
    st.header("📊 Reports")
    reports = ReportsManager()

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Start", value=date.today().replace(day=1))
    with col2:
        end = st.date_input("End", value=date.today())

    rtype = st.selectbox("Report Type", ["Sales", "Expenses", "Vendor Ledger", "Personal Ledger", "Shift Summary"])

    if rtype == "Sales":
        df = reports.get_sales_report(start, end, st.session_state.user)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            total = df['amount'].sum()
            st.metric("Total Sales", f"PKR {total:,.2f}")
            if st.button("Export PDF", use_container_width=True):
                pdf = generate_pdf(df, f"Sales {start} to {end}", "sales.pdf")
                st.markdown(get_pdf_download_link(pdf, "sales.pdf"), unsafe_allow_html=True)
        else:
            st.info("No data.")

    elif rtype == "Expenses":
        df = reports.get_expenses_report(start, end)
        if not df.empty:
            heads = df['head_name'].unique() if 'head_name' in df.columns else []
            selected = st.multiselect("Filter by Head", heads, default=heads)
            if selected:
                df = df[df['head_name'].isin(selected)]
            st.dataframe(df, use_container_width=True, hide_index=True)
            total = df['amount'].sum()
            st.metric("Total Expenses", f"PKR {total:,.2f}")
            if st.button("Export PDF", use_container_width=True):
                pdf = generate_pdf(df, f"Expenses {start} to {end}", "expenses.pdf")
                st.markdown(get_pdf_download_link(pdf, "expenses.pdf"), unsafe_allow_html=True)
        else:
            st.info("No data.")

    elif rtype == "Vendor Ledger":
        vm = VendorManager()
        vendors = vm.get_all_vendors(include_inactive=False)
        if vendors:
            vendor_dict = {v['vendor_name']: v['id'] for v in vendors}
            selected = st.selectbox("Select Vendor", list(vendor_dict.keys()))
            vendor_id = vendor_dict[selected]
            ledger = vm.get_vendor_ledger(vendor_id, start, end)
            if ledger:
                df = pd.DataFrame(ledger)
                st.dataframe(df, use_container_width=True, hide_index=True)
                if st.button("Export PDF", use_container_width=True):
                    pdf = generate_pdf(df, f"Ledger {selected} {start} to {end}", "vendor_ledger.pdf")
                    st.markdown(get_pdf_download_link(pdf, "vendor_ledger.pdf"), unsafe_allow_html=True)
            else:
                st.info("No transactions.")
        else:
            st.info("No vendors.")

    elif rtype == "Personal Ledger":
        plm = PersonalLedgerManager()
        trans = plm.get_transactions(start_date=start, end_date=end)
        if trans:
            df = pd.DataFrame(trans)
            st.dataframe(df, use_container_width=True, hide_index=True)
            inv = df[df['transaction_type']=='investment']['amount'].sum()
            wd = df[df['transaction_type']=='withdrawal']['amount'].sum()
            st.metric("Net", f"PKR {inv - wd:,.2f}")
            if st.button("Export PDF", use_container_width=True):
                pdf = generate_pdf(df, f"Personal Ledger {start} to {end}", "personal.pdf")
                st.markdown(get_pdf_download_link(pdf, "personal.pdf"), unsafe_allow_html=True)
        else:
            st.info("No transactions.")

    elif rtype == "Shift Summary":
        shift_mgr = ShiftManager()
        shifts = shift_mgr.get_shifts_in_date_range(start, end, st.session_state.user)
        if shifts:
            df = pd.DataFrame(shifts)
            st.dataframe(df, use_container_width=True, hide_index=True)
            if st.button("Export PDF", use_container_width=True):
                pdf = generate_pdf(df, f"Shifts {start} to {end}", "shifts.pdf")
                st.markdown(get_pdf_download_link(pdf, "shifts.pdf"), unsafe_allow_html=True)
        else:
            st.info("No shifts.")

# ============================================
# PROFIT & LOSS
# ============================================
def show_profit_loss():
    st.header("📈 Profit & Loss Statement")

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("From", value=date.today().replace(day=1))
    with col2:
        end = st.date_input("To", value=date.today())

    col1, col2 = st.columns(2)
    with col1:
        sales = st.number_input("Total Sales (PKR)", min_value=0.0, step=1000.0, format="%.2f")
    with col2:
        cogs = st.number_input("Cost of Goods Sold (PKR)", min_value=0.0, step=1000.0, format="%.2f")

    if st.button("Calculate P&L", use_container_width=True):
        reports = ReportsManager()
        exp_df = reports.get_expenses_report(start, end)
        total_exp = exp_df['amount'].sum() if not exp_df.empty else 0

        gross = sales - cogs
        net = gross - total_exp

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Gross Profit", f"PKR {gross:,.2f}")
        with col2:
            st.metric("Total Expenses", f"PKR {total_exp:,.2f}")
        with col3:
            st.metric("Net Profit", f"PKR {net:,.2f}")

        if not exp_df.empty:
            with st.expander("Expenses Breakdown"):
                st.dataframe(exp_df[['expense_date', 'head_name', 'amount', 'description']], use_container_width=True, hide_index=True)

        if st.button("Export P&L as PDF", use_container_width=True):
            data = {
                'Description': ['Sales', 'COGS', 'Gross Profit', 'Expenses', 'Net Profit'],
                'Amount (PKR)': [sales, cogs, gross, total_exp, net]
            }
            df = pd.DataFrame(data)
            pdf = generate_pdf(df, f"P&L {start} to {end}", "pnl.pdf")
            st.markdown(get_pdf_download_link(pdf, "pnl.pdf"), unsafe_allow_html=True)

# ============================================
# PDF SETTINGS
# ============================================
def show_pdf_settings():
    st.header("🖨️ PDF Settings")

    with st.form("pdf_settings"):
        col1, col2 = st.columns(2)
        with col1:
            primary = st.color_picker("Primary Color", value=st.session_state.pdf_settings['primary_color'])
            secondary = st.color_picker("Secondary Color", value=st.session_state.pdf_settings['secondary_color'])
        with col2:
            font = st.slider("Font Size", 8, 14, st.session_state.pdf_settings['font_size'])
            company = st.text_input("Company Name", value=st.session_state.pdf_settings['company_name'])

        if st.form_submit_button("Save Settings", use_container_width=True):
            st.session_state.pdf_settings = {
                'primary_color': primary,
                'secondary_color': secondary,
                'font_size': font,
                'company_name': company
            }
            st.success("Settings saved!")

# ============================================
# MY SHIFT
# ============================================
def show_my_shift():
    st.header("🕒 My Shift")
    user = st.session_state.user
    shift_mgr = ShiftManager()
    current = shift_mgr.get_current_shift(user['shift'])
    if current:
        st.success(f"Your {user['shift']} shift is OPEN")
        st.write(f"Opened: {current['opening_date']} {current['opening_time']}")
        st.write(f"Opening Cash: PKR {current['opening_cash']:,.2f}")

        summary = shift_mgr.get_shift_summary(current['id'])
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Sales", f"PKR {summary['sales']:,.2f}")
        with col2:
            st.metric("Expenses", f"PKR {summary['expenses']:,.2f}")
        with col3:
            st.metric("Payments", f"PKR {summary['vendor_payments']:,.2f}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Withdrawals", f"PKR {summary['withdrawals']:,.2f}")
        with col2:
            st.metric("Investments", f"PKR {summary['investments']:,.2f}")
        with col3:
            expected = shift_mgr.calculate_expected_cash(current['id'])
            st.metric("Expected Cash", f"PKR {expected:,.2f}")

        with st.form("close_my_shift"):
            closing = st.number_input("Closing Cash (PKR)", min_value=0.0, step=100.0, format="%.2f")
            if st.form_submit_button("Close Shift", use_container_width=True):
                if closing <= 0:
                    st.error("Enter closing cash.")
                else:
                    success, msg, _ = shift_mgr.close_shift(current['id'], closing, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    else:
        st.warning(f"No open {user['shift']} shift.")
        if st.button(f"Open {user['shift']} Shift", use_container_width=True):
            success, msg, _ = shift_mgr.open_shift(user['shift'], user['id'])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# ============================================
# MAIN
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
        elif page == "Profit & Loss":
            show_profit_loss()
        elif page == "PDF Settings":
            show_pdf_settings()
        elif page == "My Shift":
            show_my_shift()
        else:
            st.header("Page under construction")

if __name__ == "__main__":
    main()
