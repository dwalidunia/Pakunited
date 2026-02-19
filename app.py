# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any, Tuple
from supabase import create_client, Client
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import matplotlib.pyplot as plt
import time

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
# VENDOR MANAGER (with Returns)
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

    # Purchases
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

    def update_purchase(self, purchase_id: str, purchase_data: Dict) -> Tuple[bool, str]:
        try:
            purchase_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendor_purchases').update(purchase_data).eq('id', purchase_id).execute()
            return True, "Purchase updated."
        except Exception as e:
            return False, f"Error updating purchase: {e}"

    def delete_purchase(self, purchase_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table('vendor_purchases').delete().eq('id', purchase_id).execute()
            return True, "Purchase deleted."
        except Exception as e:
            return False, f"Error deleting purchase: {e}"

    # Payments
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

    def update_payment(self, payment_id: str, payment_data: Dict) -> Tuple[bool, str]:
        try:
            payment_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendor_payments').update(payment_data).eq('id', payment_id).execute()
            return True, "Payment updated."
        except Exception as e:
            return False, f"Error updating payment: {e}"

    def delete_payment(self, payment_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table('vendor_payments').delete().eq('id', payment_id).execute()
            return True, "Payment deleted."
        except Exception as e:
            return False, f"Error deleting payment: {e}"

    # Returns (New)
    def add_return(self, return_data: Dict, created_by: str) -> Tuple[bool, str]:
        try:
            return_data['created_by'] = created_by
            return_data['created_at'] = datetime.now().isoformat()
            return_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendor_returns').insert(return_data).execute()
            return True, "Return recorded. Vendor balance reduced."
        except Exception as e:
            return False, f"Error adding return: {e}"

    def get_returns(self, vendor_id: str = None, start_date: date = None, end_date: date = None, limit: int = None) -> List[Dict]:
        try:
            query = self.supabase.table('vendor_returns')\
                .select('*, vendors(vendor_name), shifts(shift_name)')\
                .order('return_date', desc=True)
            if vendor_id:
                query = query.eq('vendor_id', vendor_id)
            if start_date:
                query = query.gte('return_date', start_date.isoformat())
            if end_date:
                query = query.lte('return_date', end_date.isoformat())
            if limit:
                query = query.limit(limit)
            return query.execute().data
        except Exception as e:
            st.error(f"Error fetching returns: {e}")
            return []

    def update_return(self, return_id: str, return_data: Dict) -> Tuple[bool, str]:
        try:
            return_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('vendor_returns').update(return_data).eq('id', return_id).execute()
            return True, "Return updated."
        except Exception as e:
            return False, f"Error updating return: {e}"

    def delete_return(self, return_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table('vendor_returns').delete().eq('id', return_id).execute()
            return True, "Return deleted."
        except Exception as e:
            return False, f"Error deleting return: {e}"

    # Vendor Ledger (includes purchases, payments, returns)
    def get_vendor_ledger(self, vendor_id: str, start_date: date, end_date: date) -> List[Dict]:
        try:
            purchases = self.supabase.table('vendor_purchases')\
                .select('purchase_date as date, amount, invoice_number, notes, shifts(shift_name)')\
                .eq('vendor_id', vendor_id)\
                .gte('purchase_date', start_date.isoformat())\
                .lte('purchase_date', end_date.isoformat())\
                .execute().data
            payments = self.supabase.table('vendor_payments')\
                .select('payment_date as date, amount, notes, shifts(shift_name)')\
                .eq('vendor_id', vendor_id)\
                .gte('payment_date', start_date.isoformat())\
                .lte('payment_date', end_date.isoformat())\
                .execute().data
            returns = self.supabase.table('vendor_returns')\
                .select('return_date as date, amount, reason as notes, shifts(shift_name)')\
                .eq('vendor_id', vendor_id)\
                .gte('return_date', start_date.isoformat())\
                .lte('return_date', end_date.isoformat())\
                .execute().data

            ledger = []
            for p in purchases:
                ledger.append({
                    'date': p['date'],
                    'type': 'Purchase',
                    'invoice': p.get('invoice_number', ''),
                    'debit': p['amount'],
                    'credit': 0,
                    'notes': p.get('notes', ''),
                    'shift': p['shifts']['shift_name'] if p['shifts'] else ''
                })
            for p in payments:
                ledger.append({
                    'date': p['date'],
                    'type': 'Payment',
                    'invoice': '',
                    'debit': 0,
                    'credit': p['amount'],
                    'notes': p.get('notes', ''),
                    'shift': p['shifts']['shift_name'] if p['shifts'] else ''
                })
            for r in returns:
                ledger.append({
                    'date': r['date'],
                    'type': 'Return',
                    'invoice': '',
                    'debit': 0,  # Return reduces balance, so treat as credit
                    'credit': r['amount'],
                    'notes': f"Return: {r.get('notes', '')}",
                    'shift': r['shifts']['shift_name'] if r['shifts'] else ''
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

    def update_transaction(self, trans_id: str, trans_data: Dict) -> Tuple[bool, str]:
        try:
            trans_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('personal_transactions').update(trans_data).eq('id', trans_id).execute()
            return True, "Transaction updated."
        except Exception as e:
            return False, f"Error updating transaction: {e}"

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

    def update_sale(self, sale_id: str, sale_data: Dict) -> Tuple[bool, str]:
        try:
            sale_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('sales').update(sale_data).eq('id', sale_id).execute()
            return True, "Sale updated."
        except Exception as e:
            return False, f"Error updating sale: {e}"

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

    def update_expense(self, expense_id: str, expense_data: Dict) -> Tuple[bool, str]:
        try:
            expense_data['updated_at'] = datetime.now().isoformat()
            self.supabase.table('expenses').update(expense_data).eq('id', expense_id).execute()
            return True, "Expense updated."
        except Exception as e:
            return False, f"Error updating expense: {e}"

    def delete_expense(self, expense_id: str, user_role: str) -> Tuple[bool, str]:
        if user_role not in ['Super User', 'Owner']:
            return False, "Permission denied."
        try:
            self.supabase.table('expenses').delete().eq('id', expense_id).execute()
            return True, "Expense deleted."
        except Exception as e:
            return False, f"Error deleting expense: {e}"


# ============================================
# PDF GENERATION FUNCTIONS
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
# PAGE CONFIG & CUSTOM CSS
# ============================================
st.set_page_config(
    page_title="Pharmacy ERP - Cash & Ledger",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS: Black sidebar with white text, white main area
st.markdown("""
<style>
    /* Main content area background white */
    .main {
        background-color: #ffffff;
        padding: 1rem 2rem;
    }
    
    /* Sidebar background black */
    section[data-testid="stSidebar"] {
        background-color: #000000 !important;
        padding: 1.5rem 1rem;
    }
    
    /* Sidebar text color white */
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stSelectbox div,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: white !important;
    }
    
    /* Sidebar selectbox styling */
    section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: #333333;
        border-color: #555555;
        color: white;
    }
    section[data-testid="stSidebar"] div[data-baseweb="select"] > div:hover {
        border-color: #888888;
    }
    section[data-testid="stSidebar"] .stSelectbox svg {
        fill: white;
    }
    
    /* Sidebar button (logout) */
    section[data-testid="stSidebar"] .stButton > button {
        background-color: #333333;
        color: white;
        border: 1px solid #555555;
    }
    section[data-testid="stSidebar"] .stButton > button:hover {
        background-color: #444444;
        border-color: #777777;
    }
    
    /* User info card in sidebar */
    .sidebar-user-card {
        background: #1a1a1a;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        border: 1px solid #333333;
        color: white;
    }
    .sidebar-user-card p {
        margin: 0;
        color: #dddddd;
    }
    .sidebar-user-card .name {
        color: white;
        font-weight: 600;
    }
    
    /* Divider in sidebar */
    hr {
        border-color: #333333;
    }
    
    /* Rest of the styles (previous) */
    h1, h2, h3 {
        color: #0f172a;
        font-weight: 600;
    }
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
    .stForm {
        background-color: white;
        padding: 2rem;
        border-radius: 12px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border: 1px solid #e2e8f0;
        margin-bottom: 2rem;
    }
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
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1rem;
        font-weight: 500;
    }
    .stAlert {
        border-radius: 8px;
        border-left-width: 4px;
    }
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
# LOGIN / LOGOUT
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
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <h2 style="color: white; margin-bottom: 0;">💊 Pharmacy ERP</h2>
            <p style="color: #cccccc; font-size: 0.9rem;">Cash & Ledger</p>
        </div>
        """, unsafe_allow_html=True)

        user = st.session_state.user
        st.markdown(f"""
        <div class="sidebar-user-card">
            <p class="name">👤 {user['full_name']}</p>
            <p>{user['role']}</p>
            {f"<p style='color: #3b82f6;'>Shift: {user['shift']}</p>" if user.get('shift') else ""}
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
# EDIT FUNCTIONS (Reusable)
# ============================================
def edit_sale():
    st.subheader("✏️ Edit Sale")
    sales_mgr = SalesManager()
    sales = sales_mgr.get_sales(limit=50)
    if not sales:
        st.info("No sales to edit.")
        return
    sale_dict = {f"{s['sale_date']} - {s['invoice_number']} (PKR {s['amount']})": s['id'] for s in sales}
    selected = st.selectbox("Select Sale to Edit", list(sale_dict.keys()))
    sale_id = sale_dict[selected]
    sale = next(s for s in sales if s['id'] == sale_id)

    with st.form("edit_sale_form"):
        col1, col2 = st.columns(2)
        with col1:
            invoice = st.text_input("Invoice Number", value=sale.get('invoice_number', ''))
            amount = st.number_input("Amount (PKR)", min_value=0.0, value=float(sale['amount']), step=100.0, format="%.2f")
        with col2:
            sale_date = st.date_input("Date", value=datetime.strptime(sale['sale_date'], '%Y-%m-%d').date())
            notes = st.text_area("Notes", value=sale.get('notes', ''))
        submitted = st.form_submit_button("Update Sale")
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'invoice_number': invoice,
                    'amount': amount,
                    'sale_date': sale_date.isoformat(),
                    'notes': notes,
                    'updated_at': datetime.now().isoformat()
                }
                success, msg = sales_mgr.update_sale(sale_id, data)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

def edit_expense():
    st.subheader("✏️ Edit Expense")
    exp_mgr = ExpensesManager()
    ehm = ExpenseHeadManager()
    expenses = exp_mgr.get_expenses(limit=50)
    if not expenses:
        st.info("No expenses to edit.")
        return
    exp_dict = {f"{e['expense_date']} - {e.get('expense_heads', {}).get('head_name', 'Unknown')} (PKR {e['amount']})": e['id'] for e in expenses}
    selected = st.selectbox("Select Expense to Edit", list(exp_dict.keys()))
    exp_id = exp_dict[selected]
    expense = next(e for e in expenses if e['id'] == exp_id)

    heads = ehm.get_all_heads(include_inactive=False)
    head_dict = {h['head_name']: h['id'] for h in heads}
    current_head = expense.get('expense_heads', {}).get('head_name', '')

    with st.form("edit_expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            head = st.selectbox("Expense Head", list(head_dict.keys()), index=list(head_dict.keys()).index(current_head) if current_head in head_dict else 0)
            amount = st.number_input("Amount (PKR)", min_value=0.0, value=float(expense['amount']), step=100.0, format="%.2f")
        with col2:
            exp_date = st.date_input("Date", value=datetime.strptime(expense['expense_date'], '%Y-%m-%d').date())
            description = st.text_area("Description", value=expense.get('description', ''))
        submitted = st.form_submit_button("Update Expense")
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'expense_head_id': head_dict[head],
                    'amount': amount,
                    'expense_date': exp_date.isoformat(),
                    'description': description,
                    'updated_at': datetime.now().isoformat()
                }
                success, msg = exp_mgr.update_expense(exp_id, data)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

def edit_purchase(vendor_id):
    st.subheader("✏️ Edit Purchase")
    vm = VendorManager()
    purchases = vm.get_purchases(vendor_id=vendor_id, limit=50)
    if not purchases:
        st.info("No purchases to edit.")
        return
    purch_dict = {f"{p['purchase_date']} - {p.get('invoice_number', 'No Invoice')} (PKR {p['amount']})": p['id'] for p in purchases}
    selected = st.selectbox("Select Purchase to Edit", list(purch_dict.keys()))
    purch_id = purch_dict[selected]
    purchase = next(p for p in purchases if p['id'] == purch_id)

    with st.form("edit_purchase_form"):
        col1, col2 = st.columns(2)
        with col1:
            invoice = st.text_input("Invoice Number", value=purchase.get('invoice_number', ''))
            amount = st.number_input("Amount (PKR)", min_value=0.0, value=float(purchase['amount']), step=100.0, format="%.2f")
        with col2:
            pdate = st.date_input("Date", value=datetime.strptime(purchase['purchase_date'], '%Y-%m-%d').date())
            due = st.date_input("Due Date", value=datetime.strptime(purchase['due_date'], '%Y-%m-%d').date() if purchase.get('due_date') else None)
            notes = st.text_area("Notes", value=purchase.get('notes', ''))
        submitted = st.form_submit_button("Update Purchase")
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'invoice_number': invoice,
                    'amount': amount,
                    'purchase_date': pdate.isoformat(),
                    'due_date': due.isoformat() if due else None,
                    'notes': notes,
                    'updated_at': datetime.now().isoformat()
                }
                success, msg = vm.update_purchase(purch_id, data)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

def edit_payment(vendor_id):
    st.subheader("✏️ Edit Payment")
    vm = VendorManager()
    payments = vm.get_payments(vendor_id=vendor_id, limit=50)
    if not payments:
        st.info("No payments to edit.")
        return
    pay_dict = {f"{p['payment_date']} (PKR {p['amount']})": p['id'] for p in payments}
    selected = st.selectbox("Select Payment to Edit", list(pay_dict.keys()))
    pay_id = pay_dict[selected]
    payment = next(p for p in payments if p['id'] == pay_id)

    with st.form("edit_payment_form"):
        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input("Amount (PKR)", min_value=0.0, value=float(payment['amount']), step=100.0, format="%.2f")
        with col2:
            pdate = st.date_input("Date", value=datetime.strptime(payment['payment_date'], '%Y-%m-%d').date())
            notes = st.text_area("Notes", value=payment.get('notes', ''))
        submitted = st.form_submit_button("Update Payment")
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'amount': amount,
                    'payment_date': pdate.isoformat(),
                    'notes': notes,
                    'updated_at': datetime.now().isoformat()
                }
                success, msg = vm.update_payment(pay_id, data)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

def edit_return(vendor_id):
    st.subheader("✏️ Edit Return")
    vm = VendorManager()
    returns = vm.get_returns(vendor_id=vendor_id, limit=50)
    if not returns:
        st.info("No returns to edit.")
        return
    ret_dict = {f"{r['return_date']} (PKR {r['amount']})": r['id'] for r in returns}
    selected = st.selectbox("Select Return to Edit", list(ret_dict.keys()))
    ret_id = ret_dict[selected]
    ret = next(r for r in returns if r['id'] == ret_id)

    with st.form("edit_return_form"):
        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input("Amount (PKR)", min_value=0.0, value=float(ret['amount']), step=100.0, format="%.2f")
        with col2:
            rdate = st.date_input("Date", value=datetime.strptime(ret['return_date'], '%Y-%m-%d').date())
            reason = st.text_area("Reason", value=ret.get('reason', ''))
        submitted = st.form_submit_button("Update Return")
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'amount': amount,
                    'return_date': rdate.isoformat(),
                    'reason': reason,
                    'updated_at': datetime.now().isoformat()
                }
                success, msg = vm.update_return(ret_id, data)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

def edit_personal_transaction():
    st.subheader("✏️ Edit Personal Transaction")
    plm = PersonalLedgerManager()
    trans = plm.get_transactions(limit=50)
    if not trans:
        st.info("No transactions to edit.")
        return
    trans_dict = {f"{t['transaction_date']} - {t['transaction_type']} (PKR {t['amount']})": t['id'] for t in trans}
    selected = st.selectbox("Select Transaction to Edit", list(trans_dict.keys()))
    trans_id = trans_dict[selected]
    tran = next(t for t in trans if t['id'] == trans_id)

    with st.form("edit_personal_form"):
        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input("Amount (PKR)", min_value=0.0, value=float(tran['amount']), step=100.0, format="%.2f")
            trans_type = st.selectbox("Type", ['withdrawal', 'investment'], index=0 if tran['transaction_type']=='withdrawal' else 1)
        with col2:
            tdate = st.date_input("Date", value=datetime.strptime(tran['transaction_date'], '%Y-%m-%d').date())
            description = st.text_area("Description", value=tran.get('description', ''))
        submitted = st.form_submit_button("Update Transaction")
        if submitted:
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                data = {
                    'amount': amount,
                    'transaction_type': trans_type,
                    'transaction_date': tdate.isoformat(),
                    'description': description,
                    'updated_at': datetime.now().isoformat()
                }
                success, msg = plm.update_transaction(trans_id, data)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


# ============================================
# DASHBOARD
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
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)
                        st.rerun()
            with col2:
                if st.form_submit_button("Reactivate"):
                    success, msg = um.reactivate_user(user_id)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
                    st.rerun()
    else:
        st.info("No users found.")


# ============================================
# SALES ENTRY
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

    # Add Sale Form
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

    # Edit Section
    with st.expander("✏️ Edit Existing Sale"):
        edit_sale()

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

    # Edit Section
    with st.expander("✏️ Edit Existing Expense"):
        edit_expense()

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
# VENDOR LEDGER (with Returns and Edit)
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
    selected_vendor = st.selectbox("Select Vendor", list(vendor_dict.keys()))
    vendor_id = vendor_dict[selected_vendor]

    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("From", value=date.today().replace(day=1))
    with col2:
        end = st.date_input("To", value=date.today())

    # Display Ledger
    ledger = vm.get_vendor_ledger(vendor_id, start, end)
    if ledger:
        df = pd.DataFrame(ledger)
        st.dataframe(df, use_container_width=True, hide_index=True)
        if st.button("Export PDF", use_container_width=True):
            pdf = generate_pdf(df, f"Ledger - {selected_vendor}", "vendor_ledger.pdf")
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

    # Tabs for different operations
    tab1, tab2, tab3, tab4 = st.tabs(["➕ Add Purchase", "💳 Add Payment", "🔄 Vendor Return", "✏️ Edit Transactions"])

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

    with tab3:
        with st.form("return_form"):
            col1, col2 = st.columns(2)
            with col1:
                amt = st.number_input("Return Amount*", min_value=0.0, step=100.0, format="%.2f")
            with col2:
                rdate = st.date_input("Date", value=date.today())
                reason = st.text_area("Reason")
            if st.form_submit_button("Record Return", use_container_width=True):
                if amt <= 0:
                    st.error("Amount must be > 0.")
                else:
                    data = {
                        'shift_id': shift_id,
                        'vendor_id': vendor_id,
                        'return_date': rdate.isoformat(),
                        'return_time': datetime.now().time().isoformat(),
                        'amount': amt,
                        'reason': reason
                    }
                    success, msg = vm.add_return(data, user['id'])
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tab4:
        st.subheader("Edit Transactions")
        edit_tab = st.radio("Select Type", ["Purchase", "Payment", "Return"], horizontal=True)
        if edit_tab == "Purchase":
            edit_purchase(vendor_id)
        elif edit_tab == "Payment":
            edit_payment(vendor_id)
        else:
            edit_return(vendor_id)


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

    tab1, tab2, tab3 = st.tabs(["➕ Withdrawal", "➕ Investment", "✏️ Edit"])

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

    with tab3:
        edit_personal_transaction()

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
