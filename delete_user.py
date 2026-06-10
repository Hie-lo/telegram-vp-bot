import sqlite3
import sys

DB_NAME = 'pasarguard_data.db'

def delete_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جداول و ستون‌های مرتبط با user_id
    tables_columns = {
        'payment_requests': ['user_id'],
        'test_requests': ['user_id'],
        'orders': ['user_id'],
        'transactions': ['user_id'],
        'admins': ['user_id'],
        'payment_logs': ['user_id', 'admin_id'],
        'referral_logs': ['referrer_id', 'referred_id']
    }
    
    for table, columns in tables_columns.items():
        for col in columns:
            try:
                cursor.execute(f"DELETE FROM {table} WHERE {col} = ?", (user_id,))
            except sqlite3.OperationalError:
                # اگر ستون وجود نداشت، نادیده بگیر
                pass
    
    # حذف خود کاربر از جدول اصلی
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    
    conn.commit()
    if cursor.rowcount > 0:
        print(f"✅ کاربر {user_id} و تمام اطلاعات مرتبط حذف شد.")
    else:
        print(f"❌ کاربر {user_id} یافت نشد.")
    
    conn.close()

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("استفاده: python delete_user.py [USER_ID]")
        sys.exit(1)
    try:
        uid = int(sys.argv[1])
        delete_user(uid)
    except ValueError:
        print("❌ لطفاً یک عدد صحیح وارد کنید.")