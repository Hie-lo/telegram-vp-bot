# fix_db.py
import sqlite3
import random
import string

DB_NAME = 'pasarguard_data.db'

def add_columns():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # اضافه کردن ستون referral_code
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE')
        print("✅ ستون referral_code اضافه شد.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("⚠️ ستون referral_code قبلاً وجود دارد.")
        else:
            print(f"❌ خطا: {e}")
    
    # اضافه کردن ستون referrer_id
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN referrer_id INTEGER')
        print("✅ ستون referrer_id اضافه شد.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("⚠️ ستون referrer_id قبلاً وجود دارد.")
        else:
            print(f"❌ خطا: {e}")
    
    # اضافه کردن ستون referral_earnings
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN referral_earnings INTEGER DEFAULT 0')
        print("✅ ستون referral_earnings اضافه شد.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("⚠️ ستون referral_earnings قبلاً وجود دارد.")
        else:
            print(f"❌ خطا: {e}")
    
    # تولید کد رفرال برای کاربرانی که ندارند
    cursor.execute('SELECT user_id FROM users WHERE referral_code IS NULL')
    users = cursor.fetchall()
    for (user_id,) in users:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            cursor.execute('SELECT 1 FROM users WHERE referral_code = ?', (code,))
            if not cursor.fetchone():
                cursor.execute('UPDATE users SET referral_code = ? WHERE user_id = ?', (code, user_id))
                break
    print(f"✅ کد رفرال برای {len(users)} کاربر تولید شد.")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    add_columns()