import sqlite3
from datetime import datetime
from typing import Optional, Dict, List, Tuple

DB_NAME = 'pasarguard_data.db'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Plans table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            traffic_gb INTEGER NOT NULL,
            duration_days INTEGER NOT NULL,
            price_rial INTEGER NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Test requests table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            request_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expire_time TIMESTAMP,
            config_sent BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(user_id)
        )
    ''')
    
    # Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            config_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        )
    ''')
    
    # Transactions table (for manual charges)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            type TEXT DEFAULT 'charge',
            admin_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
                   
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            receipt_file_id TEXT,
            admin_seen INTEGER DEFAULT 0,
            reject_reason TEXT,  -- اضافه شد
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')


    conn.commit()
    conn.close()
    init_payment_table()
    add_reject_reason_column()
# User operations
def add_user(user_id: int, username: str = None, first_name: str = None):
    """Add new user to database"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[Dict]:
    """Get user by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_username(username: str) -> Optional[Dict]:
    """Get user by username (with @ or without)"""
    username = username.lstrip('@')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def update_balance(user_id: int, amount: int) -> bool:
    """Add amount to user balance (positive or negative)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET balance = balance + ? 
        WHERE user_id = ?
    ''', (amount, user_id))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def get_user_balance(user_id: int) -> int:
    """Get user balance"""
    user = get_user(user_id)
    return user['balance'] if user else 0

# Plan operations
def add_plan(name: str, traffic_gb: int, duration_days: int, price_rial: int):
    """Add new plan"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO plans (name, traffic_gb, duration_days, price_rial)
        VALUES (?, ?, ?, ?)
    ''', (name, traffic_gb, duration_days, price_rial))
    conn.commit()
    conn.close()

def get_active_plans() -> List[Dict]:
    """Get all active plans"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM plans WHERE is_active = 1 ORDER BY price_rial')
    plans = cursor.fetchall()
    conn.close()
    return [dict(plan) for plan in plans]

def get_plan(plan_id: int) -> Optional[Dict]:
    """Get plan by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM plans WHERE id = ?', (plan_id,))
    plan = cursor.fetchone()
    conn.close()
    return dict(plan) if plan else None

# Test request operations
def has_test_request(user_id: int) -> bool:
    """Check if user already requested test"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM test_requests WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def add_test_request(user_id: int, expire_time: datetime):
    """Add test request for user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO test_requests (user_id, expire_time, config_sent)
        VALUES (?, ?, ?)
    ''', (user_id, expire_time, 0))
    conn.commit()
    conn.close()

def update_test_config_sent(user_id: int):
    """Mark test config as sent"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE test_requests SET config_sent = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Order operations
def create_order(user_id: int, plan_id: int, amount: int) -> int:
    """Create new order and return order ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO orders (user_id, plan_id, amount, status)
        VALUES (?, ?, ?, 'pending')
    ''', (user_id, plan_id, amount))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id

def update_order_config(order_id: int, config_link: str):
    """Update order with config link and mark as completed"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE orders 
        SET status = 'completed', config_link = ?
        WHERE id = ?
    ''', (config_link, order_id))
    conn.commit()
    conn.close()

# Transaction operations
def add_transaction(user_id: int, amount: int, admin_id: int = None):
    """Add transaction record"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, admin_id)
        VALUES (?, ?, ?)
    ''', (user_id, amount, admin_id))
    conn.commit()
    conn.close()

# =============== Payment Requests (برای شارژ کیف پول) ===============

def init_payment_table():
    """Create payment_requests table if not exists"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            receipt_file_id TEXT,
            admin_seen INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    conn.commit()
    conn.close()

def add_payment_request(user_id: int, amount: int, receipt_file_id: str = None) -> int:
    """Add a new payment request"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO payment_requests (user_id, amount, receipt_file_id)
        VALUES (?, ?, ?)
    ''', (user_id, amount, receipt_file_id))
    payment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return payment_id

def get_payment_request(payment_id: int):
    """Get payment request by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM payment_requests WHERE id = ?', (payment_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else None

def get_pending_payments(limit: int = 10):
    """Get pending payment requests for admin"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT pr.*, u.username, u.first_name 
        FROM payment_requests pr
        JOIN users u ON pr.user_id = u.user_id
        WHERE pr.status = 'pending'
        ORDER BY pr.created_at DESC
        LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    return [dict(r) for r in results]

def update_payment_status(payment_id: int, status: str, admin_id: int = None):
    """Update payment request status"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE payment_requests 
        SET status = ?
        WHERE id = ?
    ''', (status, payment_id))
    conn.commit()
    conn.close()

def add_reject_reason_column():
    """Add reject_reason column to payment_requests if not exists"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('ALTER TABLE payment_requests ADD COLUMN reject_reason TEXT')
        conn.commit()
        print("✅ ستون reject_reason با موفقیت اضافه شد.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            print(f"⚠️ خطا در افزودن ستون: {e}")
        # اگر ستون قبلاً وجود داشت، خطا را نادیده می‌گیریم
    finally:
        conn.close()

def approve_payment(payment_id: int, admin_id: int):
    """Approve payment and add balance to user"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get payment request
    cursor.execute('SELECT user_id, amount FROM payment_requests WHERE id = ? AND status = "pending"', (payment_id,))
    payment = cursor.fetchone()
    
    if not payment:
        conn.close()
        return False
    
    # Update user balance
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (payment['amount'], payment['user_id']))
    
    # Update payment status
    cursor.execute('UPDATE payment_requests SET status = "approved" WHERE id = ?', (payment_id,))
    
    # Add transaction record
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, admin_id)
        VALUES (?, ?, ?)
    ''', (payment['user_id'], payment['amount'], admin_id))
    
    conn.commit()
    conn.close()
    return True

def get_pending_payments_paginated(page: int = 1, per_page: int = 5, order_by: str = 'newest'):
    """
    Get pending payment requests with pagination
    order_by: 'newest' or 'oldest'
    """
    conn = get_db()
    cursor = conn.cursor()
    
    offset = (page - 1) * per_page
    order_clause = "ORDER BY created_at DESC" if order_by == 'newest' else "ORDER BY created_at ASC"
    
    cursor.execute(f'''
        SELECT pr.*, u.username, u.first_name 
        FROM payment_requests pr
        JOIN users u ON pr.user_id = u.user_id
        WHERE pr.status = 'pending'
        {order_clause}
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    
    results = cursor.fetchall()
    conn.close()
    return [dict(r) for r in results]

def count_pending_payments():
    """Get total number of pending payment requests"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM payment_requests WHERE status = "pending"')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def delete_plan(plan_id: int) -> bool:
    """Delete a plan by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM plans WHERE id = ?', (plan_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success