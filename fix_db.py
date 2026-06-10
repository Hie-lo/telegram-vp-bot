import sqlite3
import random
import string

DB_NAME = 'pasarguard_data.db'

def add_columns():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. اضافه کردن ستون referral_code (بدون UNIQUE)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN referral_code TEXT')
        print("✅ ستون referral_code اضافه شد (بدون UNIQUE).")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("⚠️ ستون referral_code قبلاً وجود دارد.")
        else:
            print(f"❌ خطا در افزودن ستون: {e}")
    
    # 2. اضافه کردن ستون referrer_id (اگر نبود)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN referrer_id INTEGER')
        print("✅ ستون referrer_id اضافه شد.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("⚠️ ستون referrer_id قبلاً وجود دارد.")
        else:
            print(f"❌ خطا: {e}")
    
    # 3. اضافه کردن ستون referral_earnings (اگر نبود)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN referral_earnings INTEGER DEFAULT 0')
        print("✅ ستون referral_earnings اضافه شد.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("⚠️ ستون referral_earnings قبلاً وجود دارد.")
        else:
            print(f"❌ خطا: {e}")
    
    # 4. تولید کد رفرال یکتا برای کاربرانی که ندارند
    cursor.execute('SELECT user_id FROM users WHERE referral_code IS NULL')
    users = cursor.fetchall()
    updated = 0
    for (user_id,) in users:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            cursor.execute('SELECT 1 FROM users WHERE referral_code = ?', (code,))
            if not cursor.fetchone():
                cursor.execute('UPDATE users SET referral_code = ? WHERE user_id = ?', (code, user_id))
                updated += 1
                break
    print(f"✅ کد رفرال برای {updated} کاربر تولید شد.")
    
    # 5. ایجاد ایندکس یکتا روی ستون referral_code (اگر وجود نداشته باشد)
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)')
        print("✅ ایندکس یکتا روی referral_code ایجاد شد.")
    except sqlite3.OperationalError as e:
        print(f"⚠️ ایجاد ایندکس ممکن نیست: {e}")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    add_columns()