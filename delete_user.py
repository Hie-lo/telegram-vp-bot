import sqlite3
import sys

DB_NAME = 'pasarguard_data.db'

def delete_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # حذف رکوردهای وابسته
    tables = [
        'referral_logs',   # ستون referrer_id و referred_id
        'payment_requests', # ستون user_id
        'test_requests',    # ستون user_id
        'orders',           # ستون user_id
        'transactions',     # ستون user_id
        'admins',           # ستون user_id
        'payment_logs'      # ستون user_id و admin_id
    ]
    for table in tables:
        # حذف رکوردهایی که user_id دارند
        cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        # اگر جدول ستون referrer_id دارد (فقط referral_logs)
        if table == 'referral_logs':
            cursor.execute(f"DELETE FROM {table} WHERE referrer_id = ?", (user_id,))
    
    # حذف خود کاربر
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