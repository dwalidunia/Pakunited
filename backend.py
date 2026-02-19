# backend.py
import os
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any, Tuple
from supabase import create_client, Client
import streamlit as st
import pandas as pd

# ============================================
# SUPABASE CONNECTION (Singleton)
# ============================================
class SupabaseConnection:
    _instance: Optional[Client] = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
            cls._instance = create_client(url, key)
        return cls._instance


# ============================================
# USER MANAGER
# ============================================
class UserManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        try:
            response = self.supabase.table('users')\
                .select('*')\
                .eq('username', username)\
                .eq('password', password)\
                .eq('is_active', True)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            st.error(f"Authentication error: {e}")
            return None

    def get_all_users(self, include_inactive: bool = False) -> List[Dict]:
        try:
            query = self.supabase.table('users').select('*')
            if not include_inactive:
                query = query.eq('is_active', True)
            response = query.order('full_name').execute()
            return response.data
        except Exception as e:
            st.error(f"Error fetching users: {e}")
            return []

    def create_user(self, user_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            existing = self.supabase.table('users')\
                .select('id')\
                .eq('username', user_data['username'])\
                .execute()
            if existing.data:
                return False, "Username already exists."

            user_data['created_by'] = created_by
            user_data['created_at'] = datetime.now().isoformat()
            user_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('users').insert(user_data).execute()
            return True, "User created successfully."
        except Exception as e:
            return False, f"Error creating user: {e}"

    def update_user(self, user_id: str, user_data: Dict) -> Tuple[bool, str]:
        try:
            user_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('users')\
                .update(user_data)\
                .eq('id', user_id)\
                .execute()
            return True, "User updated successfully."
        except Exception as e:
            return False, f"Error updating user: {e}"

    def deactivate_user(self, user_id: str) -> Tuple[bool, str]:
        try:
            self.supabase.table('users')\
                .update({'is_active': False, 'updated_at': datetime.now().isoformat()})\
                .eq('id', user_id)\
                .execute()
            return True, "User deactivated successfully."
        except Exception as e:
            return False, f"Error deactivating user: {e}"

    def reactivate_user(self, user_id: str) -> Tuple[bool, str]:
        try:
            self.supabase.table('users')\
                .update({'is_active': True, 'updated_at': datetime.now().isoformat()})\
                .eq('id', user_id)\
                .execute()
            return True, "User reactivated successfully."
        except Exception as e:
            return False, f"Error reactivating user: {e}"

    @staticmethod
    def can_edit_shift(user: Dict, target_shift: str) -> bool:
        role = user['role']
        if role == 'Super User' or role == 'Accountant':
            return True
        if role in ['Morning User', 'Evening User', 'Night User']:
            return user.get('shift') == target_shift
        return False

    @staticmethod
    def can_delete(user: Dict) -> bool:
        return user['role'] in ['Super User', 'Owner']

    @staticmethod
    def can_manage_withdrawals(user: Dict) -> bool:
        return user['role'] in ['Super User', 'Owner']

    @staticmethod
    def can_manage_vendor_payments(user: Dict) -> bool:
        return user['role'] in ['Super User', 'Owner', 'Accountant']


# ============================================
# SHIFT MANAGER
# ============================================
class ShiftManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()

    def get_current_shift(self, shift_name: str) -> Optional[Dict]:
        try:
            response = self.supabase.table('shifts')\
                .select('*')\
                .eq('shift_name', shift_name)\
                .eq('status', 'open')\
                .order('opening_date', desc=True)\
                .limit(1)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            st.error(f"Error fetching current shift: {e}")
            return None

    def open_shift(self, shift_name: str, opened_by: str) -> Tuple[bool, str, Optional[Dict]]:
        try:
            if self.get_current_shift(shift_name):
                return False, f"{shift_name} shift is already open.", None

            data = {
                'shift_name': shift_name,
                'opening_date': date.today().isoformat(),
                'opening_time': datetime.now().time().isoformat(),
                'opening_cash': 10000.00,
                'opened_by': opened_by,
                'status': 'open'
            }
            response = self.supabase.table('shifts').insert(data).execute()
            return True, f"{shift_name} shift opened successfully.", response.data[0]
        except Exception as e:
            return False, f"Error opening shift: {e}", None

    def close_shift(self, shift_id: str, closing_cash: float, closed_by: str) -> Tuple[bool, str, Optional[Dict]]:
        try:
            shift_resp = self.supabase.table('shifts').select('*').eq('id', shift_id).execute()
            if not shift_resp.data:
                return False, "Shift not found.", None

            expected = self.calculate_expected_cash(shift_id)
            difference = closing_cash - expected

            update_data = {
                'closing_date': date.today().isoformat(),
                'closing_time': datetime.now().time().isoformat(),
                'closing_cash': closing_cash,
                'expected_cash': expected,
                'cash_difference': difference,
                'closed_by': closed_by,
                'status': 'closed',
                'updated_at': datetime.now().isoformat()
            }
            response = self.supabase.table('shifts')\
                .update(update_data)\
                .eq('id', shift_id)\
                .execute()
            return True, f"Shift closed. Difference: PKR {difference:,.2f}", response.data[0]
        except Exception as e:
            return False, f"Error closing shift: {e}", None

    def calculate_expected_cash(self, shift_id: str) -> float:
        try:
            shift = self.supabase.table('shifts').select('opening_cash').eq('id', shift_id).execute()
            opening = shift.data[0]['opening_cash'] if shift.data else 10000.0

            sales = sum(s['amount'] for s in self.supabase.table('sales').select('amount').eq('shift_id', shift_id).execute().data)
            expenses = sum(e['amount'] for e in self.supabase.table('expenses').select('amount').eq('shift_id', shift_id).execute().data)
            payments = sum(p['amount'] for p in self.supabase.table('vendor_payments').select('amount').eq('shift_id', shift_id).execute().data)
            withdrawals = sum(w['amount'] for w in self.supabase.table('personal_transactions').select('amount').eq('shift_id', shift_id).eq('transaction_type', 'withdrawal').execute().data)
            investments = sum(i['amount'] for i in self.supabase.table('personal_transactions').select('amount').eq('shift_id', shift_id).eq('transaction_type', 'investment').execute().data)

            return opening + sales - expenses - payments - withdrawals + investments
        except Exception as e:
            st.error(f"Error calculating expected cash: {e}")
            return 0.0

    def get_shift_summary(self, shift_id: str) -> Dict:
        summary = {'sales': 0, 'expenses': 0, 'vendor_purchases': 0,
                   'vendor_payments': 0, 'withdrawals': 0, 'investments': 0}
        try:
            summary['sales'] = sum(s['amount'] for s in self.supabase.table('sales').select('amount').eq('shift_id', shift_id).execute().data)
            summary['expenses'] = sum(e['amount'] for e in self.supabase.table('expenses').select('amount').eq('shift_id', shift_id).execute().data)
            summary['vendor_purchases'] = sum(p['amount'] for p in self.supabase.table('vendor_purchases').select('amount').eq('shift_id', shift_id).execute().data)
            summary['vendor_payments'] = sum(p['amount'] for p in self.supabase.table('vendor_payments').select('amount').eq('shift_id', shift_id).execute().data)
            for p in self.supabase.table('personal_transactions').select('transaction_type,amount').eq('shift_id', shift_id).execute().data:
                if p['transaction_type'] == 'withdrawal':
                    summary['withdrawals'] += p['amount']
                else:
                    summary['investments'] += p['amount']
            return summary
        except Exception as e:
            st.error(f"Error getting shift summary: {e}")
            return summary

    def get_shifts_in_date_range(self, start_date: date, end_date: date, user: Dict = None) -> List[Dict]:
        try:
            query = self.supabase.table('shifts')\
                .select('*, opened_by_user:opened_by(full_name), closed_by_user:closed_by(full_name)')\
                .gte('opening_date', start_date.isoformat())\
                .lte('opening_date', end_date.isoformat())\
                .order('opening_date', desc=True)

            if user and user['role'] in ['Morning User', 'Evening User', 'Night User']:
                query = query.eq('shift_name', user['shift'])

            return query.execute().data
        except Exception as e:
            st.error(f"Error fetching shifts: {e}")
            return []


# ============================================
# EXPENSE HEAD MANAGER
# ============================================
class ExpenseHeadManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()

    def get_all_heads(self, include_inactive: bool = False) -> List[Dict]:
        try:
            query = self.supabase.table('expense_heads').select('*')
            if not include_inactive:
                query = query.eq('is_active', True)
            return query.order('head_name').execute().data
        except Exception as e:
            st.error(f"Error fetching expense heads: {e}")
            return []

    def create_head(self, head_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            head_data['created_by'] = created_by
            head_data['created_at'] = datetime.now().isoformat()
            head_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('expense_heads').insert(head_data).execute()
            return True, "Expense head created."
        except Exception as e:
            return False, f"Error creating expense head: {e}"

    def update_head(self, head_id: str, head_data: Dict) -> Tuple[bool, str]:
        try:
            head_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('expense_heads').update(head_data).eq('id', head_id).execute()
            return True, "Expense head updated."
        except Exception as e:
            return False, f"Error updating expense head: {e}"

    def toggle_active(self, head_id: str, is_active: bool) -> Tuple[bool, str]:
        try:
            self.supabase.table('expense_heads')\
                .update({'is_active': is_active, 'updated_at': datetime.now().isoformat()})\
                .eq('id', head_id)\
                .execute()
            status = "enabled" if is_active else "disabled"
            return True, f"Expense head {status}."
        except Exception as e:
            return False, f"Error toggling expense head: {e}"


# ============================================
# VENDOR MANAGER
# ============================================
class VendorManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()

    def get_all_vendors(self, include_inactive: bool = False) -> List[Dict]:
        try:
            query = self.supabase.table('vendors').select('*')
            if not include_inactive:
                query = query.eq('is_active', True)
            return query.order('vendor_name').execute().data
        except Exception as e:
            st.error(f"Error fetching vendors: {e}")
            return []

    def create_vendor(self, vendor_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            vendor_data['current_balance'] = vendor_data.get('opening_balance', 0)
            vendor_data['created_by'] = created_by
            vendor_data['created_at'] = datetime.now().isoformat()
            vendor_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendors').insert(vendor_data).execute()
            return True, "Vendor created."
        except Exception as e:
            return False, f"Error creating vendor: {e}"

    def update_vendor(self, vendor_id: str, vendor_data: Dict) -> Tuple[bool, str]:
        try:
            vendor_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendors').update(vendor_data).eq('id', vendor_id).execute()
            return True, "Vendor updated."
        except Exception as e:
            return False, f"Error updating vendor: {e}"

    def toggle_active(self, vendor_id: str, is_active: bool) -> Tuple[bool, str]:
        try:
            self.supabase.table('vendors')\
                .update({'is_active': is_active, 'updated_at': datetime.now().isoformat()})\
                .eq('id', vendor_id)\
                .execute()
            status = "enabled" if is_active else "disabled"
            return True, f"Vendor {status}."
        except Exception as e:
            return False, f"Error toggling vendor: {e}"

    def add_purchase(self, purchase_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            purchase_data['created_by'] = created_by
            purchase_data['created_at'] = datetime.now().isoformat()
            purchase_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendor_purchases').insert(purchase_data).execute()
            return True, "Purchase added."
        except Exception as e:
            return False, f"Error adding purchase: {e}"

    def get_purchases(self, vendor_id: str = None, start_date: date = None, end_date: date = None, limit: int = None) -> List[Dict]:
        try:
            query = self.supabase.table('vendor_purchases')\
                .select('*, vendors(vendor_name), shifts(shift_name)')\
                .order('purchase_date', desc=True)
            if vendor_id:
                query = query.eq('vendor_id', vendor_id)
            if start_date:
                query = query.gte('purchase_date', start_date.isoformat())
            if end_date:
                query = query.lte('purchase_date', end_date.isoformat())
            if limit:
                query = query.limit(limit)
            return query.execute().data
        except Exception as e:
            st.error(f"Error fetching purchases: {e}")
            return []

    def add_payment(self, payment_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            payment_data['created_by'] = created_by
            payment_data['created_at'] = datetime.now().isoformat()
            payment_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendor_payments').insert(payment_data).execute()
            return True, "Payment added."
        except Exception as e:
            return False, f"Error adding payment: {e}"

    def get_payments(self, vendor_id: str = None, start_date: date = None, end_date: date = None, limit: int = None) -> List[Dict]:
        try:
            query = self.supabase.table('vendor_payments')\
                .select('*, vendors(vendor_name), shifts(shift_name)')\
                .order('payment_date', desc=True)
            if vendor_id:
                query = query.eq('vendor_id', vendor_id)
            if start_date:
                query = query.gte('payment_date', start_date.isoformat())
            if end_date:
                query = query.lte('payment_date', end_date.isoformat())
            if limit:
                query = query.limit(limit)
            return query.execute().data
        except Exception as e:
            st.error(f"Error fetching payments: {e}")
            return []

    def get_vendor_ledger(self, vendor_id: str, start_date: date, end_date: date) -> List[Dict]:
        try:
            purchases = self.supabase.table('vendor_purchases')\
                .select('purchase_date, amount, invoice_number, notes, shifts(shift_name)')\
                .eq('vendor_id', vendor_id)\
                .gte('purchase_date', start_date.isoformat())\
                .lte('purchase_date', end_date.isoformat())\
                .execute().data
            payments = self.supabase.table('vendor_payments')\
                .select('payment_date, amount, notes, shifts(shift_name)')\
                .eq('vendor_id', vendor_id)\
                .gte('payment_date', start_date.isoformat())\
                .lte('payment_date', end_date.isoformat())\
                .execute().data

            ledger = []
            for p in purchases:
                ledger.append({
                    'date': p['purchase_date'],
                    'type': 'Purchase',
                    'invoice': p.get('invoice_number', ''),
                    'debit': p['amount'],
                    'credit': 0,
                    'notes': p.get('notes', ''),
                    'shift': p['shifts']['shift_name'] if p['shifts'] else ''
                })
            for p in payments:
                ledger.append({
                    'date': p['payment_date'],
                    'type': 'Payment',
                    'invoice': '',
                    'debit': 0,
                    'credit': p['amount'],
                    'notes': p.get('notes', ''),
                    'shift': p['shifts']['shift_name'] if p['shifts'] else ''
                })

            ledger.sort(key=lambda x: x['date'])

            vendor_resp = self.supabase.table('vendors').select('opening_balance').eq('id', vendor_id).execute()
            opening = vendor_resp.data[0]['opening_balance'] if vendor_resp.data else 0

            balance = opening
            for entry in ledger:
                balance = balance + entry['debit'] - entry['credit']
                entry['balance'] = balance

            ledger.reverse()
            return ledger
        except Exception as e:
            st.error(f"Error fetching vendor ledger: {e}")
            return []

    def delete_transaction(self, table: str, transaction_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table(table).delete().eq('id', transaction_id).execute()
            return True, "Transaction deleted."
        except Exception as e:
            return False, f"Error deleting transaction: {e}"


# ============================================
# PERSONAL LEDGER MANAGER
# ============================================
class PersonalLedgerManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()

    def add_transaction(self, trans_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            trans_data['created_by'] = created_by
            trans_data['created_at'] = datetime.now().isoformat()
            trans_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('personal_transactions').insert(trans_data).execute()
            return True, f"{trans_data['transaction_type'].capitalize()} added."
        except Exception as e:
            return False, f"Error adding transaction: {e}"

    def get_transactions(self, trans_type: str = None, start_date: date = None, end_date: date = None, limit: int = None) -> List[Dict]:
        try:
            query = self.supabase.table('personal_transactions')\
                .select('*, shifts(shift_name), users(full_name)')\
                .order('transaction_date', desc=True)
            if trans_type:
                query = query.eq('transaction_type', trans_type)
            if start_date:
                query = query.gte('transaction_date', start_date.isoformat())
            if end_date:
                query = query.lte('transaction_date', end_date.isoformat())
            if limit:
                query = query.limit(limit)
            return query.execute().data
        except Exception as e:
            st.error(f"Error fetching personal transactions: {e}")
            return []

    def get_balance(self) -> float:
        try:
            inv = sum(i['amount'] for i in self.supabase.table('personal_transactions').select('amount').eq('transaction_type', 'investment').execute().data)
            wd = sum(w['amount'] for w in self.supabase.table('personal_transactions').select('amount').eq('transaction_type', 'withdrawal').execute().data)
            return inv - wd
        except Exception as e:
            st.error(f"Error calculating personal balance: {e}")
            return 0.0

    def delete_transaction(self, transaction_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table('personal_transactions').delete().eq('id', transaction_id).execute()
            return True, "Transaction deleted."
        except Exception as e:
            return False, f"Error deleting transaction: {e}"


# ============================================
# REPORTS MANAGER
# ============================================
class ReportsManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()
        self.shift_mgr = ShiftManager()
        self.vendor_mgr = VendorManager()
        self.personal_mgr = PersonalLedgerManager()

    def get_daily_summary(self, report_date: date) -> Dict:
        summary = {
            'total_sales': 0,
            'total_expenses': 0,
            'vendor_payments': 0,
            'withdrawals': 0,
            'investments': 0,
            'net_cash': 0,
            'vendor_payable': 0,
            'personal_balance': 0
        }
        try:
            summary['total_sales'] = sum(s['amount'] for s in self.supabase.table('sales').select('amount').eq('sale_date', report_date.isoformat()).execute().data)
            summary['total_expenses'] = sum(e['amount'] for e in self.supabase.table('expenses').select('amount').eq('expense_date', report_date.isoformat()).execute().data)
            summary['vendor_payments'] = sum(p['amount'] for p in self.supabase.table('vendor_payments').select('amount').eq('payment_date', report_date.isoformat()).execute().data)

            for p in self.supabase.table('personal_transactions').select('transaction_type,amount').eq('transaction_date', report_date.isoformat()).execute().data:
                if p['transaction_type'] == 'withdrawal':
                    summary['withdrawals'] += p['amount']
                else:
                    summary['investments'] += p['amount']

            summary['net_cash'] = (summary['total_sales'] - summary['total_expenses'] -
                                   summary['vendor_payments'] - summary['withdrawals'] +
                                   summary['investments'])

            vendors = self.vendor_mgr.get_all_vendors(include_inactive=False)
            summary['vendor_payable'] = sum(v['current_balance'] for v in vendors if v['current_balance'] > 0)

            summary['personal_balance'] = self.personal_mgr.get_balance()

            return summary
        except Exception as e:
            st.error(f"Error generating daily summary: {e}")
            return summary

    def get_sales_report(self, start_date: date, end_date: date, user: Dict = None) -> pd.DataFrame:
        try:
            query = self.supabase.table('sales')\
                .select('*, shifts(shift_name), users(full_name)')\
                .gte('sale_date', start_date.isoformat())\
                .lte('sale_date', end_date.isoformat())\
                .order('sale_date', desc=True)
            df = pd.DataFrame(query.execute().data)
            if not df.empty and 'shifts' in df.columns:
                df['shift'] = df['shifts'].apply(lambda x: x['shift_name'] if x else '')
            return df
        except Exception as e:
            st.error(f"Error fetching sales report: {e}")
            return pd.DataFrame()

    def get_expenses_report(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            response = self.supabase.table('expenses')\
                .select('*, expense_heads(head_name), shifts(shift_name), users(full_name)')\
                .gte('expense_date', start_date.isoformat())\
                .lte('expense_date', end_date.isoformat())\
                .order('expense_date', desc=True)\
                .execute()
            df = pd.DataFrame(response.data)
            if not df.empty:
                if 'expense_heads' in df.columns:
                    df['head_name'] = df['expense_heads'].apply(lambda x: x['head_name'] if x else '')
                if 'shifts' in df.columns:
                    df['shift'] = df['shifts'].apply(lambda x: x['shift_name'] if x else '')
            return df
        except Exception as e:
            st.error(f"Error fetching expenses report: {e}")
            return pd.DataFrame()

    def get_vendor_ledger_report(self, vendor_id: str, start_date: date, end_date: date) -> pd.DataFrame:
        ledger = self.vendor_mgr.get_vendor_ledger(vendor_id, start_date, end_date)
        return pd.DataFrame(ledger)

    def get_personal_ledger_report(self, start_date: date, end_date: date) -> pd.DataFrame:
        trans = self.personal_mgr.get_transactions(start_date=start_date, end_date=end_date)
        return pd.DataFrame(trans)


# ============================================
# SALES MANAGER
# ============================================
class SalesManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()

    def add_sale(self, sale_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            sale_data['created_by'] = created_by
            sale_data['created_at'] = datetime.now().isoformat()
            sale_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('sales').insert(sale_data).execute()
            return True, "Sale added."
        except Exception as e:
            return False, f"Error adding sale: {e}"

    def get_sales(self, shift_id: str = None, start_date: date = None, end_date: date = None, limit: int = None) -> List[Dict]:
        try:
            query = self.supabase.table('sales').select('*, shifts(shift_name)')
            if shift_id:
                query = query.eq('shift_id', shift_id)
            if start_date:
                query = query.gte('sale_date', start_date.isoformat())
            if end_date:
                query = query.lte('sale_date', end_date.isoformat())
            query = query.order('sale_date', desc=True)
            if limit:
                query = query.limit(limit)
            return query.execute().data
        except Exception as e:
            st.error(f"Error fetching sales: {e}")
            return []

    def delete_sale(self, sale_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table('sales').delete().eq('id', sale_id).execute()
            return True, "Sale deleted."
        except Exception as e:
            return False, f"Error deleting sale: {e}"


# ============================================
# EXPENSES MANAGER
# ============================================
class ExpensesManager:
    def __init__(self):
        self.supabase = SupabaseConnection.get_client()

    def add_expense(self, expense_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            expense_data['created_by'] = created_by
            expense_data['created_at'] = datetime.now().isoformat()
            expense_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('expenses').insert(expense_data).execute()
            return True, "Expense added."
        except Exception as e:
            return False, f"Error adding expense: {e}"

    def get_expenses(self, shift_id: str = None, start_date: date = None, end_date: date = None, limit: int = None) -> List[Dict]:
        try:
            query = self.supabase.table('expenses').select('*, expense_heads(head_name), shifts(shift_name)')
            if shift_id:
                query = query.eq('shift_id', shift_id)
            if start_date:
                query = query.gte('expense_date', start_date.isoformat())
            if end_date:
                query = query.lte('expense_date', end_date.isoformat())
            query = query.order('expense_date', desc=True)
            if limit:
                query = query.limit(limit)
            return query.execute().data
        except Exception as e:
            st.error(f"Error fetching expenses: {e}")
            return []

    def delete_expense(self, expense_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table('expenses').delete().eq('id', expense_id).execute()
            return True, "Expense deleted."
        except Exception as e:
            return False, f"Error deleting expense: {e}"
